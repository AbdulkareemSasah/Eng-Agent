"""Kill while waiting at an approval, then resume (plan 0006 T17; AC35)."""

from __future__ import annotations

import multiprocessing
from http import HTTPStatus
from pathlib import Path
from typing import Any

from helpers.t17_real import kill_wait_worker, real_page, until
from workflows.ctx_flows import flow
from workflows.rig import Host

from eng_harness.block import Registry
from eng_harness.ctx import ModelHandle, Preview, PreviewItem
from eng_harness.engine import RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev


def _preview(host: Host, *items: str) -> Preview:
    state = host.models["m1"]
    assert state.model_id is not None
    handle = ModelHandle(model_key="m1", model_id=state.model_id, revision=state.revision or 0)
    shown = tuple(PreviewItem(id=item, label=f"Change {item}", refs=()) for item in items)
    return Preview(items=shown, diff_ref=None, models=(handle,))


def test_kill_while_waiting_then_resume(tmp_path: Path) -> None:
    """AC35: kill at an open approval; resume shows the same request; an answer completes; no resolved for the wait."""
    ctx = multiprocessing.get_context("spawn")
    ready, die = ctx.Event(), ctx.Event()
    process = ctx.Process(target=kill_wait_worker, args=(str(tmp_path), ready, die), daemon=True)
    process.start()
    assert ready.wait(30)
    request_id = (tmp_path / "request_id.txt").read_text(encoding="utf-8")
    shown_sha = (tmp_path / "shown_sha256.txt").read_text(encoding="utf-8")
    run_id = (tmp_path / "run_id.txt").read_text(encoding="utf-8")
    die.set()
    process.join(15)
    assert process.exitcode == 77

    box: list[Any] = []

    async def body(ctx: Any) -> list[str]:
        await ctx.approve("Apply the change", _preview(box[0].host, "i1"))
        return []

    workflow = flow(body, name="kill_flow")
    with real_page(tmp_path, Registry([workflow])) as page:
        box.append(page)
        future = page.resume(run_id)
        until(lambda: bool(page.shown), 15)
        request = page.shown[-1]
        assert request.request_id == request_id
        assert request.shown_sha256 == shown_sha
        assert page.client.get(f"/request/{request.request_id}").status == HTTPStatus.OK
        assert page.answer(request) == HTTPStatus.OK
        outcome = future.result(timeout=15)
    assert outcome.status is RunStatus.COMPLETED
    events = page.events(run_id)
    resolved = [e for e in events if e.type is EventType.APPROVAL_RESOLVED]
    assert len(resolved) == 1  # only the resume's answer; none from the killed wait
    assert isinstance(resolved[0].payload, ev.ApprovalResolved)
    assert resolved[0].payload.request_id == request_id
