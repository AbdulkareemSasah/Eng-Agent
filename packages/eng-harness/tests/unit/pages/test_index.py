"""Several open requests: `/` lists them in presentation order, each answered on its own page (plan 0006 T7; AC38)."""

import asyncio
from http import HTTPStatus
from pathlib import Path

from helpers.engine_standin import approval_request, in_thread, input_request, until, wired

from eng_harness.journal import EventType, JournalReader
from eng_harness.journal import _events as ev


def test_multiple_open_requests(tmp_path: Path) -> None:
    requests = [approval_request(f"apr_{n}", title=f"Request {n}") for n in (3, 1, 2)]  # not in id order
    choice = input_request()
    with wired(tmp_path) as w:

        async def engine() -> list[object]:
            return await asyncio.gather(
                *(w.engine.approve(w.approvals, r) for r in requests), w.engine.ask(w.inputs, choice)
            )

        future = in_thread(engine())
        until(lambda: all(w.approvals.hub.screen("request", r.request_id) for r in [*requests, choice]))
        body = w.client.get("/").body
        order = [body.index(f"/request/{r.request_id}") for r in [*requests, choice]]
        assert order == sorted(order)  # the order the engine presented them in, not the order of their ids
        assert all(f"Request {n}" in body for n in (3, 1, 2))

        middle = requests[1]
        assert w.answer(middle, decision="approve") == HTTPStatus.OK
        body = w.client.get("/").body
        assert middle.request_id not in body  # an answered request leaves the list
        assert all(r.request_id in body for r in [requests[0], requests[2], choice])
        for r in [requests[0], requests[2]]:
            page = w.client.get(f"/request/{r.request_id}")
            assert page.status == HTTPStatus.OK
            assert r.title in page.body  # each request has its own page
            assert w.answer(r, decision="reject", reason=f"no {r.title}") == HTTPStatus.OK
        assert w.answer(choice, **{"choice:q": "b"}) == HTTPStatus.OK
        answers = future.result(timeout=5)
    assert [getattr(a, "request_id", None) for a in answers] == [r.request_id for r in [*requests, choice]]
    assert dict(answers[3].choices) == {"q": "b"}
    events = [
        e
        for e in JournalReader(w.engine.run_dir).events()
        if e.type in (EventType.APPROVAL_RESOLVED, EventType.INPUT_PROVIDED)
    ]
    assert [e.payload.request_id for e in events] == [
        middle.request_id,
        requests[0].request_id,
        requests[2].request_id,
        choice.request_id,
    ]
    assert isinstance(events[-1].payload, ev.InputProvided)
