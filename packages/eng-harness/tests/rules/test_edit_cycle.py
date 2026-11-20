"""Rules of the edit cycle (plan 0007 T7; spec 0007 AC18, section 4.6; spec 0005 AC12).

Expected picks are derived by hand from the rule lines of the table in spec 0007 section 4.6:
`edit_cycle_readback_result.pass` is "status `PASS` and reason `readback` -> `continue`" and
`edit_cycle_analysis_messages.clean` is "not `has_errors`, not `has_unclassified`, drift `PASS` -> `continue`".
Neither rule reads the basis (spec 0007 4.6: no rule holds a number),
so the restricted basis view is built with no path.
A state outside the rule gives `None` (spec 0007 AC18), so the next rule or the engineer decides.
"""

import json
from math import inf, nextafter
from pathlib import Path

from eng_contract.kinds.basis import DesignBasis
from eng_contract.verdicts import VerdictStatus

from eng_harness.calc import InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs.edit_cycle.analysis_summary import SummaryBody, SummaryInput, analysis_summary
from eng_harness.ctx import BasisView
from eng_harness.decisions import _points, _rules
from eng_harness.decisions._points import DecisionPoint, PointRegistry
from eng_harness.decisions._rules import RuleRegistry
from eng_harness.decisions.types import Pick, RuleBasis
from eng_harness.rules.edit_cycle import analysis_messages_clean, readback_result_pass
from eng_harness.workflows.model_edit_cycle._points import (
    ANALYSIS_POLICY,
    READBACK_POLICY,
    TURN_POLICY,
    AnalysisAction,
    AnalysisState,
    ReadbackAction,
    ReadbackReason,
    ReadbackState,
)

_RESULT = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
_BASIS = RuleBasis(BasisView(_RESULT, DesignBasis(template=None, fields={}), ()), ())


def _readback(
    status: VerdictStatus = VerdictStatus.PASS, reason: ReadbackReason = ReadbackReason.READBACK
) -> ReadbackState:
    return ReadbackState(
        status=status,
        has_mismatch=False,
        has_missing=False,
        has_unexpected=False,
        has_not_read=False,
        reason=reason,
        refs=(),
    )


def _analysis(*, has_errors: bool = False, has_unclassified: bool = False) -> AnalysisState:
    return AnalysisState(
        has_errors=has_errors,
        has_unclassified=has_unclassified,
        drift_status=VerdictStatus.PASS,
        refs=(),
    )


def test_pass_typical() -> None:
    assert readback_result_pass.fn(_readback(), _BASIS) == Pick(ReadbackAction.CONTINUE)


def test_pass_boundary() -> None:
    # Each state differs from the one passing state in exactly one field of the rule's condition.
    failed_check = _readback(reason=ReadbackReason("check_model_failed"))
    assert readback_result_pass.fn(failed_check, _BASIS) is None
    changed = _readback(reason=ReadbackReason.MODEL_CHANGED_DURING_APPLY)
    assert readback_result_pass.fn(changed, _BASIS) is None
    for status in (VerdictStatus.FAIL, VerdictStatus.NEEDS_ENGINEER, VerdictStatus.NOT_APPLICABLE, VerdictStatus.ERROR):
        assert readback_result_pass.fn(_readback(status=status), _BASIS) is None
    both = _readback(status=VerdictStatus.FAIL, reason=ReadbackReason.MODEL_CHANGED_DURING_APPLY)
    assert readback_result_pass.fn(both, _BASIS) is None


def test_clean_typical() -> None:
    assert analysis_messages_clean.fn(_analysis(), _BASIS) == Pick(AnalysisAction.CONTINUE)


def test_clean_boundary() -> None:
    # One flag at a time, then both: each of the two conditions alone is enough to leave the rule.
    assert analysis_messages_clean.fn(_analysis(has_errors=True), _BASIS) is None
    assert analysis_messages_clean.fn(_analysis(has_unclassified=True), _BASIS) is None
    assert analysis_messages_clean.fn(_analysis(has_errors=True, has_unclassified=True), _BASIS) is None
    # Every non-PASS drift status leaves the clean rule (spec 0007 4.6, amendment B-544).
    for status in VerdictStatus:
        if status != VerdictStatus.PASS:
            drift = _analysis().model_copy(update={"drift_status": status})
            assert analysis_messages_clean.fn(drift, _BASIS) is None


def _summary(inp: SummaryInput, meta: InputMeta) -> SummaryBody:
    return SummaryBody.model_validate(analysis_summary(inp, meta, TraceBuilder()).model_dump())


def test_clean_drift_at_and_above_the_limit() -> None:
    """Spec 0007 4.4.4, 4.6, AC18: exact equality passes; the next stored float exceeds.

    Source: data/golden/edit_cycle/analysis-clean.json, its confirmed synthetic basis limit
    0.01 (dimensionless), no messages, X drifts 0.004 and 0.01. By hand: neither row is
    strictly above 0.01, so exceeding is empty, drift_status PASS and D-3 continues.
    Replace the highest row by nextafter(limit, +inf): it alone is strictly above the
    limit, so exceeding has S2, drift_status NEEDS_ENGINEER and the clean rule gives None.
    No tolerance or engineering limit is chosen here. No rows also means exceeding empty
    and PASS under Q21's interim reading; this test adds no missing-row policy.
    """
    path = Path(__file__).resolve().parents[1] / "data/golden/edit_cycle/analysis-clean.json"
    case = json.loads(path.read_text(encoding="utf-8"))
    inp = SummaryInput.model_validate(case["input"])
    kinds = {
        "messages": "harness.csi_analysis_messages/1",
        "drifts": "forces.story_drifts/1",
        "basis": "basis.design_basis/1",
    }
    meta = InputMeta(
        refs={
            name: RefMeta(
                result_id=result_id,
                ref=result_id,
                kind=kinds[name],
                complete=True,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="fixture",
            )
            for name, result_id in case["refs"].items()
        }
    )
    at = _summary(inp, meta)
    assert at.exceeding == []
    assert at.governing_drift["X"].ratio == at.limit_ratio
    state = AnalysisState(
        has_errors=at.has_errors, has_unclassified=at.has_unclassified, drift_status=VerdictStatus.PASS, refs=()
    )
    assert analysis_messages_clean.fn(state, _BASIS) == Pick(AnalysisAction.CONTINUE)
    rows = list(inp.drifts.rows)
    rows[1] = rows[1].model_copy(update={"drift_ratio": nextafter(at.limit_ratio, inf)})
    above = _summary(inp.model_copy(update={"drifts": inp.drifts.model_copy(update={"rows": rows})}), meta)
    assert [(row.story, row.ratio) for row in above.exceeding] == [("S2", nextafter(at.limit_ratio, inf))]
    drift_status = VerdictStatus.NEEDS_ENGINEER if above.exceeding else VerdictStatus.PASS
    assert analysis_messages_clean.fn(state.model_copy(update={"drift_status": drift_status}), _BASIS) is None
    absent = _summary(inp.model_copy(update={"drifts": inp.drifts.model_copy(update={"rows": []})}), meta)
    assert absent.exceeding == []
    assert analysis_messages_clean.fn(state, _BASIS) == Pick(AnalysisAction.CONTINUE)


def _values(point: DecisionPoint) -> list[str]:
    assert isinstance(point.options, type)
    return [str(member.value) for member in point.options]


def test_discovery_finds_the_points_and_rules() -> None:
    points, rules = _points.discover(), _rules.discover()
    # Other workflows ship their own points and rules; this test judges those of the edit cycle.
    RuleRegistry(rules.rules, points)  # every rule names a point whose state model is its first parameter
    points = PointRegistry([p for p in points.points if p.name.startswith("edit_cycle_")])
    rules = RuleRegistry([r for r in rules.rules if r.id.startswith("edit_cycle_")], points)
    assert [p.name for p in points.points] == [
        "edit_cycle_analysis_messages",
        "edit_cycle_engineer_turn",
        "edit_cycle_readback_result",
    ]
    assert [r.id for r in rules.rules] == ["edit_cycle_analysis_messages.clean", "edit_cycle_readback_result.pass"]
    assert {p.name: _values(p) for p in points.points} == {
        "edit_cycle_analysis_messages": ["continue", "stop_cycle"],
        "edit_cycle_engineer_turn": ["accept", "more_edits", "hand_edit"],
        "edit_cycle_readback_result": ["continue", "restore_previous", "stop_cycle"],
    }
    assert all(r.thresholds == () and r.version == 2 for r in rules.rules)
    assert {p.name: p.version for p in points.points} == {
        "edit_cycle_analysis_messages": 1,
        "edit_cycle_engineer_turn": 1,
        "edit_cycle_readback_result": 2,
    }


def test_policies_follow_the_table() -> None:
    for policy in (READBACK_POLICY, ANALYSIS_POLICY):
        assert (policy.require_engineer, policy.model, policy.llm) == (True, False, False)
    assert TURN_POLICY.require_engineer is True
