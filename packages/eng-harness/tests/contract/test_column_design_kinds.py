"""Contract tests of the column-workflow kinds (plan 0013 T1, T4; spec 0013 AC3, AC8, section 4.2)."""

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from eng_harness.kinds import COLUMN_DESIGN_KINDS
from eng_harness.kinds.column_design import COLUMN_DESIGN_KINDS as KIND_MODELS
from eng_harness.kinds.column_design import ColumnCheckItems, ColumnReview

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
    with pytest.raises(ValidationError, match="status is NEEDS_ENGINEER when not_checked is set"):
        ColumnReview.model_validate(_load("column_review.invalid.json"))


def test_column_review_members_and_changes_rules() -> None:
    """Amendment B-577: ColumnReview carries keyed members and column-specific S5 change rows."""
    base = _load("column_review.json")
    # Invalid code_pack check_id pattern
    bad_check = copy.deepcopy(base)
    bad_check["members"][0]["check_id"] = "host.steel_design_ratio"
    with pytest.raises(ValidationError, match="code_pack pattern"):
        ColumnReview.model_validate(bad_check)
    # Unsorted / duplicate members
    bad_order = copy.deepcopy(base)
    bad_order["members"] = list(reversed(bad_order["members"]))
    with pytest.raises(ValidationError, match="members must be sorted and unique"):
        ColumnReview.model_validate(bad_order)
    # Unknown column in members
    bad_col = copy.deepcopy(base)
    bad_col["members"].append(
        {"frame_id": "C9", "source": "host", "check_id": "host.steel_design_ratio", "status": "PASS", "ratio": 0.1}
    )
    with pytest.raises(ValidationError, match="members name unknown columns"):
        ColumnReview.model_validate(bad_col)
    # Unsorted columns
    two_cols = copy.deepcopy(base)
    col_c2 = copy.deepcopy(two_cols["columns"][0]) | {"frame_id": "C2"}
    two_cols["columns"] = [col_c2, two_cols["columns"][0]]
    with pytest.raises(ValidationError, match="columns must be sorted and unique"):
        ColumnReview.model_validate(two_cols)
    # failing / attention mismatch
    bad_fail = copy.deepcopy(base)
    bad_fail["failing"] = ["C1"]
    with pytest.raises(ValidationError, match="failing must list the FAIL columns"):
        ColumnReview.model_validate(bad_fail)
    bad_attn = copy.deepcopy(base)
    bad_attn["attention"] = ["C1"]
    with pytest.raises(ValidationError, match="attention must list the NEEDS_ENGINEER and ERROR columns"):
        ColumnReview.model_validate(bad_attn)
    # Valid failing + attention + changes
    valid_changes = copy.deepcopy(base)
    valid_changes["columns"] = [
        {**base["columns"][0], "frame_id": "C1", "status": "FAIL", "host_status": "FAIL"},
        {**base["columns"][0], "frame_id": "C2", "status": "NEEDS_ENGINEER", "code_status": "NEEDS_ENGINEER"},
    ]
    valid_changes["failing"] = ["C1"]
    valid_changes["attention"] = ["C2"]
    valid_changes["changes"] = {
        "newly_failing": [
            {
                "frame_id": "C1",
                "source": "host",
                "check_id": "host.steel_design_ratio",
                "previous_status": "PASS",
                "status": "FAIL",
                "previous_ratio": 0.5,
                "ratio": 1.1,
            }
        ],
        "newly_passing": [
            {
                "frame_id": "C1",
                "source": "code_pack",
                "check_id": "aci318_14.22_4_2_1.max_axial_strength",
                "previous_status": "FAIL",
                "status": "PASS",
                "previous_ratio": 1.2,
                "ratio": 0.6,
            }
        ],
        "other_changes": [
            {
                "frame_id": "C2",
                "source": "code_pack",
                "check_id": "aci318_14.22_4_2_1.max_axial_strength",
                "previous_status": "NEEDS_ENGINEER",
                "status": "PASS",
                "previous_ratio": None,
                "ratio": 0.4,
            }
        ],
        "appeared": [
            {
                "frame_id": "C2",
                "source": "host",
                "check_id": "host.concrete_design_ratio",
                "status": "NEEDS_ENGINEER",
                "ratio": None,
            }
        ],
        "disappeared": [],
    }
    ColumnReview.model_validate(valid_changes)
    # S5 change classification errors
    for bucket, prev_s, curr_s in (
        ("newly_failing", "FAIL", "FAIL"),
        ("newly_failing", "PASS", "PASS"),
        ("newly_passing", "PASS", "PASS"),
        ("newly_passing", "FAIL", "FAIL"),
        ("other_changes", "PASS", "PASS"),
        ("other_changes", "PASS", "FAIL"),
        ("other_changes", "FAIL", "PASS"),
    ):
        bad_change = copy.deepcopy(base)
        bad_change["changes"][bucket] = [
            {
                "frame_id": "C1",
                "source": "host",
                "check_id": "host.steel_design_ratio",
                "previous_status": prev_s,
                "status": curr_s,
                "previous_ratio": 0.5,
                "ratio": 0.6,
            }
        ]
        with pytest.raises(ValidationError, match=f"a row of {bucket} does not fit that list"):
            ColumnReview.model_validate(bad_change)
    # Unsorted appeared
    bad_appeared = copy.deepcopy(valid_changes)
    row_a = copy.deepcopy(bad_appeared["changes"]["appeared"][0])
    row_b = row_a | {"frame_id": "C1"}
    bad_appeared["changes"]["appeared"] = [row_a, row_b]
    with pytest.raises(ValidationError, match="appeared must be sorted and unique"):
        ColumnReview.model_validate(bad_appeared)


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
