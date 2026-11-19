"""The decision points of the column workflow (spec 0013 section 4.8).

Purpose: four points with their option sets and state models, found by the discovery of spec 0005 section 4.2 over
`eng_harness.workflows` and listed in `decisions.lock.json`: the action for each reviewed column
(`column_design_member_action`, asked with `decide_many`), the engineer turn after a cycle, and the two results of
the Revit run (the map and the read-back). Names have no dot (spec 0005 AC1), so the spec's
`column_design.member_action` is `column_design_member_action`. States hold statuses, booleans, labels and
references only; no point holds a number. All four ask the engineer after their rules and never consult a model
or a language model (spec 0013 Q8).
Units: none. Errors: `DecisionDefinitionError` at import for an invalid definition (spec 0005 AC1, AC2).
"""

from enum import StrEnum

from eng_contract.refs import Ref
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict

from eng_harness.decisions.types import DecisionPolicy, Label, decision_point

__all__ = [
    "COLUMN_POLICY",
    "EngineerTurnPoint",
    "MapAction",
    "MapResultPoint",
    "MapState",
    "MemberAction",
    "MemberActionPoint",
    "MemberState",
    "ProposalState",
    "RevitReadbackAction",
    "RevitReadbackPoint",
    "RevitReadbackState",
    "TurnAction",
    "TurnState",
]

_STRICT = ConfigDict(frozen=True, extra="forbid")

COLUMN_POLICY = DecisionPolicy(model=False, llm=False, require_engineer=True)
"""Policy of the four points (spec 0013 4.8, Q8): the engineer decides after the rules; no model, no language model."""


class MemberAction(StrEnum):
    """Options of the per-column action."""

    KEEP = "keep"
    CHANGE_SECTION = "change_section"
    REFER_TO_ENGINEER = "refer_to_engineer"


class ProposalState(StrEnum):
    """The section proposal of a column: none, or the status of `harness.column_match/1` (spec 0013 4.4.4)."""

    NONE = "none"
    MATCHED = "matched"
    NO_SECTION_IN_MODEL = "no_section_in_model"
    AMBIGUOUS = "ambiguous"


class MemberState(BaseModel):
    """State of one column: its three review statuses, whether a check was not run, its proposal and references."""

    model_config = _STRICT

    status: VerdictStatus
    host_status: VerdictStatus
    code_status: VerdictStatus
    has_not_checked: bool
    proposal: ProposalState
    refs: tuple[Ref, ...]


class TurnAction(StrEnum):
    """Options of the engineer turn."""

    ACCEPT = "accept"
    REVISE = "revise"
    HAND_EDIT = "hand_edit"


class TurnState(BaseModel):
    """State of the engineer turn: the review and read-back statuses, the counts as labels and references."""

    model_config = _STRICT

    review_status: VerdictStatus
    readback_status: VerdictStatus
    counts: tuple[Label, ...]
    refs: tuple[Ref, ...]


class MapAction(StrEnum):
    """Options of the map result of the Revit run."""

    CONTINUE_MATCHED = "continue_matched"
    STOP = "stop"


class MapState(BaseModel):
    """State of the map result: which kinds of finding the frame-element map has and whether it is complete."""

    model_config = _STRICT

    has_ambiguous: bool
    has_unmatched_frames: bool
    has_conflicts: bool
    complete: bool


class RevitReadbackAction(StrEnum):
    """Options of the read-back result of the Revit run."""

    ACCEPT = "accept"
    ABANDON = "abandon"


class RevitReadbackState(BaseModel):
    """State of the Revit read-back result: its status and its issue codes as labels."""

    model_config = _STRICT

    status: VerdictStatus
    issues: tuple[Label, ...]


@decision_point(
    name="column_design_member_action",
    version=1,
    title="Action for a reviewed column",
    options=MemberAction,
    state=MemberState,
)
class MemberActionPoint: ...


@decision_point(
    name="column_design_engineer_turn",
    version=1,
    title="Engineer turn after the column review",
    options=TurnAction,
    state=TurnState,
)
class EngineerTurnPoint: ...


@decision_point(
    name="column_revit_map_result",
    version=1,
    title="Result of the frame and Revit element map",
    options=MapAction,
    state=MapState,
)
class MapResultPoint: ...


@decision_point(
    name="column_revit_readback_result",
    version=1,
    title="Read-back of the Revit column types",
    options=RevitReadbackAction,
    state=RevitReadbackState,
)
class RevitReadbackPoint: ...
