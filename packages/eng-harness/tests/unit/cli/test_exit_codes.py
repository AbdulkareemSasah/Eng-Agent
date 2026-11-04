"""Exit codes (spec 0006 AC3, section 4.2.3)."""

import pytest

from eng_harness.cli import ExitCode
from eng_harness.cli._exit import Outcome, exit_code_for, exit_code_for_error


def test_table_values() -> None:
    assert {c.name: int(c) for c in ExitCode} == {
        "OK": 0, "RUN_FAILED": 1, "USAGE": 2, "REFUSED": 3, "RUN_LOCKED": 4, "JOURNAL_INTEGRITY": 5,
        "NOT_FOUND": 6, "AWAITING_ENGINEER": 10, "NEEDS_ENGINEER": 11, "STOPPED": 12, "INTERNAL": 70,
        "INTERRUPTED": 130,
    }


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (Outcome.COMPLETED, 0),
        (Outcome.FAILED, 1),
        (Outcome.PAUSED_AWAITING_APPROVAL, 10),
        (Outcome.PAUSED_AWAITING_INPUT, 10),
        (Outcome.BASIS_PENDING, 10),
        (Outcome.NEEDS_ENGINEER, 11),
        (Outcome.PAUSED_STOP_REQUESTED, 12),
        (Outcome.RUN_REFUSED, 3),
        (Outcome.RUN_LOCKED, 4),
        (Outcome.JOURNAL_INTEGRITY, 5),
        (Outcome.NOT_FOUND, 6),
        (Outcome.USAGE, 2),
        (Outcome.UNEXPECTED, 70),
        (Outcome.SECOND_INTERRUPT, 130),
    ],
)
def test_outcome_mapping(outcome: Outcome, code: int) -> None:
    assert exit_code_for(outcome) == code


def test_every_outcome_is_mapped() -> None:
    assert all(isinstance(exit_code_for(o), ExitCode) for o in Outcome)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        ("INVALID_ARGUMENT", 2),
        ("BASIS_INCOMPLETE", 3),
        ("SERVER_CHECK_FAILED", 3),
        ("CALC_NOT_APPROVED", 3),
        ("CALC_WITHDRAWN", 3),
        ("RUN_LOCKED", 4),
        ("JOURNAL_INTEGRITY", 5),
        ("REF_NOT_FOUND", 6),
    ],
)
def test_error_codes(error: str, code: int) -> None:
    assert exit_code_for_error(error) == code


def test_unknown_error_code_is_internal() -> None:
    assert exit_code_for_error("SOMETHING_ELSE") == ExitCode.INTERNAL
