"""The page approval end to end: stand-in (plan 0006 T7) and real engine (plan T17; AC29, AC33, AC34, AC37)."""

import time
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from pathlib import Path
from typing import Any

from helpers.engine_standin import SHA, approval_request, until, wired
from helpers.t17_real import RealPage, real_page
from helpers.t17_real import until as wait_until
from workflows.ctx_flows import flow
from workflows.rig import Host

from eng_harness.block import Registry
from eng_harness.ctx import ModelHandle, Preview, PreviewItem
from eng_harness.engine import RunStatus
from eng_harness.errors import ApprovalVoid, BlockRuleViolation, HarnessCode
from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev
from eng_harness.pages._answers import REASON, REJECT


def _resolved(run_dir: Path) -> list[ev.ApprovalResolved]:
    return [e.payload for e in JournalReader(run_dir).events() if isinstance(e.payload, ev.ApprovalResolved)]


def _preview(host: Host, *items: str) -> Preview:
    state = host.models["m1"]
    assert state.model_id is not None
    handle = ModelHandle(model_key="m1", model_id=state.model_id, revision=state.revision or 0)
    shown = tuple(PreviewItem(id=item, label=f"Change {item}", refs=()) for item in items)
    return Preview(items=shown, diff_ref=None, models=(handle,))


def test_answer_bound_to_hash(tmp_path: Path) -> None:
    request = approval_request()
    with wired(tmp_path) as w:
        future = w.open(request)
        assert w.answer(request, shown_sha256="b" * 64, decision="approve") == HTTPStatus.CONFLICT
        assert not future.done()
        assert request.request_id in w.client.get("/").body  # still open, shown again
        assert w.client.get(f"/request/{request.request_id}").status == HTTPStatus.OK
        assert w.answer(request, decision="approve", by="Ada") == HTTPStatus.OK
        answer = future.result(timeout=5)
    assert answer is not None
    assert (answer.request_id, answer.shown_sha256, answer.decision) == (request.request_id, SHA, "approve")
    assert [(r.request_id, r.shown_sha256, r.by, r.decision) for r in _resolved(w.engine.run_dir)] == [
        (request.request_id, SHA, "engineer:Ada", "approve")
    ]


def test_page_confirms_after_commit(tmp_path: Path) -> None:
    request = approval_request()
    with wired(tmp_path, ack_timeout_s=10) as w:
        w.engine.release.clear()  # the journal commits the answer, the sink is not told yet
        future = w.open(request)
        with ThreadPoolExecutor(max_workers=1) as pool:
            posted = pool.submit(w.client.post, f"/answer/{request.request_id}", w.form(request))
            until(lambda: len(_resolved(w.engine.run_dir)) == 1)
            time.sleep(0.2)
            assert not posted.done()  # committed, but the page has not seen it: the browser still waits
            w.engine.release.set()
            result = posted.result(timeout=5)
        assert future.result(timeout=5) is not None
    assert result.status == HTTPStatus.OK
    assert "Answer recorded." in result.body
    assert "not yet recorded" not in result.body

    with wired(tmp_path / "late", ack_timeout_s=0.3) as w:  # the sink never reports the commit
        w.engine.sink = None
        w.open(request)
        began = time.monotonic()
        late = w.client.post(f"/answer/{request.request_id}", w.form(request))
        waited = time.monotonic() - began
    assert late.status == HTTPStatus.OK
    assert "Answer received, not yet recorded." in late.body
    assert 'href="/"' in late.body
    assert 0.25 <= waited < 5


def test_answer_bound_to_hash_real_engine(tmp_path: Path) -> None:
    """AC29 re-check with the real engine: a wrong hash is 409; a matching hash journals the answer (plan T17)."""
    box: list[RealPage] = []

    async def body(ctx: Any) -> list[str]:
        await ctx.approve("Apply the change", _preview(box[0].host, "i1"))
        return []

    workflow = flow(body, name="hash_flow")
    with real_page(tmp_path, Registry([workflow])) as page:
        box.append(page)
        future = page.start("hash_flow")
        request = page.wait_shown()
        assert page.answer(request, shown_sha256="b" * 64) == HTTPStatus.CONFLICT
        assert request.request_id in page.client.get("/").body
        assert page.answer(request, by="Ada") == HTTPStatus.OK
        outcome = future.result(timeout=15)
    assert outcome.status is RunStatus.COMPLETED
    resolved = [e.payload for e in page.events(outcome.run_id) if isinstance(e.payload, ev.ApprovalResolved)]
    assert [(r.shown_sha256, r.by, r.decision) for r in resolved] == [(request.shown_sha256, "engineer:Ada", "approve")]


def test_page_confirms_after_commit_real_engine(tmp_path: Path) -> None:
    """AC37 re-check with the real engine: recorded only after the sink sees approval_resolved (plan T17)."""
    box: list[RealPage] = []

    async def body(ctx: Any) -> list[str]:
        await ctx.approve("Apply the change", _preview(box[0].host, "i1"))
        return []

    workflow = flow(body, name="ack_flow")
    with real_page(tmp_path / "ok", Registry([workflow]), gate_sink=True, ack_timeout_s=10) as page:
        box.append(page)
        gated = page.gated
        assert gated is not None
        held = gated.seen
        future = page.start("ack_flow")
        request = page.wait_shown()
        gated.release.clear()  # hold approval_resolved after present; earlier journal events already passed
        with ThreadPoolExecutor(max_workers=1) as pool:
            posted = pool.submit(page.client.post, f"/answer/{request.request_id}", page.form(request))
            wait_until(lambda: any(isinstance(e.payload, ev.ApprovalResolved) for e in held))
            time.sleep(0.2)
            assert not posted.done()
            gated.release.set()
            result = posted.result(timeout=10)
        assert future.result(timeout=15).status is RunStatus.COMPLETED
    assert result.status == HTTPStatus.OK
    assert "Answer recorded." in result.body
    assert "not yet recorded" not in result.body

    box.clear()
    with real_page(tmp_path / "late", Registry([workflow]), gate_sink=True, ack_timeout_s=0.3) as page:
        box.append(page)
        gated = page.gated
        assert gated is not None
        future = page.start("ack_flow")
        request = page.wait_shown()
        gated.release.clear()  # the sink never reports the commit within the ack timeout
        began = time.monotonic()
        late = page.client.post(f"/answer/{request.request_id}", page.form(request))
        waited = time.monotonic() - began
        gated.release.set()
        assert future.result(timeout=15).status is RunStatus.COMPLETED
    assert late.status == HTTPStatus.OK
    assert "Answer received, not yet recorded." in late.body
    assert 'href="/"' in late.body
    assert 0.25 <= waited < 5


def test_per_item_reject_end_to_end(tmp_path: Path) -> None:
    """AC33: item 2 rejected on the page; writes of 1 and 3 proceed; write of 2 is BlockRuleViolation (plan T17)."""
    box: list[RealPage] = []
    seen: dict[str, str | None] = {}

    async def body(ctx: Any) -> list[str]:
        approval = await ctx.approve("Apply the change", _preview(box[0].host, "i1", "i2", "i3"))
        for index, item in enumerate(("i1", "i2", "i3")):
            try:
                await ctx.tool("write_b", {"n": index, "model": "m1"}, under=approval, item=item)
            except BlockRuleViolation as stop:
                seen[item] = stop.message
            else:
                seen[item] = None
        return []

    workflow = flow(body, name="reject_flow")
    with real_page(tmp_path, Registry([workflow])) as page:
        box.append(page)
        # Two chained write results (items 1 and 3); item 2 is refused before the host (engine AC56 / EC5).
        page.host.script("write_b", page.written("m1", 1), page.written("m1", 2))
        future = page.start("reject_flow")
        request = page.wait_shown()
        fields = {REJECT + "i2": "on", REASON + "i2": "too thin"}
        assert page.answer(request, **fields) == HTTPStatus.OK
        outcome = future.result(timeout=15)
    assert outcome.status is RunStatus.COMPLETED
    assert seen["i1"] is None
    assert seen["i3"] is None
    assert seen["i2"] is not None
    assert "i2" in seen["i2"]
    calls = [entry.tool for entry in page.host.ledger]
    assert calls == ["write_b", "write_b"]  # rejected item never reached the host
    resolved = [e.payload for e in page.events(outcome.run_id) if isinstance(e.payload, ev.ApprovalResolved)]
    assert resolved[0].rejected_items == ["i2"]
    assert resolved[0].item_reasons == {"i2": "too thin"}


def test_void_after_model_change(tmp_path: Path) -> None:
    """AC34: model changed after the approval is shown and before the write: ApprovalVoid, nothing written.

    Engine AC55 leaves no STEP_FAILED / APPROVAL_VOID for a void before the first write. The voided page display
    is T7b (`tests/unit/pages/test_void.py`); this re-check asserts the real-engine journal half only.
    """
    box: list[RealPage] = []
    trail: list[str] = []

    async def body(ctx: Any) -> list[str]:
        approval = await ctx.approve("Apply the change", _preview(box[0].host, "i1"))
        try:
            await ctx.tool("write_b", {"n": 0, "model": "m1"}, under=approval, item="i1")
        except ApprovalVoid as void:
            trail.append(void.message)
        return []

    workflow = flow(body, name="void_flow")
    with real_page(tmp_path, Registry([workflow])) as page:
        box.append(page)
        future = page.start("void_flow")
        request = page.wait_shown()
        page.host.models["m1"] = page.host.models["m1"].model_copy(update={"fingerprint": "changed", "revision": 9})
        assert page.answer(request) == HTTPStatus.OK
        outcome = future.result(timeout=15)
        assert trail
        assert "changed since approval" in trail[0]
        assert page.host.ledger == []  # the port was not called
        events = list(page.events(outcome.run_id))
    assert outcome.status is RunStatus.COMPLETED
    assert not any(
        isinstance(e.payload, ev.StepFailed)
        and isinstance(e.payload.error, ev.HarnessError)
        and e.payload.error.harness_code is HarnessCode.APPROVAL_VOID
        for e in events
    ), "engine AC55: a void before the first write journals no APPROVAL_VOID step (page display is T7b)"
