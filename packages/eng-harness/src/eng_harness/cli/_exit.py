"""Process exit codes (spec 0006 section 4.2.3, AC3)."""

import enum


class ExitCode(enum.IntEnum):
    """The exit code table of the command line."""

    OK = 0
    RUN_FAILED = 1
    USAGE = 2
    REFUSED = 3
    RUN_LOCKED = 4
    JOURNAL_INTEGRITY = 5
    NOT_FOUND = 6
    AWAITING_ENGINEER = 10
    NEEDS_ENGINEER = 11
    STOPPED = 12
    INTERNAL = 70
    INTERRUPTED = 130


class Outcome(enum.Enum):
    """What a command ended with; the engine's own types are mapped onto these by the run wiring (plan T14)."""

    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED_AWAITING_APPROVAL = "paused_awaiting_approval"
    PAUSED_AWAITING_INPUT = "paused_awaiting_input"
    PAUSED_STOP_REQUESTED = "paused_stop_requested"
    BASIS_PENDING = "basis_pending"
    NEEDS_ENGINEER = "needs_engineer"
    RUN_REFUSED = "run_refused"
    RUN_LOCKED = "run_locked"
    JOURNAL_INTEGRITY = "journal_integrity"
    NOT_FOUND = "not_found"
    USAGE = "usage"
    UNEXPECTED = "unexpected"
    SECOND_INTERRUPT = "second_interrupt"


_BY_OUTCOME = {
    Outcome.COMPLETED: ExitCode.OK,
    Outcome.FAILED: ExitCode.RUN_FAILED,
    Outcome.PAUSED_AWAITING_APPROVAL: ExitCode.AWAITING_ENGINEER,
    Outcome.PAUSED_AWAITING_INPUT: ExitCode.AWAITING_ENGINEER,
    Outcome.PAUSED_STOP_REQUESTED: ExitCode.STOPPED,
    Outcome.BASIS_PENDING: ExitCode.AWAITING_ENGINEER,
    Outcome.NEEDS_ENGINEER: ExitCode.NEEDS_ENGINEER,
    Outcome.RUN_REFUSED: ExitCode.REFUSED,
    Outcome.RUN_LOCKED: ExitCode.RUN_LOCKED,
    Outcome.JOURNAL_INTEGRITY: ExitCode.JOURNAL_INTEGRITY,
    Outcome.NOT_FOUND: ExitCode.NOT_FOUND,
    Outcome.USAGE: ExitCode.USAGE,
    Outcome.UNEXPECTED: ExitCode.INTERNAL,
    Outcome.SECOND_INTERRUPT: ExitCode.INTERRUPTED,
}

_BY_ERROR_CODE = {
    "INVALID_ARGUMENT": ExitCode.USAGE,
    "BASIS_INCOMPLETE": ExitCode.REFUSED,
    "SERVER_CHECK_FAILED": ExitCode.REFUSED,
    "CALC_NOT_APPROVED": ExitCode.REFUSED,
    "CALC_WITHDRAWN": ExitCode.REFUSED,
    "RUN_LOCKED": ExitCode.RUN_LOCKED,
    "JOURNAL_INTEGRITY": ExitCode.JOURNAL_INTEGRITY,
    "REF_NOT_FOUND": ExitCode.NOT_FOUND,
}


def exit_code_for(outcome: Outcome) -> ExitCode:
    """Return the exit code of an outcome."""
    return _BY_OUTCOME[outcome]


def exit_code_for_error(code: str) -> ExitCode:
    """Return the exit code of a contract error code (spec section 6); an unlisted code is `INTERNAL`."""
    return _BY_ERROR_CODE.get(code, ExitCode.INTERNAL)
