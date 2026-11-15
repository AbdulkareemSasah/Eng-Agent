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
    root: Path, *, marks: ReleaseMarks, exceptions: Sequence[str] = ("exc_1", "exc_2")
) -> Iterator[tuple[Wired, ApprovalRequest]]:
    engine = EngineStandIn(root)
    store = engine.store
    counts: dict[str, JsonValue] = {
        s: STATUSES.count(s) for s in ("PASS", "FAIL", "NOT_APPLICABLE", "NEEDS_ENGINEER", "ERROR")
    }
    body: dict[str, JsonValue] = {
        "verdicts": [_verdict(f"C{n}", status) for n, status in enumerate(STATUSES, 1)],
        "traces": [],
        "counts": counts,
        "draft": False,
    }
    verdicts = store.put("verdicts.set/1", body, _producer("csi/new-tool"))
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
