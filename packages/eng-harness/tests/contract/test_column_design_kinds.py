"""Contract tests of the column-workflow kinds (plan 0013 T1; spec 0013 AC3, section 4.2)."""

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from eng_harness.kinds import COLUMN_DESIGN_KINDS
from eng_harness.kinds.column_design import COLUMN_DESIGN_KINDS as KIND_MODELS
from eng_harness.kinds.column_design import ColumnCheckItems

DATA = Path(__file__).resolve().parents[1] / "data" / "kinds" / "column_design"
KINDS = {
    "column_selection": "harness.column_selection/1",
    "column_check_items": "harness.column_check_items/1",
    "column_review": "harness.column_review/1",
    "column_match": "harness.column_match/1",
    "generated_change_set": "harness.generated_change_set/1",
    "revit_column_update": "harness.revit_column_update/1",
    "revit_column_readback": "harness.revit_column_readback/1",
    "column_design_record": "harness.column_design_record/1",
}


def _load(name: str) -> dict[str, Any]:
    data = json.loads((DATA / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_kind_fixtures() -> None:
    """AC3: each kind of section 4.2 has one valid fixture and one invalid fixture, and is registered on the package."""
    assert COLUMN_DESIGN_KINDS is KIND_MODELS
    assert set(COLUMN_DESIGN_KINDS) == set(KINDS.values())
    assert all(name.startswith("harness.") for name in COLUMN_DESIGN_KINDS)
    for stem, kind in KINDS.items():
        model = COLUMN_DESIGN_KINDS[kind]
        payload = _load(f"{stem}.json")
        parsed = model.model_validate(payload)
        assert model.model_validate(parsed.model_dump(mode="json", exclude_none=False)) == parsed
        with pytest.raises(ValidationError, match="Extra inputs"):
            model.model_validate({**payload, "unknown_field": 1})
        with pytest.raises(ValidationError):
            model.model_validate(_load(f"{stem}.invalid.json"))


_AXIAL_FLEXURE_ID = "aci318_14.22_4_1_1.axial_flexure_uniaxial"
_BARE_REF = "res_00000000000000000000000001#/fields/materials.concrete_fc_MPa/value"
_VALID_REF = {"$ref": _BARE_REF}


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("Pu_kN", _BARE_REF),
        ("fc_MPa", _BARE_REF),
        ("n_bars_b", 3.0),
        ("n_bars_h", 3.0),
        ("transverse_kind", "spiral"),
        ("transverse_kind", 1),
        ("transverse_kind", _VALID_REF),
        ("fc_MPa", 30.0),
        ("fy_MPa", 420.0),
        ("k_factor", 1.0),
        ("ratio_limit", 1.0),
        ("fc_MPa", {"$ref": "not_a_ref"}),
        ("fc_MPa", {"$ref": _BARE_REF, "extra": 1}),
        ("fc_MPa", {"ref": _BARE_REF}),
        ("Pu_kN", _VALID_REF),
        ("n_bars_b", _VALID_REF),
        ("Pu_kN", "1200"),
        ("n_bars_b", "3"),
        ("Pu_kN", True),
        ("n_bars_b", True),
        ("fc_MPa", False),
        ("transverse_kind", False),
        ("Pu_kN", math.nan),
        ("Pu_kN", math.inf),
        ("Pu_kN", -math.inf),
        ("Pu_kN", "tied"),
    ],
)
def test_check_item_inputs_are_ref_objects_or_literals(field_name: str, bad_value: Any) -> None:
    """Plan 0013 T3 (B-578): ColumnCheckItems enforces field-aware literal and $ref shapes and round-trips $ref."""
    valid = _load("column_check_items.json")
    parsed = ColumnCheckItems.model_validate(valid)
    dumped = parsed.model_dump(mode="json", exclude_none=False)
    af_inputs = dumped["items"][_AXIAL_FLEXURE_ID][0]["inputs"]
    assert af_inputs["fc_MPa"] == _VALID_REF
    assert type(af_inputs["n_bars_b"]) is int
    assert type(af_inputs["n_bars_h"]) is int

    invalid = copy.deepcopy(valid)
    invalid["items"][_AXIAL_FLEXURE_ID][0]["inputs"][field_name] = bad_value
    with pytest.raises(ValidationError):
        ColumnCheckItems.model_validate(invalid)
