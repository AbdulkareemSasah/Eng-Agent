"""Rules of `footing_fix_strategy` (plan 0010 T7; spec 0010 AC14, section 4.5; spec 0005 section 4.4).

Expected picks are derived by hand from the table of spec 0010 section 4.5, where "the five others" are the five
families that the rule does not name and every family but the named one must be `PASS`:

- `limits_reached`: `plan_at_max` and `depth_at_max` and `spacing_at_min` give `ask_engineer`.
- `bearing_only`: bearing `FAIL`, the five others `PASS`, not `plan_at_max` give `enlarge_plan`.
- `shear_only`: one-way or punching `FAIL`, bearing, flexure, minimum steel, development `PASS`, not `depth_at_max`
  give `increase_depth`.
- `steel_only`: flexure or minimum steel `FAIL`, bearing, one-way, punching, development `PASS`, not `spacing_at_min`
  give `reduce_bar_spacing`.
- `development_only`: development `FAIL`, the five others `PASS`, not `plan_at_max` give `enlarge_plan`.

A boundary state differs from a typical one in one thing (one more failing family, one family not failing, a bound
reached) and gives `None`, so the next rule or the engineer decides. No rule reads the basis (`thresholds=()`).
The spec table names the rules `ff.<name>`; a rule id is `<point>.<name>` (spec 0005 AC9), so the ids here are
`footing_fix_strategy.<name>`. Synthetic states only: no engineering value takes part.
"""

from collections.abc import Iterator
from itertools import product
from typing import Any

import pytest
from eng_contract.kinds.basis import DesignBasis
from eng_contract.verdicts import VerdictStatus

from eng_harness.ctx import BasisView
from eng_harness.decisions import _points, _rules
from eng_harness.decisions._rules import RuleRegistry
from eng_harness.decisions.types import Pick, Rule, RuleBasis
from eng_harness.rules.footing import (
    FOOTING_RULES,
    bearing_only,
    development_only,
    limits_reached,
    shear_only,
    steel_only,
)
from eng_harness.workflows.isolated_footing._points import FootingAction, FootingFailureState

_BASIS = RuleBasis(BasisView("res_01ARZ3NDEKTSV4RRFFQ69G5FAV", DesignBasis(template=None, fields={}), ()), ())
_PASS, _FAIL, _NEEDS = VerdictStatus.PASS, VerdictStatus.FAIL, VerdictStatus.NEEDS_ENGINEER
_FAMILIES = ("bearing", "one_way_shear", "punching", "flexure", "min_steel", "development")
_FLAGS = ("plan_at_max", "depth_at_max", "spacing_at_min", "hand_sized")
_NOT_FAIL = (_PASS, _NEEDS, VerdictStatus.ERROR, VerdictStatus.NOT_APPLICABLE)
_AT_MAX = {"plan_at_max": True, "depth_at_max": True, "spacing_at_min": True}


def _state(**over: Any) -> FootingFailureState:
    """All six families `PASS` and all four flags false, with `over` applied."""
    base: dict[str, Any] = {**dict.fromkeys(_FAMILIES, _PASS), **dict.fromkeys(_FLAGS, False)}
    return FootingFailureState.model_validate(base | over)


def _typical() -> Iterator[tuple[Rule, dict[str, Any], FootingAction]]:
    yield limits_reached, {**_AT_MAX, "bearing": _FAIL}, FootingAction.ASK_ENGINEER
    yield limits_reached, {**_AT_MAX, "flexure": _FAIL, "hand_sized": True}, FootingAction.ASK_ENGINEER
    yield bearing_only, {"bearing": _FAIL}, FootingAction.ENLARGE_PLAN
    # The other bounds and the hand-sized flag are no part of the rule's condition.
    yield (
        bearing_only,
        {"bearing": _FAIL, "depth_at_max": True, "spacing_at_min": True, "hand_sized": True},
        FootingAction.ENLARGE_PLAN,
    )
    yield shear_only, {"one_way_shear": _FAIL}, FootingAction.INCREASE_DEPTH
    yield shear_only, {"punching": _FAIL}, FootingAction.INCREASE_DEPTH
    yield shear_only, {"one_way_shear": _FAIL, "punching": _FAIL}, FootingAction.INCREASE_DEPTH
    yield (
        shear_only,
        {"punching": _FAIL, "plan_at_max": True, "spacing_at_min": True, "hand_sized": True},
        FootingAction.INCREASE_DEPTH,
    )
    yield steel_only, {"flexure": _FAIL}, FootingAction.REDUCE_BAR_SPACING
    yield steel_only, {"min_steel": _FAIL}, FootingAction.REDUCE_BAR_SPACING
    yield steel_only, {"flexure": _FAIL, "min_steel": _FAIL}, FootingAction.REDUCE_BAR_SPACING
    yield (
        steel_only,
        {"min_steel": _FAIL, "plan_at_max": True, "depth_at_max": True, "hand_sized": True},
        FootingAction.REDUCE_BAR_SPACING,
    )
    yield development_only, {"development": _FAIL}, FootingAction.ENLARGE_PLAN
    yield (
        development_only,
        {"development": _FAIL, "depth_at_max": True, "spacing_at_min": True, "hand_sized": True},
        FootingAction.ENLARGE_PLAN,
    )


def _boundaries() -> Iterator[tuple[Rule, dict[str, Any]]]:
    # limits_reached: each bound alone not reached.
    for flag in ("plan_at_max", "depth_at_max", "spacing_at_min"):
        yield limits_reached, {**_AT_MAX, flag: False, "bearing": _FAIL}
    # bearing_only: the bound reached; the bearing family not failing; one more failing or open family.
    yield bearing_only, {"bearing": _FAIL, "plan_at_max": True}
    for status in _NOT_FAIL:
        yield bearing_only, {"bearing": status}
    for family, status in product(_FAMILIES[1:], (_FAIL, _NEEDS)):
        yield bearing_only, {"bearing": _FAIL, family: status}
    # shear_only.
    yield shear_only, {"one_way_shear": _FAIL, "depth_at_max": True}
    yield shear_only, {"punching": _FAIL, "depth_at_max": True}
    for status in _NOT_FAIL:
        yield shear_only, {"one_way_shear": status, "punching": status}
    for family, status in product(("bearing", "flexure", "min_steel", "development"), (_FAIL, _NEEDS)):
        yield shear_only, {"one_way_shear": _FAIL, family: status}
        yield shear_only, {"punching": _FAIL, family: status}
    # steel_only.
    yield steel_only, {"flexure": _FAIL, "spacing_at_min": True}
    yield steel_only, {"min_steel": _FAIL, "spacing_at_min": True}
    for status in _NOT_FAIL:
        yield steel_only, {"flexure": status, "min_steel": status}
    for family, status in product(("bearing", "one_way_shear", "punching", "development"), (_FAIL, _NEEDS)):
        yield steel_only, {"flexure": _FAIL, family: status}
        yield steel_only, {"min_steel": _FAIL, family: status}
    # development_only.
    yield development_only, {"development": _FAIL, "plan_at_max": True}
    for status in _NOT_FAIL:
        yield development_only, {"development": status}
    for family, status in product(_FAMILIES[:-1], (_FAIL, _NEEDS)):
        yield development_only, {"development": _FAIL, family: status}


def _cases() -> list[tuple[Rule, dict[str, Any], FootingAction | None]]:
    return [*_typical(), *((rule, over, None) for rule, over in _boundaries())]


@pytest.mark.parametrize(("rule", "over", "expected"), _cases())
def test_typical_and_boundary(rule: Rule, over: dict[str, Any], expected: FootingAction | None) -> None:
    assert rule.fn(_state(**over), _BASIS) == (None if expected is None else Pick(expected))


def test_order() -> None:
    names = ["limits_reached", "bearing_only", "shear_only", "steel_only", "development_only"]
    assert [r.id for r in FOOTING_RULES] == [f"footing_fix_strategy.{name}" for name in names]
    assert (limits_reached, bearing_only, shear_only, steel_only, development_only) == FOOTING_RULES
    # Discovery finds all five, sorted by id (spec 0005 4.4), and each names the point and its state model.
    found = _rules.discover()
    assert {r.id for r in FOOTING_RULES} <= {r.id for r in found.rules}
    RuleRegistry(found.rules, _points.discover())
    assert all(r.point == "footing_fix_strategy" and r.thresholds == () and r.version == 1 for r in FOOTING_RULES)
    assert all(r.state is FootingFailureState for r in FOOTING_RULES)
    # The conditions exclude one another: over a grid of statuses and flags no state is matched by two rules, so the
    # first match in the order above is the only match and the order decides no pick.
    picks: dict[str, int] = dict.fromkeys(names, 0)
    for statuses in product((_PASS, _FAIL, _NEEDS), repeat=len(_FAMILIES)):
        for flags in product((False, True), repeat=len(_FLAGS)):
            state = _state(**dict(zip(_FAMILIES, statuses, strict=True)) | dict(zip(_FLAGS, flags, strict=True)))
            matched = [r for r in FOOTING_RULES if r.fn(state, _BASIS) is not None]
            assert len(matched) <= 1
            for r in matched:
                picks[r.id.split(".")[1]] += 1
    assert all(count > 0 for count in picks.values())
