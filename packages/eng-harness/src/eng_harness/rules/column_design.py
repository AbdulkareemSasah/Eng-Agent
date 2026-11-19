"""Rules of the column workflow decision points (spec 0013 section 4.8; spec 0005 section 4.4).

Purpose: the four rules that answer the column and Revit points without the engineer; all ship `draft` for the owner's
review (spec 0005 Q7). A rule states only what the spec table states, reads no basis path and holds no number. The
table's `cm.no_proposal`, `cm.fail_matched`, `map.clean` and `rr.pass` carry their point as the id prefix (spec 0005
AC9). Units: none. Errors: none; a state outside a rule gives `None` and the next rule, or the engineer, decides: a
`FAIL` or `NEEDS_ENGINEER` column with proposal `none` gets no decision (spec 0013 AC14).
"""

from eng_contract.verdicts import VerdictStatus

from eng_harness.decisions.types import Pick, RuleBasis, rule
from eng_harness.workflows.column_design._points import (
    MapAction,
    MapState,
    MemberAction,
    MemberState,
    ProposalState,
    RevitReadbackAction,
    RevitReadbackState,
)

__all__ = ["map_result_clean", "member_fail_matched", "member_no_proposal", "readback_pass"]


@rule(
    id="column_design_member_action.no_proposal",
    version=1,
    point="column_design_member_action",
    rationale="A column that passes and has no section proposal stays as it is.",
)
def member_no_proposal(state: MemberState, basis: RuleBasis) -> Pick[MemberAction] | None:
    """Spec 0013 4.8: status `PASS` and proposal `none` give `keep`."""
    if state.status == VerdictStatus.PASS and state.proposal == ProposalState.NONE:
        return Pick(MemberAction.KEEP)
    return None


@rule(
    id="column_design_member_action.fail_matched",
    version=1,
    point="column_design_member_action",
    rationale="A failing column whose proposed section is one that exists in the model changes to that section.",
)
def member_fail_matched(state: MemberState, basis: RuleBasis) -> Pick[MemberAction] | None:
    """Spec 0013 4.8: status `FAIL` and proposal `matched` give `change_section`."""
    if state.status == VerdictStatus.FAIL and state.proposal == ProposalState.MATCHED:
        return Pick(MemberAction.CHANGE_SECTION)
    return None


@rule(
    id="column_revit_map_result.clean",
    version=1,
    point="column_revit_map_result",
    rationale="A complete map with no ambiguous pair, no unmatched frame and no conflict continues with the matches.",
)
def map_result_clean(state: MapState, basis: RuleBasis) -> Pick[MapAction] | None:
    """Spec 0013 4.8: no ambiguous pair, no unmatched frame, no conflict and `complete` give `continue_matched`."""
    if not (state.has_ambiguous or state.has_unmatched_frames or state.has_conflicts) and state.complete:
        return Pick(MapAction.CONTINUE_MATCHED)
    return None


@rule(
    id="column_revit_readback_result.pass",
    version=1,
    point="column_revit_readback_result",
    rationale="A Revit read-back that passes is accepted.",
)
def readback_pass(state: RevitReadbackState, basis: RuleBasis) -> Pick[RevitReadbackAction] | None:
    """Spec 0013 4.8: status `PASS` gives `accept`."""
    if state.status == VerdictStatus.PASS:
        return Pick(RevitReadbackAction.ACCEPT)
    return None
