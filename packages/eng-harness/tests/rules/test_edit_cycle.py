"""Rules of the edit cycle (plan 0007 T7; spec 0007 AC18, section 4.6; spec 0005 AC12).

Expected picks are derived by hand from the rule lines of the table in spec 0007 section 4.6:
`edit_cycle_readback_result.pass` is "status `PASS` and reason `readback` -> `continue`" and
`edit_cycle_analysis_messages.clean` is "not `has_errors`, not `has_unclassified` -> `continue`". Neither rule
reads the basis (spec 0007 4.6: no rule holds a number), so the restricted basis view is built with no path.
A state outside the rule gives `None` (spec 0007 AC18), so the next rule or the engineer decides.
"""

from eng_contract.kinds.basis import DesignBasis
from eng_contract.verdicts import VerdictStatus

from eng_harness.ctx import BasisView
from eng_harness.decisions import _points, _rules
from eng_harness.decisions._points import DecisionPoint
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
    # The rule states nothing about the drift status: a drift above the limit does not leave it.
    drift = _analysis().model_copy(update={"drift_status": VerdictStatus.NEEDS_ENGINEER})
    assert analysis_messages_clean.fn(drift, _BASIS) == Pick(AnalysisAction.CONTINUE)


def _values(point: DecisionPoint) -> list[str]:
    assert isinstance(point.options, type)
    return [str(member.value) for member in point.options]


def test_discovery_finds_the_points_and_rules() -> None:
    points, rules = _points.discover(), _rules.discover()
    assert [p.name for p in points.points] == [
        "edit_cycle_analysis_messages",
        "edit_cycle_engineer_turn",
        "edit_cycle_readback_result",
    ]
    assert [r.id for r in rules.rules] == ["edit_cycle_analysis_messages.clean", "edit_cycle_readback_result.pass"]
    RuleRegistry(rules.rules, points)  # every rule names a point whose state model is its first parameter
    assert {p.name: _values(p) for p in points.points} == {
        "edit_cycle_analysis_messages": ["continue", "stop_cycle"],
        "edit_cycle_engineer_turn": ["accept", "more_edits", "hand_edit"],
        "edit_cycle_readback_result": ["continue", "restore_previous", "stop_cycle"],
    }
    assert all(r.thresholds == () and r.version == 1 for r in rules.rules)


def test_policies_follow_the_table() -> None:
    for policy in (READBACK_POLICY, ANALYSIS_POLICY):
        assert (policy.require_engineer, policy.model, policy.llm) == (True, False, False)
    assert TURN_POLICY.require_engineer is True
