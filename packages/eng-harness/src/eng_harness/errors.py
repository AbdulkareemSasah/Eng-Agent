"""Harness codes and error families (spec 0001 section 6).

Purpose: `HarnessCode` names engine conditions that are not contract error codes. `EngineStop` (a `BaseException`, so
block code cannot swallow it with `except Exception`, AC10) and `StepError` (an `Exception`) carry `code`, `message`
and optional `evidence` (reference strings). No units are involved.
Errors: a code outside the allowed set of `RunRefused` or `CalcRefused` raises `ValueError`.
"""

# ruff: noqa: N818  # B-101: exception names are fixed by spec 0001 section 6

from collections.abc import Sequence
from enum import StrEnum

from eng_contract.errors import ErrorCode, ErrorDetail

__all__ = [
    "ApprovalRejected",
    "ApprovalVoid",
    "BlockRuleViolation",
    "CalcRefused",
    "DecisionInvalid",
    "EngineStop",
    "Escalation",
    "HarnessCode",
    "HostStateMismatch",
    "JournalIntegrityError",
    "ModelIntegrityError",
    "NeedsReconciliation",
    "NotImplementedGap",
    "Pause",
    "ReplayDivergence",
    "RunLocked",
    "RunRefused",
    "StepError",
    "ToolFailed",
]


class HarnessCode(StrEnum):
    """Engine conditions that are not contract error codes (spec 0001 section 6)."""

    PAUSED = "PAUSED"
    REPLAY_DIVERGENCE = "REPLAY_DIVERGENCE"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
    HOST_STATE_MISMATCH = "HOST_STATE_MISMATCH"
    NEEDS_ENGINEER = "NEEDS_ENGINEER"
    BLOCK_RULE_VIOLATION = "BLOCK_RULE_VIOLATION"
    BASIS_INCOMPLETE = "BASIS_INCOMPLETE"
    SERVER_CHECK_FAILED = "SERVER_CHECK_FAILED"
    RUN_CLASS_MISMATCH = "RUN_CLASS_MISMATCH"
    RUN_LOCKED = "RUN_LOCKED"
    JOURNAL_INTEGRITY = "JOURNAL_INTEGRITY"
    MODEL_INTEGRITY = "MODEL_INTEGRITY"
    DECISION_INVALID = "DECISION_INVALID"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_VOID = "APPROVAL_VOID"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    CALC_NOT_APPROVED = "CALC_NOT_APPROVED"
    CALC_WITHDRAWN = "CALC_WITHDRAWN"


class _Fields:
    """Shared fields of every harness exception: `code`, `message`, `evidence`."""

    code: HarnessCode | ErrorCode
    message: str
    evidence: tuple[str, ...]

    def _set(self, code: HarnessCode | ErrorCode, message: str, evidence: Sequence[str]) -> None:
        self.code = code
        self.message = message
        self.evidence = tuple(evidence)

    def _pick(self, code: HarnessCode, allowed: tuple[HarnessCode, ...]) -> HarnessCode:
        """Return `code` when allowed, else raise `ValueError`."""
        if code not in allowed:
            raise ValueError(f"code {code} is not allowed for {type(self).__name__}")
        return code


class EngineStop(_Fields, BaseException):
    """Base of the stops that must propagate to the engine; derives from `BaseException` (AC10)."""

    _CODE: HarnessCode

    def __init__(self, message: str, *, evidence: Sequence[str] = ()) -> None:
        """Build the stop with the class's fixed code."""
        BaseException.__init__(self, message)
        self._set(self._CODE, message, evidence)


class Pause(EngineStop):
    """Awaiting approval, input or a stop request."""

    _CODE = HarnessCode.PAUSED


class ReplayDivergence(EngineStop):
    """Replay differs from the journal (spec 4.5.2)."""

    _CODE = HarnessCode.REPLAY_DIVERGENCE


class NeedsReconciliation(EngineStop):
    """A write was in flight at a crash (spec 4.5.3)."""

    _CODE = HarnessCode.NEEDS_RECONCILIATION


class HostStateMismatch(EngineStop):
    """The host model differs from the journaled state (spec 4.5.4)."""

    _CODE = HarnessCode.HOST_STATE_MISMATCH


class Escalation(EngineStop):
    """The run needs an engineer: escalation, exhausted attempts, units mismatch, unhandled error."""

    _CODE = HarnessCode.NEEDS_ENGINEER


class BlockRuleViolation(EngineStop):
    """Block code broke a rule of spec 4.3 or 4.9."""

    _CODE = HarnessCode.BLOCK_RULE_VIOLATION


class _Plain(_Fields, Exception):
    """Exception with a fixed harness code."""

    _CODE: HarnessCode

    def __init__(self, message: str, *, evidence: Sequence[str] = ()) -> None:
        """Build the exception with the class's fixed code."""
        Exception.__init__(self, message)
        self._set(self._CODE, message, evidence)


class StepError(_Plain):
    """Base of failures of one step; leaving the root block it is journaled `step_failed` (spec 6)."""


class RunLocked(_Plain):
    """The run is locked by another engine (spec 4.4.4)."""

    _CODE = HarnessCode.RUN_LOCKED


class JournalIntegrityError(_Plain):
    """The journal's hash chain or schema is broken (spec 4.4.1)."""

    _CODE = HarnessCode.JOURNAL_INTEGRITY


class ModelIntegrityError(StepError):
    """Invariant 1 broken."""

    _CODE = HarnessCode.MODEL_INTEGRITY


class DecisionInvalid(StepError):
    """Invariant 4 broken."""

    _CODE = HarnessCode.DECISION_INVALID


class ApprovalRejected(StepError):
    """An inserted approval was rejected (spec 4.7)."""

    _CODE = HarnessCode.APPROVAL_REJECTED


class ApprovalVoid(StepError):
    """An approval no longer applies (spec 4.9)."""

    _CODE = HarnessCode.APPROVAL_VOID


class NotImplementedGap(StepError):
    """A known gap (E-G1)."""

    _CODE = HarnessCode.NOT_IMPLEMENTED


class RunRefused(Exception, _Fields):
    """A run was refused before `run_started`, or at resume before any live step."""

    _ALLOWED = (HarnessCode.BASIS_INCOMPLETE, HarnessCode.SERVER_CHECK_FAILED, HarnessCode.RUN_CLASS_MISMATCH)

    def __init__(self, code: HarnessCode, message: str, *, evidence: Sequence[str] = ()) -> None:
        """Raises:
        ValueError: `code` is not `BASIS_INCOMPLETE`, `SERVER_CHECK_FAILED` or `RUN_CLASS_MISMATCH`.
        """
        Exception.__init__(self, message)
        self._set(self._pick(code, self._ALLOWED), message, evidence)


class CalcRefused(StepError):
    """The CalcPort refused a calc that is not approved (production run) or is withdrawn (spec 0003 4.5)."""

    _ALLOWED = (HarnessCode.CALC_NOT_APPROVED, HarnessCode.CALC_WITHDRAWN)

    def __init__(self, code: HarnessCode, message: str, *, evidence: Sequence[str] = ()) -> None:
        """Raises:
        ValueError: `code` is not `CALC_NOT_APPROVED` or `CALC_WITHDRAWN`.
        """
        Exception.__init__(self, message)
        self._set(self._pick(code, self._ALLOWED), message, evidence)


class ToolFailed(StepError):
    """A failure envelope; `code` is the contract `ErrorDetail.code`."""

    def __init__(self, detail: ErrorDetail, *, evidence: Sequence[str] = ()) -> None:
        """Keep the contract detail in `.detail`."""
        Exception.__init__(self, detail.message)
        self.detail = detail
        self._set(detail.code, detail.message, evidence)
