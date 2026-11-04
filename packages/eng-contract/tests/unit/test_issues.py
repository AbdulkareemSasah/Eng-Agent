"""ModelIssue, CheckModelSummary (plan T10; spec 4.9.2, AC45)."""

from typing import Any

import pytest
from pydantic import ValidationError

from eng_contract.issues import CheckModelSummary, ModelIssue, Severity

_SUBJECT = {"kind": "model", "id": "m"}


def _issue(**over: Any) -> dict[str, Any]:
    return {"severity": "error", "code": "BAD_THING", "subject": _SUBJECT, "message": "m"} | over


def test_model_issue() -> None:
    issue = ModelIssue.model_validate(_issue(severity="warning", code="DUP_NODE"))
    assert issue.severity is Severity.WARNING
    assert ModelIssue.model_validate(issue.model_dump(mode="json")) == issue
    assert {s.value for s in Severity} == {"error", "warning", "info"}


@pytest.mark.parametrize(
    "over",
    [
        {"code": "a"},
        {"code": "lower"},
        {"code": "A"},
        {"code": "A" * 65},
        {"message": ""},
        {"message": "x" * 2001},
        {"severity": "fatal"},
        {"extra": 1},
    ],
)
def test_model_issue_rejects(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ModelIssue.model_validate(_issue(**over))


def test_model_issue_code_boundaries() -> None:
    for code in ("AB", "A" + "B" * 63):
        assert ModelIssue.model_validate(_issue(code=code)).code == code


def test_summary() -> None:
    assert CheckModelSummary(errors=0, warnings=2, infos=1, clean=True).clean is True
    assert CheckModelSummary(errors=3, warnings=0, infos=0, clean=False).errors == 3
    for bad in (
        {"errors": 0, "warnings": 0, "infos": 0, "clean": False},
        {"errors": 1, "warnings": 0, "infos": 0, "clean": True},
        {"errors": -1, "warnings": 0, "infos": 0, "clean": False},
        {"errors": 0, "warnings": -1, "infos": 0, "clean": True},
        {"errors": 0, "warnings": 0, "infos": -1, "clean": True},
        {"errors": 0, "warnings": 0, "clean": True},
    ):
        with pytest.raises(ValidationError):
            CheckModelSummary.model_validate(bad)
