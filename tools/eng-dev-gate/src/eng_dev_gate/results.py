"""Check statuses and process exit codes (spec 4.2, AC1)."""

from __future__ import annotations

from enum import IntEnum, StrEnum


class ExitCode(IntEnum):
    """Process exit codes of every command (spec AC1)."""

    OK = 0  # pass, skipped, or awaiting owner
    FAILED = 1  # a rule failed
    USAGE = 2  # usage or configuration error
    ENVIRONMENT = 3  # environment or tool error


class Status(StrEnum):
    """Status of a check: fail if any error, else awaiting-owner if any awaiting finding, else pass."""

    PASS = "pass"  # noqa: S105  # B-030: a status name, not a password
    FAIL = "fail"
    AWAITING_OWNER = "awaiting-owner"
    SKIPPED = "skipped"


class GateError(Exception):
    """Base of the typed errors that map to an exit code."""

    exit_code: ExitCode = ExitCode.ENVIRONMENT


class UsageError(GateError):
    """Bad option, malformed configuration or unreadable input (exit 2)."""

    exit_code = ExitCode.USAGE


class EnvironmentFaultError(GateError):
    """A required tool is missing, crashed or timed out (exit 3)."""

    exit_code = ExitCode.ENVIRONMENT


def exit_code_for(status: Status) -> ExitCode:
    """Map a check status to the exit code: only ``fail`` is non-zero.

    Args:
        status: the status of the finished command.

    Returns:
        ``ExitCode.FAILED`` for ``fail``, else ``ExitCode.OK``.
    """
    return ExitCode.FAILED if status is Status.FAIL else ExitCode.OK
