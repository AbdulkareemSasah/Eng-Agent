"""Exceptions of the core framework (spec 0001 sections 4.1 and 6).

Purpose: typed errors. Only `CheckNotUsable` maps to a contract error code; the others signal programming or data
mistakes and are not `ContractError` (spec section 6).
"""

from eng_contract.errors import ContractError, ErrorCode

__all__ = [
    "ApprovalsFileError",
    "CheckDefinitionError",
    "CheckNotUsable",
    "NotImplementedGap",
    "TraceValueError",
    "VerificationDataError",
]


class CheckDefinitionError(Exception):
    """A check, its metadata, inputs, trace use, overlay or import is defined wrongly (a programming error)."""


class NotImplementedGap(Exception):  # noqa: N818  # B-256: name fixed by spec 4.1
    """The explicit gap of an unimplemented clause part; the runner turns it into a `NEEDS_ENGINEER` verdict."""

    def __init__(self, gap_id: str, clause: str, reason: str) -> None:
        """Keep the declared gap id, the clause and the reason."""
        self.gap_id = gap_id
        self.clause = clause
        self.reason = reason
        super().__init__(f"{gap_id} ({clause}): {reason}")


class TraceValueError(Exception):
    """A value recorded in a trace is not a finite number or otherwise unusable (spec AC8)."""


class CheckNotUsable(ContractError):  # noqa: N818  # B-256: name fixed by spec 4.1
    """The check is not usable in the requested mode, or is withdrawn; code `INVALID_ARGUMENT` (spec 11 Q1)."""

    def __init__(self, check_id: str, hint: str) -> None:
        """Build the error with `field` `check_id` and a `hint` naming the lifecycle state."""
        super().__init__(
            ErrorCode.INVALID_ARGUMENT, f"check {check_id!r} is not usable in this mode", field="check_id", hint=hint
        )


class ApprovalsFileError(Exception):
    """An `approvals.yaml` file is invalid."""


class VerificationDataError(Exception):
    """A verification case file is invalid."""
