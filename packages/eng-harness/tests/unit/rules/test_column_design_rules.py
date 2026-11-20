"""Decision points and rules of the column workflow (plan 0013 T9; spec 0013 AC14, section 4.8).

Expected picks are derived by hand from the rule lines of the table in spec 0013 section 4.8:
`cm.no_proposal` is "status `PASS` and proposal `none` -> `keep`", `cm.fail_matched` is "status `FAIL` and proposal
`matched` -> `change_section`", `map.clean` is "all of has_ambiguous, has_unmatched_frames, has_conflicts false and
`complete` -> `continue_matched`" and `rr.pass` is "`PASS` -> `accept`". The names carry the point as the prefix
because the grammar of spec 0005 AC1 and AC9 allows no dot in a point name and wants three characters before the dot
of a rule id. A state outside a rule gives `None`, so the engineer decides (spec 0013 AC14).
"""

import itertools
import json
from pathlib import Path

import pytest
from eng_contract.kinds.basis import DesignBasis
from eng_contract.verdicts import VerdictStatus

from eng_harness.ctx import BasisView
from eng_harness.decisions import _points, _rules
from eng_harness.decisions._points import PointRegistry
from eng_harness.decisions._rules import RuleRegistry
from eng_harness.decisions.types import Pick, RuleBasis
from eng_harness.rules.column_design import map_result_clean, member_fail_matched, member_no_proposal, readback_pass
from eng_harness.workflows.column_design._points import (
    COLUMN_POLICY,
    MapAction,
    MapState,
    MemberAction,
    MemberState,
    ProposalState,
    RevitReadbackAction,
    RevitReadbackState,
    TurnAction,
    TurnState,
)

_RESULT = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
_BASIS = RuleBasis(BasisView(_RESULT, DesignBasis(template=None, fields={}), ()), ())
_PACKAGE = Path(_points.__file__).resolve().parents[1]


def _member(
    status: VerdictStatus = VerdictStatus.PASS,
    proposal: ProposalState = ProposalState.NONE,
    *,
    has_not_checked: bool = False,
) -> MemberState:
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


def _readback(status: VerdictStatus = VerdictStatus.PASS) -> RevitReadbackState:
    return RevitReadbackState(status=status, issues=())


def test_member_action_rules() -> None:
    for status, proposal in itertools.product(VerdictStatus, ProposalState):
        keep = status == VerdictStatus.PASS and proposal == ProposalState.NONE
        change = status == VerdictStatus.FAIL and proposal == ProposalState.MATCHED
        state = _member(status, proposal)
        assert member_no_proposal.fn(state, _BASIS) == (Pick(MemberAction.KEEP) if keep else None), (status, proposal)
        assert member_fail_matched.fn(state, _BASIS) == (Pick(MemberAction.CHANGE_SECTION) if change else None), (
            status,
            proposal,
        )
    # A FAIL or NEEDS_ENGINEER column with no proposal gets no decision and reaches the engineer (AC14).
    for status in (VerdictStatus.FAIL, VerdictStatus.NEEDS_ENGINEER):
        state = _member(status, ProposalState.NONE)
        assert member_no_proposal.fn(state, _BASIS) is None
        assert member_fail_matched.fn(state, _BASIS) is None
    # The two rules are on the point of the per-column action and both are reviewed as draft rules.
    for item in (member_no_proposal, member_fail_matched):
        assert item.point == "column_design_member_action"
        assert item.thresholds == ()
    assert member_no_proposal.id == "column_design_member_action.no_proposal"
    assert member_fail_matched.id == "column_design_member_action.fail_matched"
    assert COLUMN_POLICY.model is False
    assert COLUMN_POLICY.llm is False
    assert COLUMN_POLICY.require_engineer is True


def test_revit_rules() -> None:
    for ambiguous, unmatched, conflicts, complete in itertools.product((False, True), repeat=4):
        state = _map(ambiguous=ambiguous, unmatched=unmatched, conflicts=conflicts, complete=complete)
        clean = not (ambiguous or conflicts) and complete and not unmatched
        assert map_result_clean.fn(state, _BASIS) == (Pick(MapAction.CONTINUE_MATCHED) if clean else None)
    for status in VerdictStatus:
        accepted = status == VerdictStatus.PASS
        assert readback_pass.fn(_readback(status), _BASIS) == (Pick(RevitReadbackAction.ACCEPT) if accepted else None)
    assert map_result_clean.id == "column_revit_map_result.clean"
    assert map_result_clean.point == "column_revit_map_result"
    assert readback_pass.id == "column_revit_readback_result.pass"
    assert readback_pass.point == "column_revit_readback_result"
    assert COLUMN_POLICY.require_engineer is True


def test_points_and_options() -> None:
    assert [m.value for m in MemberAction] == ["keep", "change_section", "refer_to_engineer"]
    assert [m.value for m in TurnAction] == ["accept", "revise", "hand_edit"]
    assert [m.value for m in MapAction] == ["continue_matched", "stop"]
    assert [m.value for m in RevitReadbackAction] == ["accept", "abandon"]
    assert [m.value for m in ProposalState] == ["none", "matched", "no_section_in_model", "ambiguous"]
    found = {(p.name, p.version, p.options, p.state) for p in _points.discover().points if p.name.startswith("column_")}
    assert found == {
        ("column_design_member_action", 1, MemberAction, MemberState),
        ("column_design_engineer_turn", 1, TurnAction, TurnState),
        ("column_revit_map_result", 1, MapAction, MapState),
        ("column_revit_readback_result", 1, RevitReadbackAction, RevitReadbackState),
    }


def test_lock() -> None:
    points = {p.name: p for p in _points.discover().points}
    wanted = {
        "column_design_member_action": MemberState,
        "column_design_engineer_turn": TurnState,
        "column_revit_map_result": MapState,
        "column_revit_readback_result": RevitReadbackState,
    }
    for name, state in wanted.items():
        assert points[name].state is state
    rules = _rules.discover()
    ids = {r.id for r in rules.rules}
    assert {
        "column_design_member_action.no_proposal",
        "column_design_member_action.fail_matched",
        "column_revit_map_result.clean",
        "column_revit_readback_result.pass",
    } <= ids
    # Every rule names a registered point whose state model is its first parameter (spec 0005 AC9).
    assert RuleRegistry(list(rules.rules), PointRegistry(list(points.values()))).rules == rules.rules
    point_lock = json.loads((_PACKAGE / "decisions.lock.json").read_text(encoding="utf-8"))
    lock_entries = {e["name"]: e for e in point_lock}
    for name in wanted:
        assert lock_entries[name]["version"] == 1
        assert lock_entries[name]["schema_sha256"] == points[name].schema_sha256
    rule_lock = {e["id"]: e for e in json.loads((_PACKAGE / "rules.lock.json").read_text(encoding="utf-8"))}
    for item in rules.rules:
        if item.point in wanted:
            assert rule_lock[item.id]["version"] == item.version == 1
            assert rule_lock[item.id]["code_sha256"] == item.code_sha256


def test_state_models_are_strict() -> None:
    fields = {"has_ambiguous": False, "has_unmatched_frames": False, "has_conflicts": False, "complete": True}
    assert MapState.model_validate(fields) == _map()
    with pytest.raises(ValueError, match="extra"):
        MapState.model_validate({**fields, "other": True})
