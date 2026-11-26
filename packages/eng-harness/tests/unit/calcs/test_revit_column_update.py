"""Unit tests of `harness.revit_column_update` refusals, role conversion and expectation identities.

Plan 0013 T7; spec 0013 section 4.4.5 (U1 to U7). The golden cases pin the planned bodies; these tests pin the
`INVALID_ARGUMENT` refusals for map rows the inputs lack, the `_role_mm` conversion branches (including the None
branch for an unread or non-length role parameter, the golden `revit-update-unread-role` case's 'unread-means-outside'
behaviour), the inclusive U3/U4 tolerance comparison, and the `_one_identity` validator of the kind.
"""

import copy
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.quantity import Quantity
from pydantic import ValidationError

from eng_harness.calc import InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs.column_design.revit_update import (
    RevitUpdateInput,
    _role_mm,
    _within,
    revit_column_update,
)
from eng_harness.kinds.column_design import RevitColumnUpdate

KINDS = {
    "map": "harness.frame_element_map/1",
    "frames": "model.frame_placements/1",
    "sections": "model.sections/1",
    "revit": "harness.revit_structure/1",
    "revit_placements": "model.frame_placements/1",
    "changed": "harness.column_design_record/1",
    "basis": "basis.design_basis/1",
}
REFS = {name: f"res_01KRC{'0' * 20}{n}" for n, name in enumerate(KINDS, 1)}
SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"
KINDS_DATA = Path(__file__).resolve().parents[2] / "data" / "kinds" / "column_design"
SHA = "c" * 64


def _meta_without(missing: str | None = None) -> InputMeta:
    """`InputMeta` for every referenced input, optionally without one entry."""
    return InputMeta(
        refs={
            name: RefMeta(
                result_id=result_id,
                ref=result_id + "#/changed" if name == "changed" else result_id,
                kind=kind,
                complete=True,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="fixture_tool",
            )
            for name, kind, result_id in ((n, KINDS[n], REFS[n]) for n in KINDS)
            if name != missing
        }
    )


def _fields() -> dict[str, Any]:
    """A minimal valid input: one square pair reusing another type of its family."""
    return {
        "map": {
            "calc": {"id": "harness.frame_element_map", "version": 1, "content_sha256": SHA, "status": "draft"},
            "draft": True,
            "trace": {
                "calc_id": "harness.frame_element_map",
                "calc_version": "1",
                "content_sha256": SHA,
                "inputs": [],
                "constants": [],
                "steps": [],
                "outputs": [],
            },
            "pairs": [
                {
                    "frame_id": "C1",
                    "unique_id": "u-c1",
                    "element_id": 101,
                    "type_id": 11,
                    "basis": "geometry",
                    "lower_distance_mm": 0.0,
                    "upper_distance_mm": 0.0,
                }
            ],
            "ambiguous": [],
            "unmatched_frames": [],
            "unmatched_elements": [],
            "conflicts": [],
            "complete": True,
        },
        "frames": {
            "frames": [
                {
                    "id": "C1",
                    "kind": "other",
                    "section": "C40S",
                    "i": {"x_mm": 0, "y_mm": 0, "z_mm": 0},
                    "j": {"x_mm": 0, "y_mm": 0, "z_mm": 3000},
                    "story": "L1",
                    "rotation_deg": 0,
                }
            ]
        },
        "sections": {
            "frame_sections": [
                {"name": "C40S", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 400}}
            ],
            "area_sections": [],
        },
        "revit": {
            "elements": [
                {
                    "unique_id": "u-c1",
                    "element_id": 101,
                    "category": "column",
                    "family": "F1",
                    "type_id": 11,
                    "type_name": "T40old",
                    "level_id": 1,
                    "level_name": "L1",
                    "location_kind": "point",
                    "i": None,
                    "j": None,
                    "rotation_deg": 0,
                    "parameters": {},
                }
            ],
            "types": [
                {
                    "type_id": 11,
                    "family": "F1",
                    "name": "T40old",
                    "instance_ids": [101],
                    "parameters": {
                        "section_b": {"value": 400.0, "unit": "mm"},
                        "section_h": {"value": 500.0, "unit": "mm"},
                    },
                },
                {
                    "type_id": 12,
                    "family": "F1",
                    "name": "T40",
                    "instance_ids": [],
                    "parameters": {
                        "section_b": {"value": 400.0, "unit": "mm"},
                        "section_h": {"value": 400.0, "unit": "mm"},
                    },
                },
            ],
        },
        "role_statuses": {"F1": {"section_b": "reference", "section_h": "reference"}},
        "revit_placements": {
            "frames": [
                {
                    "id": "u-c1",
                    "kind": "column",
                    "section": "F1: T40old",
                    "i": {"x_mm": 0, "y_mm": 0, "z_mm": 0},
                    "j": {"x_mm": 0, "y_mm": 0, "z_mm": 3000},
                    "story": "L1",
                    "rotation_deg": 0,
                }
            ]
        },
        "changed": [],
        "basis": {
            "template": None,
            "fields": {
                "compare.length_mm": {
                    "value": 5,
                    "unit": "mm",
                    "source": SRC,
                    "confirmed": True,
                    "citation": None,
                }
            },
        },
    }


def _run(fields: dict[str, Any], meta: InputMeta | None = None) -> dict[str, Any]:
    return revit_column_update(
        RevitUpdateInput.model_validate(fields), meta or _meta_without(), TraceBuilder()
    ).model_dump(mode="json")


def test_fixture_reuses_type_12() -> None:
    body = _run(_fields())
    assert [(row["unique_id"], row["type_id"]) for row in body["assignments"]] == [("u-c1", "12")]
    assert body["complete"] is True


def test_missing_frame_refused() -> None:
    fields = _fields()
    fields["frames"] = {"frames": []}
    with pytest.raises(ContractError) as caught:
        _run(fields)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        "frames",
        "frame C1 of the map is not in the frames",
    )


def test_missing_section_refused() -> None:
    fields = _fields()
    fields["frames"]["frames"][0]["section"] = "NOPE"
    with pytest.raises(ContractError) as caught:
        _run(fields)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        "sections",
        "section NOPE of column C1 is not in the sections",
    )


def test_missing_element_refused() -> None:
    fields = _fields()
    fields["revit"]["elements"] = []
    with pytest.raises(ContractError) as caught:
        _run(fields)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        "revit",
        "element u-c1 of the map is not in the revit structure",
    )


def test_missing_type_refused() -> None:
    fields = _fields()
    fields["revit"]["types"] = []
    with pytest.raises(ContractError) as caught:
        _run(fields)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        "revit",
        "type 11 of element u-c1 is not in the revit structure",
    )


def test_missing_revit_placement_refused() -> None:
    """U5 looks up the placement row only for a written non-square pair, and refuses when it is missing."""
    fields = _fields()
    fields["sections"]["frame_sections"][0]["shape"] = {"type": "rectangular", "b_mm": 400, "h_mm": 600}
    fields["revit"]["types"][1]["parameters"]["section_h"] = {"value": 600.0, "unit": "mm"}
    fields["revit_placements"] = {"frames": []}
    with pytest.raises(ContractError) as caught:
        _run(fields)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        "revit_placements",
        "element u-c1 of the map is not in the revit placements",
    )


@pytest.mark.parametrize("name", sorted(KINDS))
def test_missing_reference_refused(name: str) -> None:
    with pytest.raises(ContractError) as caught:
        _run(_fields(), _meta_without(name))
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        name,
        f"{name} must be a record reference",
    )


@pytest.mark.parametrize(
    ("value", "unit", "want"),
    [
        (400.0, "mm", Fraction(400)),
        (50.0, "cm", Fraction(500)),
        (0.5, "m", Fraction(500)),
        (1.0, "in", Fraction("25.4")),
    ],
)
def test_role_mm_converts_lengths(value: float, unit: str, want: Fraction) -> None:
    assert _role_mm(Quantity(value, unit)) == want


@pytest.mark.parametrize(
    "param",
    [None, "not read", 400, Quantity(30.0, "MPa"), Quantity(90.0, "deg")],
    ids=["missing", "string", "int", "pressure", "angle"],
)
def test_role_mm_rejects_unread_or_non_length(param: Any) -> None:
    """The None branch: a missing, non-Quantity or non-length role never matches ('unread-means-outside')."""
    assert _role_mm(param) is None


@pytest.mark.parametrize(
    ("actual", "want"),
    [
        (Fraction(400), True),
        (Fraction(405), True),
        (Fraction(395), True),
        (Fraction(811, 2), False),
        (Fraction(789, 2), False),
    ],
    ids=["exact", "at-plus", "at-minus", "over-plus", "over-minus"],
)
def test_within_is_inclusive(actual: Fraction, want: bool) -> None:
    assert _within(actual, Fraction(400), Fraction(5)) is want


def _kinds_payload(name: str) -> dict[str, Any]:
    data = json.loads((KINDS_DATA / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.mark.parametrize(
    "row",
    [
        {"unique_id": "u1", "type_id": "t1", "family": None, "type_name": None},
        {"unique_id": "u2", "type_id": None, "family": "F1", "type_name": "T1"},
    ],
    ids=["reuse", "new-type"],
)
def test_expectation_single_identity_valid(row: dict[str, Any]) -> None:
    payload = _kinds_payload("revit_column_update.json")
    payload["expected"]["elements"] = [row]
    RevitColumnUpdate.model_validate(payload)


@pytest.mark.parametrize(
    "row",
    [
        {"unique_id": "u-both", "type_id": "t1", "family": "F1", "type_name": "T1"},
        {"unique_id": "u-neither", "type_id": None, "family": None, "type_name": None},
        {"unique_id": "u-half", "type_id": None, "family": "F1", "type_name": None},
        {"unique_id": "u-mixed", "type_id": "t1", "family": "F1", "type_name": None},
    ],
    ids=["both", "neither", "family-only", "type-id-plus-family"],
)
def test_expectation_identity_refused(row: dict[str, Any]) -> None:
    """`_one_identity`: an expectation carries type_id, or family and type_name, not both and not neither."""
    payload = _kinds_payload("revit_column_update.json")
    payload["expected"]["elements"] = [row]
    with pytest.raises(ValidationError, match="give type_id, or family and type_name"):
        RevitColumnUpdate.model_validate(payload)


def test_invalid_fixture_names_both_identity_validators() -> None:
    """The invalid kinds fixture pins `_type_or_name` (assignment) and `_one_identity` (expectation)."""
    payload = _kinds_payload("revit_column_update.invalid.json")
    with pytest.raises(ValidationError, match="give type_id or new_type_name"):
        RevitColumnUpdate.model_validate(payload)
    with pytest.raises(ValidationError, match="give type_id, or family and type_name"):
        RevitColumnUpdate.model_validate(copy.deepcopy(payload))
