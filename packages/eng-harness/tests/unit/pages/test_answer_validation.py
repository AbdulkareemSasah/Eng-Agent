"""The checks of a posted answer: reasons, items, the engineer's name (plan 0006 T7; AC31, AC39)."""

import getpass
import os
from http import HTTPStatus
from pathlib import Path

import pytest
from helpers.engine_standin import SHA, approval_request, until, wired

from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev
from eng_harness.pages import PageApprovalPort
from eng_harness.pages._answers import (
    NAME_MAX,
    REASON,
    REASON_MAX,
    REJECT,
    AnswerError,
    ApprovalSubmission,
    engineer_name,
    parse,
)

REQUEST = approval_request(items=("i1", "i2"))
BASE = {"shown_sha256": SHA, "by": "ada"}
LONG = "x" * (REASON_MAX + 1)
EDGE = "x" * REASON_MAX

REFUSED = [
    ({"decision": "maybe"}, "choose approve or reject"),
    ({}, "choose approve or reject"),
    ({"decision": "reject"}, "a rejection needs a reason of 1 to 500 characters"),
    ({"decision": "reject", "reason": "  \t "}, "a rejection needs a reason of 1 to 500 characters"),
    ({"decision": "reject", "reason": LONG}, "a reason has at most 500 characters"),
    ({"decision": "approve", "reason": LONG}, "a reason has at most 500 characters"),
    ({"decision": "approve", REJECT + "i1": "on"}, "item i1 is rejected without a reason of its own"),
    (
        {"decision": "approve", REJECT + "i2": "on", REASON + "i2": "  "},
        "item i2 is rejected without a reason of its own",
    ),
    ({"decision": "approve", REASON + "i1": LONG}, "a reason has at most 500 characters"),
    (
        {"decision": "approve", REJECT + "zz": "on", REASON + "zz": "x"},
        "the form names an item that is not an item of this request",
    ),
    ({"decision": "approve", REASON + "zz": "x"}, "the form names an item that is not an item of this request"),
    (
        {"decision": "approve", REJECT + "i1": "on", REJECT + "i2": "on", REASON + "i1": "a", REASON + "i2": "b"},
        "every item is rejected: use reject",
    ),
]  # fmt: skip


def test_reasons_and_items(tmp_path: Path) -> None:
    for fields, message in REFUSED:
        with pytest.raises(AnswerError) as refused:
            parse(REQUEST, BASE | fields)
        assert str(refused.value) == message, fields
        assert refused.value.status == HTTPStatus.BAD_REQUEST
    accepted = parse(REQUEST, BASE | {"decision": "approve", REJECT + "i1": "on", REASON + "i1": "  thin  "})
    assert isinstance(accepted, ApprovalSubmission)
    assert (accepted.rejected_items, dict(accepted.item_reasons)) == (("i1",), {"i1": "thin"})
    edge = parse(REQUEST, BASE | {"decision": "reject", "reason": f" {EDGE} ", REASON + "i2": EDGE})
    assert isinstance(edge, ApprovalSubmission)
    assert (edge.reason, dict(edge.item_reasons)) == (EDGE, {"i2": EDGE})  # 500 characters after trimming are allowed

    with wired(tmp_path) as w:  # a refusal re-renders the page with the message and records nothing
        future = w.open(REQUEST)
        for fields, _ in REFUSED[2:4]:
            assert w.answer(REQUEST, **fields) == HTTPStatus.BAD_REQUEST
        body = w.client.post(
            "/answer/apr_one",
            {"csrf": w.client.token("/request/apr_one"), "shown_sha256": SHA, "by": "ada", "decision": "reject"},
        ).body
        assert "a rejection needs a reason of 1 to 500 characters" in body
        assert 'href="/request/apr_one"' in body  # the request is shown again
        assert not future.done()  # nothing was accepted: the engine still waits
        assert w.answer(REQUEST, decision="reject", reason="no") == HTTPStatus.OK
        assert future.result(timeout=5) is not None
    resolved = [
        e.payload for e in JournalReader(w.engine.run_dir).events() if isinstance(e.payload, ev.ApprovalResolved)
    ]
    assert [r.reason for r in resolved] == ["no"]


def test_name_rules_and_no_os_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse() -> str:
        raise AssertionError("the operating system account was asked")

    monkeypatch.setattr(getpass, "getuser", refuse)
    monkeypatch.setattr(os, "getlogin", refuse)
    assert engineer_name("  Ada  ") == "Ada"
    assert engineer_name("a") == "a"
    assert engineer_name("مهندس علي") == "مهندس علي"
    assert engineer_name("n" * NAME_MAX) == "n" * NAME_MAX
    for bad in ["", "   ", "n" * (NAME_MAX + 1), "a\x00b", "a\nb", "tab\there", "\x1b[31m"]:
        with pytest.raises(AnswerError, match="the name has 1 to 100 characters"):
            engineer_name(bad)
    with pytest.raises(AnswerError):  # no name on the form: nothing falls back to the account
        parse(REQUEST, {"shown_sha256": SHA, "decision": "approve"})

    assert PageApprovalPort().hub.engineer is None
    assert PageApprovalPort(engineer="Ada").hub.engineer == "Ada"  # `[engine] engineer`
    with wired(tmp_path, engineer="Ada") as w:
        future = w.open(REQUEST)
        assert w.answer(REQUEST, decision="approve", by="Grace") == HTTPStatus.OK
        assert future.result(timeout=5) is not None
        until(lambda: w.approvals.hub.engineer == "Grace")
    assert w.approvals.hub.engineer == "Grace"  # remembered for the session
