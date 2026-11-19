"""One typical and one boundary test per footing rule, the names spec 0005 AC12 and process/10 section 4 require.

`missing_rule_tests` looks for `test_<name>_typical` and `test_<name>_boundary` in `tests/rules/test_<module>.py`
for each rule of `eng_harness.rules.footing`. The full tables (every family, every bound, the order) are in
`test_footing_rules.py`; each test here pins the representative state of that table (spec 0010 section 4.5).
"""

from typing import Any

from eng_contract.kinds.basis import DesignBasis
from eng_contract.verdicts import VerdictStatus

from eng_harness.ctx import BasisView
from eng_harness.decisions.types import Pick, RuleBasis
from eng_harness.rules.footing import (
    bearing_only,
    development_only,
    limits_reached,
    shear_only,
    steel_only,
)
from eng_harness.workflows.isolated_footing._points import FootingAction, FootingFailureState

_BASIS = RuleBasis(BasisView("res_01ARZ3NDEKTSV4RRFFQ69G5FAV", DesignBasis(template=None, fields={}), ()), ())
_PASS, _FAIL = VerdictStatus.PASS, VerdictStatus.FAIL


def _state(**over: Any) -> FootingFailureState:
    flags: dict[str, Any] = {"plan_at_max": False, "depth_at_max": False, "spacing_at_min": False, "hand_sized": False}
    families: dict[str, Any] = dict.fromkeys(
        ("bearing", "one_way_shear", "punching", "flexure", "min_steel", "development"), _PASS
    )
    return FootingFailureState.model_validate(families | flags | over)


def test_limits_reached_typical() -> None:
    state = _state(plan_at_max=True, depth_at_max=True, spacing_at_min=True, bearing=_FAIL)
    assert limits_reached.fn(state, _BASIS) == Pick(FootingAction.ASK_ENGINEER)


def test_limits_reached_boundary() -> None:
    state = _state(plan_at_max=True, depth_at_max=True, spacing_at_min=False, bearing=_FAIL)
    assert limits_reached.fn(state, _BASIS) is None


def test_bearing_only_typical() -> None:
    assert bearing_only.fn(_state(bearing=_FAIL), _BASIS) == Pick(FootingAction.ENLARGE_PLAN)


def test_bearing_only_boundary() -> None:
    assert bearing_only.fn(_state(bearing=_FAIL, punching=_FAIL), _BASIS) is None  # one more failing family
    assert bearing_only.fn(_state(bearing=_FAIL, plan_at_max=True), _BASIS) is None  # the bound reached


def test_shear_only_typical() -> None:
    assert shear_only.fn(_state(punching=_FAIL), _BASIS) == Pick(FootingAction.INCREASE_DEPTH)


def test_shear_only_boundary() -> None:
    assert shear_only.fn(_state(punching=_FAIL, flexure=_FAIL), _BASIS) is None
    assert shear_only.fn(_state(punching=_FAIL, depth_at_max=True), _BASIS) is None


def test_steel_only_typical() -> None:
    assert steel_only.fn(_state(flexure=_FAIL), _BASIS) == Pick(FootingAction.REDUCE_BAR_SPACING)


def test_steel_only_boundary() -> None:
    assert steel_only.fn(_state(flexure=_FAIL, development=_FAIL), _BASIS) is None
    assert steel_only.fn(_state(flexure=_FAIL, spacing_at_min=True), _BASIS) is None


def test_development_only_typical() -> None:
    assert development_only.fn(_state(development=_FAIL), _BASIS) == Pick(FootingAction.ENLARGE_PLAN)


def test_development_only_boundary() -> None:
    assert development_only.fn(_state(development=_FAIL, bearing=_FAIL), _BASIS) is None
    assert development_only.fn(_state(development=_FAIL, plan_at_max=True), _BASIS) is None
