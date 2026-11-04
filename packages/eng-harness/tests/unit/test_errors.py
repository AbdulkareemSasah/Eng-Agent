"""Harness codes and error families (plan task T2; spec 0001 section 6, AC10)."""

import pytest
from eng_contract.errors import ErrorCode, ErrorDetail

from eng_harness import errors
from eng_harness.errors import (
    ApprovalRejected,
    ApprovalVoid,
    BlockRuleViolation,
    CalcRefused,
    DecisionInvalid,
    EngineStop,
    Escalation,
    HarnessCode,
    HostStateMismatch,
    JournalIntegrityError,
    ModelIntegrityError,
    NeedsReconciliation,
    NotImplementedGap,
    Pause,
    ReplayDivergence,
    RunLocked,
    RunRefused,
    StepError,
    ToolFailed,
)

STOPS = {
    Pause: HarnessCode.PAUSED,
    ReplayDivergence: HarnessCode.REPLAY_DIVERGENCE,
    NeedsReconciliation: HarnessCode.NEEDS_RECONCILIATION,
    HostStateMismatch: HarnessCode.HOST_STATE_MISMATCH,
    Escalation: HarnessCode.NEEDS_ENGINEER,
    BlockRuleViolation: HarnessCode.BLOCK_RULE_VIOLATION,
}
FIXED_EXCEPTIONS = {
    RunLocked: HarnessCode.RUN_LOCKED,
    JournalIntegrityError: HarnessCode.JOURNAL_INTEGRITY,
    ModelIntegrityError: HarnessCode.MODEL_INTEGRITY,
    DecisionInvalid: HarnessCode.DECISION_INVALID,
    ApprovalRejected: HarnessCode.APPROVAL_REJECTED,
    ApprovalVoid: HarnessCode.APPROVAL_VOID,
    NotImplementedGap: HarnessCode.NOT_IMPLEMENTED,
}


def test_engine_stop_is_not_exception() -> None:
    assert issubclass(EngineStop, BaseException)
    assert not issubclass(EngineStop, Exception)
    for cls in STOPS:
        assert issubclass(cls, EngineStop)
        assert not issubclass(cls, Exception)

    def swallow() -> None:
        try:
            raise Pause("awaiting approval")
        except Exception:  # noqa: BLE001  # B-101: the test shows this handler cannot catch a pause
            return

    with pytest.raises(Pause):
        swallow()


def test_step_errors_are_exceptions_not_stops() -> None:
    step_errors = (ToolFailed, ModelIntegrityError, DecisionInvalid, ApprovalRejected, ApprovalVoid)
    for cls in (*step_errors, NotImplementedGap, CalcRefused):
        assert issubclass(cls, StepError)
        assert issubclass(cls, Exception)
        assert not issubclass(cls, EngineStop)
    for cls in (RunRefused, RunLocked, JournalIntegrityError):
        assert issubclass(cls, Exception)
        assert not issubclass(cls, (EngineStop, StepError))


def test_codes_per_exception() -> None:
    for stop, code in STOPS.items():
        stopped = stop("message")
        assert (stopped.code, stopped.message, stopped.evidence) == (code, "message", ())
    for exc, code in FIXED_EXCEPTIONS.items():
        raised = exc("message")
        assert (raised.code, raised.message, raised.evidence) == (code, "message", ())
    assert {c.value for c in HarnessCode} == {
        "PAUSED", "REPLAY_DIVERGENCE", "NEEDS_RECONCILIATION", "HOST_STATE_MISMATCH", "NEEDS_ENGINEER",
        "BLOCK_RULE_VIOLATION", "BASIS_INCOMPLETE", "SERVER_CHECK_FAILED", "RUN_CLASS_MISMATCH", "RUN_LOCKED",
        "JOURNAL_INTEGRITY", "MODEL_INTEGRITY", "DECISION_INVALID", "APPROVAL_REJECTED", "APPROVAL_VOID",
        "NOT_IMPLEMENTED", "CALC_NOT_APPROVED", "CALC_WITHDRAWN",
    }  # fmt: skip


def test_selectable_codes_and_evidence() -> None:
    for code in (HarnessCode.BASIS_INCOMPLETE, HarnessCode.SERVER_CHECK_FAILED, HarnessCode.RUN_CLASS_MISMATCH):
        assert RunRefused(code, "refused", evidence=["r1#/a"]).code == code
    for code in (HarnessCode.CALC_NOT_APPROVED, HarnessCode.CALC_WITHDRAWN):
        assert CalcRefused(code, "calc").code == code
    assert RunRefused(HarnessCode.BASIS_INCOMPLETE, "x", evidence=["r1"]).evidence == ("r1",)
    with pytest.raises(ValueError, match="not allowed"):
        RunRefused(HarnessCode.PAUSED, "x")
    with pytest.raises(ValueError, match="not allowed"):
        CalcRefused(HarnessCode.RUN_LOCKED, "x")


def test_tool_failed_carries_contract_detail() -> None:
    detail = ErrorDetail(code=ErrorCode.CONFLICT, message="conflict", retryable=False)
    err = ToolFailed(detail)
    assert err.code is ErrorCode.CONFLICT
    assert err.detail == detail
    assert err.message == "conflict"


def test_module_exports() -> None:
    assert set(errors.__all__) >= {"HarnessCode", "EngineStop", "StepError", "RunRefused", "ToolFailed"}
