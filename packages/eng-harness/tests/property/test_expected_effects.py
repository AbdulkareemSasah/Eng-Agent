"""Expected-effects properties (plan 0007 T3; spec 0007 AC8): a permutation of the items gives the same effects."""

import copy
from typing import Any

from golden.edit_cycle import load_cases
from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.calc import InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs.edit_cycle.expected_effects import EffectsInput, expected_effects

MDL = "mdl_00000000000000000000000000"
STATE = ("sections", "loads", "restraints")
KINDS = {
    "check": "harness.change_set_check/1",
    "change_set": "basis.engineer_input/1",
    "sections": "model.sections/1",
    "loads": "model.load_set/1",
    "restraints": "model.joint_restraints/1",
    "basis": "basis.design_basis/1",
}
CASES = load_cases("effects")
MULTI = ("effects-assignments", "effects-combination-replace", "effects-loads", "effects-restraints")


def _effects(raw: dict[str, Any], refs: dict[str, str]) -> list[dict[str, Any]]:
    meta = InputMeta(
        refs={
            name: RefMeta(
                result_id=result_id,
                kind=KINDS[name],
                complete=True,
                model_id=MDL if name in STATE else None,
                model_revision=3 if name in STATE else None,
                parents=(),
                producer_tool="csi",
            )
            for name, result_id in refs.items()
        }
    )
    body = expected_effects(EffectsInput.model_validate(raw), meta, TraceBuilder())
    effects: list[dict[str, Any]] = body.model_dump(mode="json")["effects"]
    return effects


@settings(max_examples=60, deadline=None)
@given(data=st.data())
def test_order_independent(data: st.DataObject) -> None:
    """AC8: the items of the change set, of the check and of the accepted ids in any order: the same effects."""
    case = CASES[data.draw(st.sampled_from(MULTI))]
    raw = copy.deepcopy(case.input)
    permuted = copy.deepcopy(raw)
    permuted["change_set"] = {"items": data.draw(st.permutations(raw["change_set"]["items"]))}
    permuted["check"]["resolved"] = data.draw(st.permutations(raw["check"]["resolved"]))
    permuted["approval_items"] = data.draw(st.permutations(raw["approval_items"]))
    assert _effects(permuted, case.refs) == _effects(raw, case.refs) == case.expected["effects"]
