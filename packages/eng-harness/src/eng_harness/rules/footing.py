"""Rules of the decision point `footing_fix_strategy` (spec 0010 section 4.5; spec 0005 section 4.4).

Purpose: the five rules that answer a failing footing without the engineer; they ship `draft` for the owner's review
as R1 content (spec 0005 Q7, spec 0010 Q5). A rule states only what the spec table states, reads no basis path
(`thresholds=()`) and holds no number. `FOOTING_RULES` is the order in which a workflow passes them to `ctx.decide`
(the order of the table; the first rule that picks answers). The table names a rule `ff.<name>`; a rule id is
`<point>.<name>` (spec 0005 AC9), so the ids are `footing_fix_strategy.<name>`.
Units: none. Errors: none; a state outside every rule gives `None` and the engineer decides.
"""

from eng_contract.verdicts import VerdictStatus

from eng_harness.decisions.types import Pick, Rule, RuleBasis, rule
from eng_harness.workflows.isolated_footing._points import FootingAction, FootingFailureState

__all__ = ["FOOTING_RULES", "bearing_only", "development_only", "limits_reached", "shear_only", "steel_only"]


@rule(
    id="footing_fix_strategy.limits_reached",
    version=1,
    point="footing_fix_strategy",
    rationale="Plan, depth and bar spacing are all at their bounds, so no automatic change is left.",
)
def limits_reached(state: FootingFailureState, basis: RuleBasis) -> Pick[FootingAction] | None:
    """Spec 0010 4.5: `plan_at_max` and `depth_at_max` and `spacing_at_min` give `ask_engineer`."""
    if state.plan_at_max and state.depth_at_max and state.spacing_at_min:
        return Pick(FootingAction.ASK_ENGINEER)
    return None


@rule(
    id="footing_fix_strategy.bearing_only",
    version=1,
    point="footing_fix_strategy",
    rationale="Only the bearing check fails and the plan can still grow, so the plan is enlarged.",
)
def bearing_only(state: FootingFailureState, basis: RuleBasis) -> Pick[FootingAction] | None:
    """Spec 0010 4.5 (12 section 2): bearing `FAIL`, the five others `PASS`, not `plan_at_max` give `enlarge_plan`."""
    if (
        state.bearing == VerdictStatus.FAIL
        and state.one_way_shear == VerdictStatus.PASS
        and state.punching == VerdictStatus.PASS
        and state.flexure == VerdictStatus.PASS
        and state.min_steel == VerdictStatus.PASS
        and state.development == VerdictStatus.PASS
        and not state.plan_at_max
    ):
        return Pick(FootingAction.ENLARGE_PLAN)
    return None


@rule(
    id="footing_fix_strategy.shear_only",
    version=1,
    point="footing_fix_strategy",
    rationale="Only shear fails and the depth can still grow, so the footing is made deeper.",
)
def shear_only(state: FootingFailureState, basis: RuleBasis) -> Pick[FootingAction] | None:
    """Spec 0010 4.5: one-way or punching `FAIL`, bearing, flexure, minimum steel and development `PASS`, not
    `depth_at_max` give `increase_depth`."""
    if (
        (state.one_way_shear == VerdictStatus.FAIL or state.punching == VerdictStatus.FAIL)
        and state.bearing == VerdictStatus.PASS
        and state.flexure == VerdictStatus.PASS
        and state.min_steel == VerdictStatus.PASS
        and state.development == VerdictStatus.PASS
        and not state.depth_at_max
    ):
        return Pick(FootingAction.INCREASE_DEPTH)
    return None


@rule(
    id="footing_fix_strategy.steel_only",
    version=1,
    point="footing_fix_strategy",
    rationale="Only flexure or minimum steel fails and the bars can still be closer, so the spacing is reduced.",
)
def steel_only(state: FootingFailureState, basis: RuleBasis) -> Pick[FootingAction] | None:
    """Spec 0010 4.5 (Q5): flexure or minimum steel `FAIL`, bearing, one-way, punching and development `PASS`, not
    `spacing_at_min` give `reduce_bar_spacing`."""
    if (
        (state.flexure == VerdictStatus.FAIL or state.min_steel == VerdictStatus.FAIL)
        and state.bearing == VerdictStatus.PASS
        and state.one_way_shear == VerdictStatus.PASS
        and state.punching == VerdictStatus.PASS
        and state.development == VerdictStatus.PASS
        and not state.spacing_at_min
    ):
        return Pick(FootingAction.REDUCE_BAR_SPACING)
    return None


@rule(
    id="footing_fix_strategy.development_only",
    version=1,
    point="footing_fix_strategy",
    rationale="Only the development check fails and the plan can still grow, so the plan is enlarged.",
)
def development_only(state: FootingFailureState, basis: RuleBasis) -> Pick[FootingAction] | None:
    """Spec 0010 4.5: development `FAIL`, the five others `PASS`, not `plan_at_max` give `enlarge_plan`."""
    if (
        state.development == VerdictStatus.FAIL
        and state.bearing == VerdictStatus.PASS
        and state.one_way_shear == VerdictStatus.PASS
        and state.punching == VerdictStatus.PASS
        and state.flexure == VerdictStatus.PASS
        and state.min_steel == VerdictStatus.PASS
        and not state.plan_at_max
    ):
        return Pick(FootingAction.ENLARGE_PLAN)
    return None


FOOTING_RULES: tuple[Rule, ...] = (limits_reached, bearing_only, shear_only, steel_only, development_only)
"""The rules in the order of the spec 0010 4.5 table, as a workflow passes them to `ctx.decide`."""
