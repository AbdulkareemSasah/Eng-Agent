"""Step 5 of the edit cycle: the change-set request and its check (plan 0007 T8; spec 0007 AC24).

`attempts.change_set` is 2 in the synthetic basis of the stand. The runs end at the first approval request (the
responder returns `STOP`); what is asserted happened before it.
"""

from typing import Any

from pydantic import JsonValue

from eng_harness.engine import RunStatus
from eng_harness.ports import ApprovalRequest, InputRequest

from .conftest import ITEM_SECTION, STOP, Stand

UNKNOWN: dict[str, JsonValue] = {"id": "u1", "kind": "frame_section", "frames": ["FX"], "section": "C40"}


def _script(stand: Stand, answers: list[dict[str, JsonValue]]) -> Any:
    seen: list[str] = []

    def responder(_: Stand, shown: Any) -> Any:
        if isinstance(shown, ApprovalRequest):
            return STOP
        assert isinstance(shown, InputRequest)
        seen.append(shown.request_id)
        return stand.give(shown, {"change_set": answers[len(seen) - 1]})

    return responder


def test_invalid_change_set_asked_again(stand: Stand) -> None:
    """AC24: a data request; an answer that fails `ChangeSetDraft` is refused and shown again; an answer whose check
    is `FAIL` is asked again with the check named in the title; a passing one reaches the approval."""
    shape: dict[str, JsonValue] = {"items": [{**ITEM_SECTION, "bogus": 1}]}
    answers: list[dict[str, JsonValue]] = [shape, {"items": [UNKNOWN]}, {"items": [ITEM_SECTION]}]
    outcome = stand.play(stand.flow(), _script(stand, answers))
    assert outcome.status is RunStatus.PAUSED
    assert [a.kind for a in stand.approvals.presented] == ["change_set"]
    asked = [r for r in stand.inputs.presented if isinstance(r, InputRequest)]
    assert {r.kind for r in asked} == {"block"}
    assert all(r.fields_schema["x-eng-input"] == "data" for r in asked)
    ids = [r.request_id for r in asked]
    assert ids[0] == ids[1]  # the answer that fails the model: the same request is shown again
    assert len(set(ids)) == 2  # one request for each attempt: the answer that failed the check opened the second
    checks = stand.results("harness.change_set_check")
    assert [c["status"] for c in checks] == ["FAIL", "PASS"]
    assert [(i["code"], i["item_id"]) for i in checks[0]["issues"]] == [("UNKNOWN_FRAME", "u1")]
    assert [r.title for r in asked if r.request_id == ids[0]] == ["Change set"] * ids.count(ids[0])
    again = [r for r in asked if r.request_id == ids[-1]][-1]
    assert again.title.startswith("Change set: the check res_")  # the failed check is the evidence of the new request


def test_exhausting_the_attempts_escalates(stand: Stand) -> None:
    """AC24: when `attempts.change_set` runs out, the run escalates with `attempts_exhausted`."""
    answers: list[dict[str, JsonValue]] = [{"items": [UNKNOWN]}, {"items": [UNKNOWN]}]
    outcome = stand.play(stand.flow(), _script(stand, answers))
    assert outcome.status is RunStatus.NEEDS_ENGINEER
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "attempts_exhausted"
    assert [c["status"] for c in stand.results("harness.change_set_check")] == ["FAIL", "FAIL"]
