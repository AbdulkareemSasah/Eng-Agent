"""The sign-off screen and its rules end to end against the engine stand-in (plan 0006 T9b; spec 0006 AC42, Q24).

The report callable is a stub here (it only has to be linked); the real-engine half is re-checked in plan T17c.
Exceptions follow the interim reading of Q24: the verdicts that are neither PASS nor NOT_APPLICABLE, numbered from 1 in
report order, each with the reason field of the request item `exc_<n>`.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from http import HTTPStatus
from pathlib import Path

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Provenance
from eng_contract.refs import Ref
from helpers.engine_standin import EngineStandIn, Wired, until
from helpers.page_client import PageClient
from pydantic import JsonValue

from eng_harness.ctx import Preview, PreviewItem
from eng_harness.journal import EventType, JournalReader
from eng_harness.pages import PageApprovalPort, PageInputPort, PageServer
from eng_harness.pages._screens_approval import sign_off_screens
from eng_harness.ports import ApprovalRequest
from eng_harness.report import ReleaseMarks

SHA = "a" * 64
STATUSES = ("FAIL", "PASS", "NEEDS_ENGINEER", "NOT_APPLICABLE")  # C1 to C4
UNRELEASED = "Depends on unreleased tool `csi/new-tool` (record `rec-7`)"
RELEASED = ReleaseMarks(records={"csi/new-tool": "rec-7"})
REASON = "accepted by the project engineer"


def _producer(tool: str) -> Provenance:
    return Provenance(tool=tool, tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0)


def _verdict(subject: str, status: str) -> dict[str, JsonValue]:
    return {
        "source": "host",
        "check_id": "steel:ratio",
        "code": "AISC",
        "subject": {"kind": "frame", "id": subject},
        "ratio": 1.2 if status == "FAIL" else 0.5,
        "ratio_limit": 1.0,
        "status": status,
        "governing": True,
    }


@contextmanager
def _signoff(
    root: Path,
    *,
    marks: ReleaseMarks,
    exceptions: Sequence[str] = ("exc_1", "exc_2"),
    kind: str = "verdicts.set/1",
    statuses: Sequence[str] = STATUSES,
) -> Iterator[tuple[Wired, ApprovalRequest]]:
    engine = EngineStandIn(root)
    store = engine.store
    counts: dict[str, JsonValue] = {
        s: statuses.count(s) for s in ("PASS", "FAIL", "NOT_APPLICABLE", "NEEDS_ENGINEER", "ERROR")
    }
    body: dict[str, JsonValue] = {
        "verdicts": [_verdict(f"C{n}", status) for n, status in enumerate(statuses, 1)],
        "traces": [],
        "counts": counts,
        "draft": False,
    }
    if kind == "harness.host_design_verdicts/1":  # the calc port's three members (spec 0007 4.4.3)
        calc_id = "harness.host_design_verdicts"
        trace: dict[str, JsonValue] = {"inputs": [], "constants": [], "steps": [], "outputs": []}
        trace |= {"calc_id": calc_id, "calc_version": "1", "content_sha256": SHA}
        calc: dict[str, JsonValue] = {"id": calc_id, "version": 1, "content_sha256": SHA, "status": "draft"}
        body |= {"calc": calc, "trace": trace, "draft": True}
    verdicts = store.put(kind, body, _producer("csi/new-tool"))
    started = {"kind": "tool", "name": "design", "args": {}, "args_sha256": SHA, "effect": "read"}
    done = {"result": {"ref": verdicts.result_id, "summary": {}, "warnings": [], "complete": True}, "duration_ms": 1}
    engine._writer.append(EventType.STEP_STARTED, started, path="0", attempt=1)  # the stand-in has no step helper
    engine._writer.append(EventType.STEP_COMPLETED, done, path="0", attempt=1)
    items = [PreviewItem(id="out_1", label="Design verdicts", refs=(Ref.model_validate({"$ref": verdicts.result_id}),))]
    items += [PreviewItem(id=item, label="Exception", refs=()) for item in exceptions]
    args = Preview(items=tuple(items), diff_ref=None, models=()).model_dump(mode="json", by_alias=True)
    stored = store.put("harness.approval_preview/1", args, _producer("harness"))
    request = ApprovalRequest(
        request_id="apr_sign",
        run_id="run_standin",
        kind="sign_off",
        title="Sign the design",
        preview_ref=stored.result_id,
        shown_sha256=payload_sha256(args),
        binding=(),
        items=tuple(i.id for i in items),
    )
    builders, checks = sign_off_screens(store, lambda: JournalReader(engine.run_dir))
    approvals = PageApprovalPort(builders=builders, checks=checks, marks=marks, report=lambda: "<p>stub</p>")
    engine.sink = approvals.hub.emit
    with PageServer(approvals.hub) as server:
        client = PageClient(server)
        client.open()
        try:
            yield Wired(approvals, PageInputPort(approvals), engine, client), request
        finally:
            engine.close()


def test_signoff_rules(tmp_path: Path) -> None:
    with _signoff(tmp_path, marks=RELEASED) as (w, request):
        future = w.open(request)
        shown = w.client.get(f"/request/{request.request_id}")
        assert shown.status == HTTPStatus.OK
        assert 'href="/report"' in shown.body
        assert "DRAFT" in shown.body
        assert UNRELEASED in shown.body
        assert 'name="acknowledged_unreleased"' in shown.body
        assert 'name="reason_exc_1"' in shown.body
        assert 'name="reason_exc_2"' in shown.body
        assert 'name="reason_exc_3"' not in shown.body  # a PASS and a NOT_APPLICABLE are no exceptions
        assert 'name="by"' in shown.body
        both = {"reason_exc_1": REASON, "reason_exc_2": "second"}
        # an exception without its reason is refused, and so is a missing acknowledgement
        assert w.answer(request, acknowledged_unreleased="on") == HTTPStatus.BAD_REQUEST
        assert w.answer(request, reason_exc_1=REASON, acknowledged_unreleased="on") == HTTPStatus.BAD_REQUEST
        assert w.answer(request, **both) == HTTPStatus.BAD_REQUEST
        assert (
            w.answer(request, **{**both, "reason_exc_2": "  "}, acknowledged_unreleased="on") == HTTPStatus.BAD_REQUEST
        )
        assert not future.done()
        assert w.answer(request, **both, acknowledged_unreleased="on") == HTTPStatus.OK
        answer = future.result(timeout=5)
    assert answer is not None
    assert answer.decision == "approve"
    assert dict(answer.item_reasons) == {"exc_1": REASON, "exc_2": "second"}
    assert answer.acknowledged_unreleased is True


def test_screen_shows_the_verdict_counts_and_the_exceptions(tmp_path: Path) -> None:
    with _signoff(tmp_path, marks=ReleaseMarks(records={})) as (w, request):
        future = w.open(request)
        body = w.client.get(f"/request/{request.request_id}").body
        assert w.answer(request, decision="reject", reason="read only") == HTTPStatus.OK  # ends the stand-in's wait
        future.result(timeout=5)
    for status in ("FAIL", "PASS", "NEEDS_ENGINEER", "NOT_APPLICABLE", "ERROR"):
        assert f">{status}<" in body
    assert body.index("frame C1") < body.index("frame C3")  # report order: exc_1 is C1, exc_2 is C3
    assert "frame C2" not in body
    assert "frame C4" not in body
    assert "unreleased" not in body
    assert 'name="acknowledged_unreleased"' not in body


def test_signoff_without_unreleased_tools_needs_no_acknowledgement(tmp_path: Path) -> None:
    with _signoff(tmp_path, marks=ReleaseMarks(records={})) as (w, request):
        future = w.open(request)
        assert w.answer(request) == HTTPStatus.BAD_REQUEST  # the exceptions still need their reasons
        assert w.answer(request, reason_exc_1="ok", reason_exc_2="ok") == HTTPStatus.OK
        until(future.done)


def test_an_exception_without_its_item_cannot_be_signed(tmp_path: Path) -> None:
    with _signoff(tmp_path, marks=ReleaseMarks(records={}), exceptions=("exc_1",)) as (w, request):
        future = w.open(request)
        body = w.client.get(f"/request/{request.request_id}").body
        assert 'name="reason_exc_1"' in body
        assert 'name="reason_exc_2"' not in body  # no item, so no reason field
        assert w.answer(request, reason_exc_1="ok") == HTTPStatus.BAD_REQUEST
        assert not future.done()
        assert w.answer(request, decision="reject", reason="exception C3 cannot be explained") == HTTPStatus.OK
        until(future.done)


def test_rejecting_the_sign_off_needs_no_exception_reasons(tmp_path: Path) -> None:
    with _signoff(tmp_path, marks=RELEASED) as (w, request):
        future = w.open(request)
        assert w.answer(request, decision="reject", reason="not yet") == HTTPStatus.OK
        answer = future.result(timeout=5)
    assert answer is not None
    assert (answer.decision, answer.reason, answer.acknowledged_unreleased) == ("reject", "not yet", False)


def test_signoff_reads_host_design_verdicts(tmp_path: Path) -> None:
    """The edit cycle stores `harness.host_design_verdicts/1`, never `verdicts.set/1` (plan 0006 T9c, B-559)."""
    kind, statuses = "harness.host_design_verdicts/1", ("NEEDS_ENGINEER", "FAIL")
    with _signoff(tmp_path, marks=ReleaseMarks(records={}), kind=kind, statuses=statuses) as (w, request):
        future = w.open(request)
        body = w.client.get(f"/request/{request.request_id}").body
        # a signature without reasons is refused (first, so that a failure never leaves the answer wait open)
        assert w.answer(request) == HTTPStatus.BAD_REQUEST
        for status, count in (("NEEDS_ENGINEER", 1), ("FAIL", 1), ("PASS", 0)):  # the counts table cells
            assert f'{status}</bdi></td><td><bdi dir="auto">{count}</bdi>' in body
        assert body.index("frame C1") < body.index("frame C2")  # journal order: exc_1 is C1, exc_2 is C2
        assert 'name="reason_exc_1"' in body
        assert 'name="reason_exc_2"' in body
        assert w.answer(request, reason_exc_1=REASON) == HTTPStatus.BAD_REQUEST
        assert w.answer(request, reason_exc_2="second") == HTTPStatus.BAD_REQUEST
        assert not future.done()
        assert w.answer(request, reason_exc_1=REASON, reason_exc_2="second") == HTTPStatus.OK
        answer = future.result(timeout=5)
    assert answer is not None
    assert dict(answer.item_reasons) == {"exc_1": REASON, "exc_2": "second"}


def test_signoff_rules_real_engine(tmp_path: Path) -> None:
    """AC42 re-check with the real engine through the production page wiring (plan 0006 T17c)."""
    import contextlib
    import threading
    import time
    from typing import Any, cast

    from eng_contract.envelope import SuccessEnvelope
    from eng_contract.ids import SeededIdSource
    from helpers.cli_deps import FakeInput, FakeOutput, FakePorts, Rig, client_for
    from workflows.rig import Host

    from eng_harness.block import Registry, workflow
    from eng_harness.cli import ExitCode
    from eng_harness.ctx import ApprovalKind, Preview, PreviewItem
    from eng_harness.journal import _events as ev
    from eng_harness.pages._answers import bound_sha256
    from eng_harness.pages._security import CSRF_FIELD
    from eng_harness.ports import ApprovalRequest

    statuses = STATUSES
    counts = {s: statuses.count(s) for s in ("PASS", "FAIL", "NOT_APPLICABLE", "NEEDS_ENGINEER", "ERROR")}
    sha = SHA
    calc_id = "harness.host_design_verdicts"
    trace: dict[str, JsonValue] = {
        "inputs": [], "constants": [], "steps": [], "outputs": [],
        "calc_id": calc_id, "calc_version": "1", "content_sha256": sha,
    }  # fmt: skip
    calc: dict[str, JsonValue] = {"id": calc_id, "version": 1, "content_sha256": sha, "status": "draft"}
    body: dict[str, JsonValue] = {
        "verdicts": [_verdict(f"C{n}", status) for n, status in enumerate(statuses, 1)],
        "traces": [],
        "counts": cast(dict[str, JsonValue], counts),
        "draft": True,
        "calc": calc,
        "trace": trace,
    }
    flow_name = "signoff_real_flow"
    held: dict[str, Any] = {}

    @workflow(name=flow_name, version=1, description="Tool then sign-off for the real-engine AC42 re-check.")
    async def signoff_real_flow(ctx: Any, inp: FakeInput) -> FakeOutput:
        result = await ctx.tool("read_a", {"n": 0})
        items = [
            PreviewItem(id="out_1", label="Design verdicts", refs=(result.ref,)),
            PreviewItem(id="exc_1", label="Exception", refs=()),
            PreviewItem(id="exc_2", label="Exception", refs=()),
        ]
        await ctx.approve(
            "Sign the design", Preview(items=tuple(items), diff_ref=None, models=()), kind=ApprovalKind.SIGN_OFF
        )
        return FakeOutput()

    registry = Registry([signoff_real_flow])
    rig = Rig(tmp_path, real_engine=True)
    rig.workspace.mkdir(parents=True)
    (rig.workspace / "harness.toml").write_text(
        '[project_lane."csi/new-tool"]\nrecord = "rec-7"\n',
        encoding="utf-8",
    )

    def port_builder(
        config: Any,
        workspace: Any,
        store: Any,
        run_folder: Any,
        clock: Any,
        ids: Any,
        *,
        files: Any = None,
        visible: bool = False,
    ) -> FakePorts:
        host = Host(cast(SeededIdSource, ids), clock, workspace.root / "runs")
        producer = _producer("csi/new-tool")
        stored = store.put("harness.host_design_verdicts/1", body, producer)
        held["result_id"] = stored.result_id
        envelope = SuccessEnvelope(
            contract="eng-contract/1",
            ok=True,
            result_id=stored.result_id,
            kind="harness.host_design_verdicts/1",
            summary={"tool": "read_a"},
            complete=True,
            provenance=producer,
        )
        host.script("read_a", envelope)
        ports = FakePorts(rig.log, host)
        held["ports"] = ports
        return ports

    seen: dict[str, str] = {}
    posts: list[int] = []

    def interact(address: str) -> None:
        with contextlib.suppress(Exception):
            client = client_for(address)
            client.open()
            end = time.monotonic() + 15
            while not rig.shown or client.get(f"/request/{rig.shown[-1].request_id}").status != 200:
                assert time.monotonic() < end
                time.sleep(0.02)
            request = rig.shown[-1]
            assert isinstance(request, ApprovalRequest)
            page = client.get(f"/request/{request.request_id}")
            seen["body"] = page.body
            assert page.status == HTTPStatus.OK
            form_base = {
                CSRF_FIELD: client.token(f"/request/{request.request_id}"),
                "shown_sha256": bound_sha256(request),
                "by": "ada",
                "decision": "approve",
            }
            posts.append(
                client.post(f"/answer/{request.request_id}", form_base | {"acknowledged_unreleased": "on"}).status
            )
            posts.append(
                client.post(
                    f"/answer/{request.request_id}",
                    form_base | {"reason_exc_1": REASON, "acknowledged_unreleased": "on"},
                ).status
            )
            posts.append(
                client.post(
                    f"/answer/{request.request_id}",
                    form_base | {"reason_exc_1": REASON, "reason_exc_2": "second"},
                ).status
            )
            posts.append(
                client.post(
                    f"/answer/{request.request_id}",
                    form_base | {"reason_exc_1": REASON, "reason_exc_2": "  ", "acknowledged_unreleased": "on"},
                ).status
            )
            posts.append(
                client.post(
                    f"/answer/{request.request_id}",
                    form_base | {"reason_exc_1": REASON, "reason_exc_2": "second", "acknowledged_unreleased": "on"},
                ).status
            )

    def opener(address: str) -> bool:
        rig.opened.append(address)
        threading.Thread(target=interact, args=(address,), daemon=True).start()
        return True

    rig.open_with = opener
    code = rig.main(
        "run",
        flow_name,
        "--progress",
        "off",
        "--json",
        workflow_registry=registry,
        port_builder=port_builder,
    )
    assert code == ExitCode.OK, (code, rig.err.getvalue(), rig.out.getvalue())
    html = seen["body"]
    assert 'href="/report"' in html
    assert "DRAFT" in html
    assert UNRELEASED in html
    assert 'name="acknowledged_unreleased"' in html
    assert 'name="reason_exc_1"' in html
    assert 'name="reason_exc_2"' in html
    assert 'name="reason_exc_3"' not in html
    assert 'name="by"' in html
    assert posts == [
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.OK,
    ]
    [run_id] = rig.run_ids()
    reader = JournalReader(rig.runs / run_id)
    try:
        events = reader.events()
    finally:
        reader.close()
    resolved = [e.payload for e in events if isinstance(e.payload, ev.ApprovalResolved)]
    assert len(resolved) == 1
    assert resolved[0].decision == "approve"
    assert dict(resolved[0].item_reasons) == {"exc_1": REASON, "exc_2": "second"}
    assert resolved[0].acknowledged_unreleased is True
    assert events[-1].type is EventType.RUN_COMPLETED
