"""Several open requests: `/` lists them in presentation order, each answered on its own page (plan 0006 T7; AC38)."""

import asyncio
from http import HTTPStatus
from pathlib import Path

from helpers.engine_standin import SHA, approval_request, in_thread, input_request, until, wired

from eng_harness._html import Tag, Text, el, trusted
from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev
from eng_harness.pages import PageApprovalPort, Screen
from eng_harness.pages._answers import CHOICE
from eng_harness.pages._security import Subject
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
        assert w.answer(choice, **{CHOICE + "q": "b"}) == HTTPStatus.OK
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


def test_a_kind_without_a_builder_gets_a_refusal_screen(tmp_path: Path) -> None:
    request = approval_request("apr_promo", kind="PROMOTION")
    with wired(tmp_path, wait_timeout_s=0.3) as w:
        future = w.open(request)
        page = w.client.get("/request/apr_promo")
        assert page.status == HTTPStatus.OK
        assert "This request cannot be answered here" in page.body
        assert "PROMOTION" in page.body
        assert "<form" not in page.body
        assert "<button" not in page.body  # no form and no button
        assert w.client.get("/request/apr_none").status == HTTPStatus.NOT_FOUND
        refused = w.client.post("/answer/apr_promo", {"shown_sha256": SHA, "by": "ada", "decision": "approve"})
        assert refused.status >= HTTPStatus.BAD_REQUEST  # no form was offered, so no token exists: nothing answers
        assert future.result(5) is None  # the engine pauses at the wait timeout with no answer


def test_index_report_and_setup_hooks(tmp_path: Path) -> None:
    def setup(setup_id: str) -> Screen | None:
        body = [el(Tag.P, Text("setup page"))]
        return Screen(trusted("Setup"), Subject("setup", setup_id, "c" * 64), frozenset(), lambda _token: body)

    with wired(tmp_path) as w:
        index = w.client.get("/")
        assert 'href="/report"' in index.body
        assert "None" in index.body  # no open request
        assert "The report is not available yet." in w.client.get("/report").body
        assert w.client.get("/setup/setup_one").status == HTTPStatus.NOT_FOUND
    with wired(tmp_path / "hooks", report=lambda: "the report", setup=setup) as w:
        assert w.client.get("/report").body == "the report"
        assert "setup page" in w.client.get("/setup/setup_one").body
        assert (
            w.client.post("/setup/setup_one", {"csrf": "x"}).status == HTTPStatus.FORBIDDEN
        )  # the token binds the draft


def test_untrusted_title_is_escaped_and_labeled(tmp_path: Path) -> None:
    request = approval_request(title="<b>x</b> & more")
    with wired(tmp_path, wait_timeout_s=0.3) as w:
        future = w.open(request)
        body = w.client.get("/").body
        assert future.result(5) is None  # the engine pauses at the wait timeout with no answer
    assert "<b>x</b>" not in body
    assert "&lt;b&gt;x&lt;/b&gt; &amp; more" in body
    assert '<bdi dir="auto">' in body
    assert PageApprovalPort().hub.index().status == HTTPStatus.OK
