"""The decision points of the isolated footing workflow (spec 0010 section 4.5).

Purpose: `footing_fix_strategy` and `footing_review`, two points with their option sets and state models, found by
the discovery of spec 0005 section 4.2 over `eng_harness.workflows` and listed in `decisions.lock.json`. State
models carry statuses, booleans, labels and references only; no point holds a number (Q4): the sizes and the bounds
are calc results, and the state says only which family fails and whether a bound is reached. `footing_fix_strategy`
runs the rules of `rules/footing.py` first, then the decision model in shadow mode (its answer is only a suggestion
on the engineer screen) and never a language model; `footing_review` is always the engineer's.
Units: none. Errors: `DecisionDefinitionError` at import for an invalid definition (spec 0005 AC1, AC2).
"""

from enum import StrEnum

from eng_contract.refs import Ref
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict

from eng_harness.decisions.types import DecisionPolicy, Label, decision_point

__all__ = [
    "FIX_STRATEGY_POLICY",
    "REVIEW_POLICY",
    "FootingAction",
    "FootingFailureState",
    "FootingFixStrategyPoint",
    "FootingReviewAction",
    "FootingReviewPoint",
    "FootingReviewState",
]

_STRICT = ConfigDict(frozen=True, extra="forbid")

FIX_STRATEGY_POLICY = DecisionPolicy(model=True, llm=False)
"""Policy of `footing_fix_strategy` (spec 0010 4.5): the decision model on, the language model off, the defaults of
12 section 3 otherwise, so the shadow mode stays on (no release exists in v1, spec 0005 4.3)."""
REVIEW_POLICY = DecisionPolicy(require_engineer=True)
"""Policy of `footing_review` (spec 0010 4.5): the engineer always decides."""


class FootingAction(StrEnum):
    """Options of `footing_fix_strategy`; `reduce_bar_spacing` is the fifth option added by spec 0010 (Q5, C1)."""

    ENLARGE_PLAN = "enlarge_plan"
    INCREASE_DEPTH = "increase_depth"
    REDUCE_BAR_SPACING = "reduce_bar_spacing"
    COMBINE_WITH_NEIGHBOR = "combine_with_neighbor"
    ASK_ENGINEER = "ask_engineer"


class FootingFailureState(BaseModel):
    """State of `footing_fix_strategy` (spec 0010 4.5): the six family statuses and four booleans; no ratio.

    The status of a family is that of `harness.footing_status` (4.4.5). `plan_at_max`, `depth_at_max` and
    `spacing_at_min` say that the plan, the depth or the bar spacing is at its basis bound. `hand_sized` says that
    the dimensions came from the engineer (the `source` of the footing's dimensions is `engineer`): spec 0010 4.5
    calls this flag `engineer_sized`, a name the redaction rule of spec 0005 4.10 refuses (the token `engineer` is
    on the deny list), so the point holds it as `hand_sized`.
    """

    model_config = _STRICT

    bearing: VerdictStatus
    one_way_shear: VerdictStatus
    punching: VerdictStatus
    flexure: VerdictStatus
    min_steel: VerdictStatus
    development: VerdictStatus
    plan_at_max: bool
    depth_at_max: bool
    spacing_at_min: bool
    hand_sized: bool


class FootingReviewAction(StrEnum):
    """Options of `footing_review`."""

    ACCEPT = "accept"
    REJECT = "reject"


class FootingReviewState(BaseModel):
    """State of `footing_review`: the counts of footings by status as labels and references to the schedule."""

    model_config = _STRICT

    counts: tuple[Label, ...]
    refs: tuple[Ref, ...]


@decision_point(
    name="footing_fix_strategy",
    version=1,
    title="Fix strategy of a failing footing",
    options=FootingAction,
    state=FootingFailureState,
)
class FootingFixStrategyPoint: ...


@decision_point(
    name="footing_review",
    version=1,
    title="Review of the footing schedule",
    options=FootingReviewAction,
    state=FootingReviewState,
)
class FootingReviewPoint: ...
