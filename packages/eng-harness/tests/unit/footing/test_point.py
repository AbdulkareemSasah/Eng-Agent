"""Decision points of the isolated footing (plan 0010 T7; spec 0010 AC13, section 4.5; spec 0005 AC1, AC2, AC4, AC32).

Expected values are the lines of spec 0010 section 4.5: `footing_fix_strategy` (version 1) offers the five options of
`FootingAction`, its state holds the six family statuses and four booleans and no number, and `footing_review`
(version 1) offers `accept` and `reject` over counts as labels and references. Both are in `decisions.lock.json`.
"""

import json
from enum import StrEnum

from eng_contract.verdicts import VerdictStatus
from eng_harness.workflows.isolated_footing._points import (
    FIX_STRATEGY_POLICY,
    REVIEW_POLICY,
    FootingAction,
    FootingFailureState,
    FootingReviewAction,
    FootingReviewState,
)
from pydantic import TypeAdapter

from eng_harness.decisions import _points
from eng_harness.decisions._points import LOCK_PATH, DecisionPoint, check_lock, load_lock
from eng_harness.decisions._redaction import check_state
from eng_harness.decisions._rules import RuleRegistry
from eng_harness.decisions._rules import discover as discover_rules

_FAMILIES = ["bearing", "one_way_shear", "punching", "flexure", "min_steel", "development"]
_FLAGS = ["plan_at_max", "depth_at_max", "spacing_at_min", "hand_sized"]


def _point(name: str) -> DecisionPoint:
    found = _points.discover().get(name)
    assert found is not None, name
    return found


def _values(point: DecisionPoint) -> list[str]:
    assert isinstance(point.options, type)
    assert issubclass(point.options, StrEnum)
    return [str(member.value) for member in point.options]


def test_point_definition() -> None:
    fix = _point("footing_fix_strategy")
    assert (fix.version, fix.title, fix.state, fix.yes_no) == (
        1,
        "Fix strategy of a failing footing",
        FootingFailureState,
        None,
    )
    assert fix.options is FootingAction
    assert _values(fix) == [
        "enlarge_plan",
        "increase_depth",
        "reduce_bar_spacing",
        "combine_with_neighbor",
        "ask_engineer",
    ]
    review = _point("footing_review")
    assert (review.version, review.title, review.state, review.yes_no) == (
        1,
        "Review of the footing schedule",
        FootingReviewState,
        None,
    )
    assert review.options is FootingReviewAction
    assert _values(review) == ["accept", "reject"]

    # The state holds only statuses and booleans: six family statuses first, then the four flags, no number (Q4).
    fields = FootingFailureState.model_fields
    assert list(fields) == _FAMILIES + _FLAGS
    assert [fields[name].annotation for name in _FAMILIES] == [VerdictStatus] * 6
    assert [fields[name].annotation for name in _FLAGS] == [bool] * 4
    assert list(FootingReviewState.model_fields) == ["counts", "refs"]
    assert FootingFailureState.model_config == {"frozen": True, "extra": "forbid"}
    assert FootingReviewState.model_config == {"frozen": True, "extra": "forbid"}

    # A point is defined only when its state passes the redaction rules by construction (spec 0005 AC32), and a state
    # of statuses and booleans has no value that could leave the machine.
    state = FootingFailureState(**dict.fromkeys(_FAMILIES, VerdictStatus.PASS), **dict.fromkeys(_FLAGS, False))
    assert check_state(TypeAdapter(FootingFailureState).dump_python(state, mode="json"), ()) == ()
    labels = FootingReviewState(counts=("passed 2", "needs engineer 1"), refs=())
    assert check_state(labels.model_dump(mode="json"), ()) == ()

    # Policies (spec 0010 section 4.5): the decision model in shadow mode and no language model for the fix strategy;
    # the engineer always decides the review.
    assert (FIX_STRATEGY_POLICY.model, FIX_STRATEGY_POLICY.llm, FIX_STRATEGY_POLICY.shadow) == (True, False, True)
    assert FIX_STRATEGY_POLICY.require_engineer is False
    assert REVIEW_POLICY.require_engineer is True

    # Both points are in the committed lock at the hash of their definition (spec 0005 AC4).
    lock = {entry["name"]: entry for entry in json.loads(LOCK_PATH.read_text(encoding="utf-8"))}
    for point in (fix, review):
        assert lock[point.name] == {
            "name": point.name,
            "version": 1,
            "schema_sha256": point.schema_sha256,
        }
    assert [f for f in check_lock(_points.discover(), load_lock(LOCK_PATH)) if f.name.startswith("footing_")] == []
    assert RuleRegistry(discover_rules().rules, _points.discover()).get("footing_fix_strategy.bearing_only")
