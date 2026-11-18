"""Rules of the column workflow: a typical and a boundary test each (plan 0013 T9; spec 0013 AC14; spec 0005 AC12).

Expected picks are derived by hand from the rule lines of the table in spec 0013 section 4.8. No rule reads the basis
(spec 0013 4.8: no rule holds a number), so the restricted basis view is built with no path. A state outside a rule
gives `None`, so the next rule or the engineer decides.
"""

from eng_contract.kinds.basis import DesignBasis
from eng_contract.verdicts import VerdictStatus
from eng_harness.rules.column_design import map_result_clean, member_fail_matched, member_no_proposal, readback_pass
from eng_harness.workflows.column_design._points import (
    MapAction,
    MapState,
    MemberAction,
    MemberState,
    ProposalState,
    RevitReadbackAction,
    RevitReadbackState,
)

from eng_harness.ctx import BasisView
from eng_harness.decisions.types import Pick, RuleBasis

_RESULT = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
_BASIS = RuleBasis(BasisView(_RESULT, DesignBasis(template=None, fields={}), ()), ())


def _member(status: VerdictStatus, proposal: ProposalState, *, has_not_checked: bool = False) -> MemberState:
    return MemberState(
        status=status,
        host_status=status,
        code_status=status,
        has_not_checked=has_not_checked,
        proposal=proposal,
        refs=(),
    )


def _map(
    *, ambiguous: bool = False, unmatched: bool = False, conflicts: bool = False, complete: bool = True
) -> MapState:
    return MapState(has_ambiguous=ambiguous, has_unmatched_frames=unmatched, has_conflicts=conflicts, complete=complete)


def test_no_proposal_typical() -> None:
    state = _member(VerdictStatus.PASS, ProposalState.NONE)
    assert member_no_proposal.fn(state, _BASIS) == Pick(MemberAction.KEEP)


def test_no_proposal_boundary() -> None:
    # Each state differs from the one passing state in exactly one field of the rule's condition.
    for proposal in (ProposalState.MATCHED, ProposalState.NO_SECTION_IN_MODEL, ProposalState.AMBIGUOUS):
        assert member_no_proposal.fn(_member(VerdictStatus.PASS, proposal), _BASIS) is None
    for status in (VerdictStatus.FAIL, VerdictStatus.NEEDS_ENGINEER, VerdictStatus.NOT_APPLICABLE, VerdictStatus.ERROR):
        assert member_no_proposal.fn(_member(status, ProposalState.NONE), _BASIS) is None


def test_fail_matched_typical() -> None:
    state = _member(VerdictStatus.FAIL, ProposalState.MATCHED)
    assert member_fail_matched.fn(state, _BASIS) == Pick(MemberAction.CHANGE_SECTION)


def test_fail_matched_boundary() -> None:
    for proposal in (ProposalState.NONE, ProposalState.NO_SECTION_IN_MODEL, ProposalState.AMBIGUOUS):
        assert member_fail_matched.fn(_member(VerdictStatus.FAIL, proposal), _BASIS) is None
    for status in (VerdictStatus.PASS, VerdictStatus.NEEDS_ENGINEER, VerdictStatus.NOT_APPLICABLE, VerdictStatus.ERROR):
        assert member_fail_matched.fn(_member(status, ProposalState.MATCHED), _BASIS) is None
    # A failing column whose other statuses differ is still decided by `status` alone, as the table says.
    state = _member(VerdictStatus.FAIL, ProposalState.MATCHED, has_not_checked=True)
    assert member_fail_matched.fn(state, _BASIS) == Pick(MemberAction.CHANGE_SECTION)


def test_clean_typical() -> None:
    assert map_result_clean.fn(_map(), _BASIS) == Pick(MapAction.CONTINUE_MATCHED)


def test_clean_boundary() -> None:
    # One condition at a time: each of the four alone is enough to leave the rule.
    assert map_result_clean.fn(_map(ambiguous=True), _BASIS) is None
    assert map_result_clean.fn(_map(unmatched=True), _BASIS) is None
    assert map_result_clean.fn(_map(conflicts=True), _BASIS) is None
    assert map_result_clean.fn(_map(complete=False), _BASIS) is None
    assert map_result_clean.fn(_map(ambiguous=True, unmatched=True, conflicts=True, complete=False), _BASIS) is None


def test_pass_typical() -> None:
    state = RevitReadbackState(status=VerdictStatus.PASS, issues=())
    assert readback_pass.fn(state, _BASIS) == Pick(RevitReadbackAction.ACCEPT)


def test_pass_boundary() -> None:
    for status in (VerdictStatus.FAIL, VerdictStatus.NEEDS_ENGINEER, VerdictStatus.NOT_APPLICABLE, VerdictStatus.ERROR):
        assert readback_pass.fn(RevitReadbackState(status=status, issues=()), _BASIS) is None
