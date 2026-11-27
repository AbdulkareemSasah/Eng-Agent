"""The decision points of the edit cycle (spec 0007 section 4.6: D-2, D-3 and D-6).

Purpose: three points with their option sets and state models, found by the discovery of spec 0005 section 4.2 over
`eng_harness.workflows` and listed in `decisions.lock.json`. State models carry statuses, booleans, labels and
references only; no point holds a number (thresholds are in the calcs and read from the basis). D-2 and D-3 ask the
engineer only after their rules (`require_engineer`) and never consult a model or an LLM; D-6 has no rule.
Units: none. Errors: `DecisionDefinitionError` at import for an invalid definition (spec 0005 AC1, AC2).
"""

from enum import StrEnum

from eng_contract.refs import Ref
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict

from eng_harness.decisions.types import DecisionPolicy, Label, decision_point

__all__ = [
    "ANALYSIS_POLICY",
    "READBACK_POLICY",
    "TURN_POLICY",
    "AnalysisAction",
    "AnalysisMessagesPoint",
    "AnalysisState",
    "EngineerTurnPoint",
    "ReadbackAction",
    "ReadbackReason",
    "ReadbackResultPoint",
    "ReadbackState",
    "TurnAction",
    "TurnState",
]

_STRICT = ConfigDict(frozen=True, extra="forbid")

READBACK_POLICY = DecisionPolicy(model=False, llm=False, require_engineer=True)
"""D-2 policy (spec 0007 4.6): the engineer decides after the rules; no model, no LLM."""
ANALYSIS_POLICY = READBACK_POLICY
"""D-3 policy: the same as D-2 (spec 0007 4.6)."""
TURN_POLICY = DecisionPolicy(require_engineer=True)
"""D-6 policy (spec 0007 4.6): the engineer always decides."""


class ReadbackAction(StrEnum):
    """Options of D-2."""

    CONTINUE = "continue"
    RESTORE_PREVIOUS = "restore_previous"
    STOP_CYCLE = "stop_cycle"


class ReadbackReason(StrEnum):
    """Why D-2 is asked: a read-back that is not clean, or a model that changed during the apply (spec 0007 4.5.1)."""

    READBACK = "readback"
    MODEL_CHANGED_DURING_APPLY = "model_changed_during_apply"
    CHECK_MODEL_FAILED = "check_model_failed"


class ReadbackState(BaseModel):
    """State of D-2: the read-back status, which kinds of finding it has, the reason and the evidence references."""

    model_config = _STRICT

    status: VerdictStatus
    has_mismatch: bool
    has_missing: bool
    has_unexpected: bool
    has_not_read: bool
    reason: ReadbackReason
    refs: tuple[Ref, ...]


class AnalysisAction(StrEnum):
    """Options of D-3."""

    CONTINUE = "continue"
    STOP_CYCLE = "stop_cycle"


class AnalysisState(BaseModel):
    """State of D-3: the message flags of the analysis summary, the drift status (spec 0007 4.4.4) and references."""

    model_config = _STRICT

    has_errors: bool
    has_unclassified: bool
    drift_status: VerdictStatus
    refs: tuple[Ref, ...]


class TurnAction(StrEnum):
    """Options of D-6."""

    ACCEPT = "accept"
    MORE_EDITS = "more_edits"
    HAND_EDIT = "hand_edit"


class TurnState(BaseModel):
    """State of D-6: the three statuses, the counts as labels and references to the summaries and the difference."""

    model_config = _STRICT

    readback_status: VerdictStatus
    analysis_status: VerdictStatus
    design_status: VerdictStatus
    counts: tuple[Label, ...]
    refs: tuple[Ref, ...]


@decision_point(
    name="edit_cycle_readback_result",
    version=2,
    title="Read-back result of the applied change set",
    options=ReadbackAction,
    state=ReadbackState,
)
class ReadbackResultPoint: ...


@decision_point(
    name="edit_cycle_analysis_messages",
    version=1,
    title="Analysis messages of the host",
    options=AnalysisAction,
    state=AnalysisState,
)
class AnalysisMessagesPoint: ...


@decision_point(
    name="edit_cycle_engineer_turn",
    version=1,
    title="Engineer turn after the cycle",
    options=TurnAction,
    state=TurnState,
)
class EngineerTurnPoint: ...
