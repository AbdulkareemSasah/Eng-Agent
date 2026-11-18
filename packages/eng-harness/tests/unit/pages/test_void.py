"""The page marks an approval the engine voided (plan 0006 T7b; spec 0006 4.4.5; AC34, page half)."""

import asyncio
from http import HTTPStatus
from pathlib import Path

from helpers.engine_standin import approval_request, wired

from eng_harness.errors import HarnessCode
from eng_harness.journal import Event, EventType
from eng_harness.journal import _events as ev
from eng_harness.pages import PageApprovalPort
from eng_harness.pages._security import Subject
from eng_harness.ports import ApprovalRequest

SHA = "a" * 64
MESSAGE = "the model changed after the answer"


def _void(message: str = MESSAGE, code: HarnessCode = HarnessCode.APPROVAL_VOID) -> Event:
    error = ev.HarnessError(harness_code=code, message=message)
    payload = ev.StepFailed(error=error, retryable=False, duration_ms=1)
    return Event(seq=9, type=EventType.STEP_FAILED, path="1", attempt=1, at="2026-01-01T00:00:00.000Z", payload=payload)


def _resolved(request: ApprovalRequest, decision: str = "approve") -> Event:
    payload = ev.ApprovalResolved.model_validate(
        {
            "request_id": request.request_id, "shown_sha256": SHA, "decision": decision,
            "rejected_items": [], "reason": None if decision == "approve" else "no", "by": "engineer:ada",
        }
    )  # fmt: skip
    return Event(
        seq=5, type=EventType.APPROVAL_RESOLVED, path=None, attempt=None, at="2026-01-01T00:00:00.000Z", payload=payload
    )


def _hub(*requests: ApprovalRequest) -> PageApprovalPort:
    port = PageApprovalPort()

    async def present() -> None:
        for request in requests:
            await port.present(request)

    asyncio.run(present())
    return port


def _text(port: PageApprovalPort, rid: str) -> str:
    screen = port.hub.screen("request", rid)
    assert screen is not None
    return "".join(node.render() for node in screen.render("tok"))


def test_void_shown_on_resolved_request(tmp_path: Path) -> None:
    request = approval_request()
    with wired(tmp_path) as w:
        future = w.open(request)
        assert w.answer(request, decision="approve") == HTTPStatus.OK
        assert future.result(timeout=5) is not None
        assert w.client.get(f"/request/{request.request_id}").status == HTTPStatus.NOT_FOUND  # answered: gone
        w.engine.journal(
            EventType.STEP_FAILED,
            {"error": {"harness_code": "APPROVAL_VOID", "message": MESSAGE}, "retryable": False, "duration_ms": 1},
        )
        page = w.client.get(f"/request/{request.request_id}")
        assert page.status == HTTPStatus.OK
        assert "voided" in page.body.lower()
        assert MESSAGE in page.body
        assert "<form" not in page.body
        assert "<button" not in page.body
        assert request.request_id not in w.client.get("/").body  # still not an open request


def test_post_to_recorded_request_is_conflict_get_is_not_found(tmp_path: Path) -> None:
    request = approval_request()
    path = f"/request/{request.request_id}"
    with wired(tmp_path) as w:
        future = w.open(request)
        token = w.client.token(path)  # a second answerer holds a token from before the first answer was recorded
        assert w.answer(request, decision="approve") == HTTPStatus.OK
        assert future.result(timeout=5) is not None
        form = {"csrf": token, "shown_sha256": request.shown_sha256, "by": "bob", "decision": "approve"}
        assert w.client.post(f"/answer/{request.request_id}", form).status == HTTPStatus.CONFLICT  # AC30
        assert w.client.get(path).status == HTTPStatus.NOT_FOUND  # a recorded request is shown no more


def test_void_marks_the_most_recent_approved_request() -> None:
    first, second = approval_request("apr_a"), approval_request("apr_b", kind="PROMOTION")
    port = _hub(first, second)
    port.hub.emit(_resolved(first))
    port.hub.emit(_resolved(second))
    port.hub.emit(_void())
    assert port.hub.screen("request", "apr_a") is None  # only the most recent one is marked
    screen = port.hub.screen("request", "apr_b")
    assert screen is not None
    assert screen.fields == frozenset()
    assert screen.subject == Subject("approval", "apr_b", second.shown_sha256)
    assert "voided" in _text(port, "apr_b").lower()
    assert MESSAGE in _text(port, "apr_b")


def test_void_without_a_marked_kind_goes_to_the_index() -> None:
    rejected, info, change = (
        approval_request("apr_r"),
        approval_request("apr_i", kind="INFO"),
        approval_request("apr_c"),
    )
    port = _hub(rejected, info, change)
    port.hub.emit(_resolved(rejected, "reject"))  # a rejection, an INFO and an open request are not voided
    port.hub.emit(_resolved(info))
    port.hub.emit(_void("other failure", HarnessCode.NEEDS_ENGINEER))  # another code voids nothing
    port.hub.emit(_void("<b>changed</b>"))
    assert all(port.hub.screen("request", r) is None for r in ("apr_r", "apr_i"))
    body = port.hub.index().body
    assert "&lt;b&gt;changed&lt;/b&gt;" in body
    assert "<b>changed" not in body
    assert "other failure" not in body
    assert "apr_c" in body  # the open request stays listed


def test_void_marks_the_engine_kinds() -> None:
    """The engine journals the lower-case enum values (`ApprovalKind`); the upper-case spelling is accepted too."""
    for kind in ("change_set", "promotion", "CHANGE_SET", "PROMOTION"):
        request = approval_request("apr_k", kind=kind)
        port = _hub(request)
        port.hub.emit(_resolved(request))
        port.hub.emit(_void())
        assert "voided" in _text(port, "apr_k").lower(), kind
