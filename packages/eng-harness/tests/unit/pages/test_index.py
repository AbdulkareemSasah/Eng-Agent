"""Several open requests: `/` lists them in presentation order, each answered on its own page (plan 0006 T7; AC38)."""

import asyncio
from http import HTTPStatus
from pathlib import Path

from helpers.engine_standin import approval_request, in_thread, input_request, until, wired

from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalAnswer, ApprovalRequest, InputAnswer, InputRequest


def test_multiple_open_requests(tmp_path: Path) -> None:
    requests = [approval_request(f"apr_{n}", title=f"Request {n}") for n in (3, 1, 2)]  # not in id order
    choice = input_request()
    every: list[ApprovalRequest | InputRequest] = [*requests, choice]
    with wired(tmp_path) as w:

        async def engine() -> tuple[list[ApprovalAnswer | None], InputAnswer | None]:
            approved, asked = await asyncio.gather(
                asyncio.gather(*(w.engine.approve(w.approvals, r) for r in requests)), w.engine.ask(w.inputs, choice)
            )
            return list(approved), asked

        future = in_thread(engine())
        until(lambda: all(w.approvals.hub.screen("request", r.request_id) for r in every))
        body = w.client.get("/").body
        order = [body.index(f"/request/{r.request_id}") for r in every]
        assert order == sorted(order)  # the order the engine presented them in, not the order of their ids
        assert all(f"Request {n}" in body for n in (3, 1, 2))

        middle = requests[1]
        assert w.answer(middle, decision="approve") == HTTPStatus.OK
        body = w.client.get("/").body
        assert middle.request_id not in body  # an answered request leaves the list
        assert all(r.request_id in body for r in (every[0], every[2], every[3]))
        for r in [requests[0], requests[2]]:
            page = w.client.get(f"/request/{r.request_id}")
            assert page.status == HTTPStatus.OK
            assert r.title in page.body  # each request has its own page
            assert w.answer(r, decision="reject", reason=f"no {r.title}") == HTTPStatus.OK
        assert w.answer(choice, **{"choice:q": "b"}) == HTTPStatus.OK
        approved, asked = future.result(timeout=5)
    assert [a.request_id for a in approved if a is not None] == [r.request_id for r in requests]
    assert asked is not None
    assert dict(asked.choices or {}) == {"q": "b"}
    journal = [
        e.payload.request_id
        for e in JournalReader(w.engine.run_dir).events()
        if isinstance(e.payload, ev.ApprovalResolved | ev.InputProvided)
    ]
    assert journal == [middle.request_id, requests[0].request_id, requests[2].request_id, choice.request_id]
