"""One request takes one answer: of two simultaneous ones exactly one is accepted (plan 0006 T7; AC30)."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from pathlib import Path

import pytest
from helpers.engine_standin import SHA, approval_request, input_request, wired
from pydantic import BaseModel

from eng_harness.journal import Event, EventType, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.pages import PageApprovalPort, PageInputPort
from eng_harness.pages._security import RefusalError
from eng_harness.ports import ApprovalAnswer

FORM = {"shown_sha256": SHA, "by": "ada", "decision": "approve"}


def test_concurrent_answers_one_wins(tmp_path: Path) -> None:
    request = approval_request()
    with wired(tmp_path) as w:
        future = w.open(request)
        barrier = threading.Barrier(2)

        def post(name: str) -> int:
            token = w.client.token(f"/request/{request.request_id}")
            barrier.wait(timeout=5)
            form = {"csrf": token, "shown_sha256": request.shown_sha256, "by": name, "decision": "approve"}
            return w.client.post(f"/answer/{request.request_id}", form).status

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = [f.result(timeout=10) for f in [pool.submit(post, "ann"), pool.submit(post, "bob")]]
        given = future.result(timeout=5)
    assert sorted(statuses) == [HTTPStatus.OK, HTTPStatus.CONFLICT]
    assert given is not None
    resolved = [
        e.payload for e in JournalReader(w.engine.run_dir).events() if isinstance(e.payload, ev.ApprovalResolved)
    ]
    assert [(r.by, r.decision) for r in resolved] == [("engineer:" + given.by, "approve")]  # one record, the winner's
    assert statuses[0 if given.by == "ann" else 1] == HTTPStatus.OK  # and its poster got the 200


def _event(payload: BaseModel, type_: EventType) -> Event:
    return Event(seq=1, type=type_, path=None, attempt=None, at="2026-01-01T00:00:00.000Z", payload=payload)


def _resolved(rid: str) -> Event:
    payload = ev.ApprovalResolved(
        request_id=rid, shown_sha256=SHA, decision="approve", rejected_items=[], by="engineer:a"
    )
    return _event(payload, EventType.APPROVAL_RESOLVED)


def test_an_answer_is_used_once_and_held_for_the_engine() -> None:
    port = PageApprovalPort(ack_timeout_s=0)
    hub, request = port.hub, approval_request()

    async def scenario() -> ApprovalAnswer | None:
        await port.present(request)
        first = hub.submit("request", request.request_id, FORM)
        assert first.status == HTTPStatus.OK
        assert "Answer received, not yet recorded." in first.body  # the sink has not seen it
        second = hub.submit("request", request.request_id, {**FORM, "decision": "reject", "reason": "no"})
        assert second.status == HTTPStatus.CONFLICT
        assert "this request has been answered already" in second.body
        return await port.answer(request.request_id, wait=False)

    given = asyncio.run(scenario())
    assert given is not None
    assert (given.decision, given.by) == ("approve", "ada")  # the first answer, never the second


def test_unknown_requests_and_setups_are_not_found() -> None:
    hub = PageApprovalPort().hub
    with pytest.raises(RefusalError) as unknown:
        hub.submit("request", "apr_none", FORM)
    with pytest.raises(RefusalError) as setup:
        hub.submit("setup", "setup_one", FORM)
    assert (unknown.value.status, setup.value.status) == (HTTPStatus.NOT_FOUND, HTTPStatus.NOT_FOUND)


def test_the_sink_records_only_the_answer_to_an_open_request() -> None:
    port = PageApprovalPort(ack_timeout_s=0)
    hub, request, choice = port.hub, approval_request(), input_request()
    made = ev.DecisionMade(
        point="p", options=[], choice="a", decided_by="engineer:a", confidence=None, latency_ms=1, state_sha256=SHA,
        suggestions=[], request_id=choice.request_id,
    )  # fmt: skip
    unasked = made.model_copy(update={"request_id": None})
    paused = ev.RunPaused(reason="awaiting_input", request_ids=[request.request_id])

    async def scenario() -> None:
        await port.present(request)
        await PageInputPort(port).present(choice)
        hub.emit(_resolved("apr_other"))  # another request
        hub.emit(_event(paused, EventType.RUN_PAUSED))  # not an answer
        hub.emit(_event(unasked, EventType.DECISION_MADE))  # a decision of no request
        assert hub.screen("request", request.request_id) is not None
        assert hub.screen("request", choice.request_id) is not None
        hub.emit(_event(made, EventType.DECISION_MADE))
        assert hub.screen("request", choice.request_id) is None  # recorded
        hub.emit(_resolved(request.request_id))
        assert hub.screen("request", request.request_id) is None
        late = hub.submit("request", request.request_id, FORM)
        assert late.status == HTTPStatus.CONFLICT  # nothing is accepted for a recorded request

    asyncio.run(scenario())
    assert "None" in hub.index().body  # nothing is open


def test_a_request_presented_again_is_open_afresh() -> None:
    port = PageApprovalPort(ack_timeout_s=0)
    request = approval_request()

    async def scenario() -> tuple[int, int, str]:
        await port.present(request)
        first = port.hub.submit("request", request.request_id, FORM)
        await port.present(request)  # the engine refused the answer and shows the request again
        assert await port.answer(request.request_id, wait=False) is None
        second = port.hub.submit("request", request.request_id, {**FORM, "by": "bob"})
        again = await port.answer(request.request_id, wait=False)
        assert again is not None
        return first.status, second.status, again.by

    assert asyncio.run(scenario()) == (HTTPStatus.OK, HTTPStatus.OK, "bob")
