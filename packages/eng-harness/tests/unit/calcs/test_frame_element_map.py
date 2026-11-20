"""Calc `harness.frame_element_map` basis refusals (plan 0011 T12; spec 0011 AC29, §4.11)."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

CALC_ID = "harness.frame_element_map"
LENGTH = "compare.length_mm"
OFFSET_X = "mapping.offset_x_mm"
OFFSET_Y = "mapping.offset_y_mm"
OFFSET_Z = "mapping.offset_z_mm"
OFFSETS = (OFFSET_X, OFFSET_Y, OFFSET_Z)
FP = "model.frame_placements/1"
RS = "harness.revit_structure/1"
MDL = "mdl_00000000000000000000000000"
SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"


def _field(value: Any, unit: str = "mm", *, confirmed: bool = True) -> dict[str, Any]:
    return {"value": value, "unit": unit, "source": SRC, "confirmed": confirmed, "citation": None}


def _basis(*, length: float = 5.0, offsets: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> dict[str, Any]:
    ox, oy, oz = offsets
    return {
        "template": None,
        "fields": {
            LENGTH: _field(length),
            OFFSET_X: _field(ox),
            OFFSET_Y: _field(oy),
            OFFSET_Z: _field(oz),
        },
    }


def _ref(n: int, kind: str, *, revision: int | None = 3) -> dict[str, Any]:
    result_id = f"res_{n:026d}"
    return {
        "result_id": result_id,
        "ref": result_id,
        "kind": kind,
        "complete": True,
        "model_id": None if revision is None else MDL,
        "model_revision": revision,
        "parents": [],
        "producer_tool": "harness" if revision is None else "csi",
    }


def _point(x: float, y: float, z: float) -> dict[str, float]:
    return {"x_mm": x, "y_mm": y, "z_mm": z}


def _frame(fid: str) -> dict[str, Any]:
    return {
        "id": fid,
        "kind": "column",
        "section": "C400",
        "i": _point(0.0, 0.0, 0.0),
        "j": _point(0.0, 0.0, 3000.0),
        "rotation_deg": 0.0,
    }


def _element(uid: str, *, element_id: int = 10, type_id: int = 20) -> dict[str, Any]:
    return {
        "unique_id": uid,
        "element_id": element_id,
        "category": "column",
        "family": "Concrete Rectangular Column",
        "type_id": type_id,
        "type_name": "400 x 400",
        "level_id": 1,
        "level_name": "L1",
        "location_kind": "curve",
        "i": _point(0.0, 0.0, 0.0),
        "j": _point(0.0, 0.0, 3000.0),
        "rotation_deg": 0.0,
        "parameters": {},
    }


def _fields() -> dict[str, Any]:
    return {
        "frames": {"frames": [_frame("F1")]},
        "elements": {"frames": [_frame("U1")]},
        "structure": {"elements": [_element("U1")], "types": []},
        "links": None,
        "basis": _basis(),
    }


def _refs() -> dict[str, Any]:
    return {
        "frames": _ref(1, FP),
        "elements": _ref(2, FP, revision=4),
        "structure": _ref(3, RS, revision=5),
        "basis": _ref(9, "basis.design_basis/1", revision=None),
    }


def _input_type() -> type[CalcInput]:
    input_type = REGISTRY[CALC_ID].input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    return input_type


def _run(fields: dict[str, Any], refs: dict[str, Any]) -> dict[str, Any]:
    inp = _input_type().model_validate(fields)
    meta = InputMeta.model_validate({"refs": refs})
    dumped = REGISTRY[CALC_ID](inp, meta, TraceBuilder()).model_dump(mode="json")
    assert isinstance(dumped, dict)
    return dumped


def _refusal(fields: dict[str, Any], refs: dict[str, Any]) -> ContractError:
    with pytest.raises(ContractError) as caught:
        _run(fields, refs)
    return caught.value


def test_basis_fields_required() -> None:
    """AC29: refuse a basis without compare.length_mm or with an unconfirmed mapping.offset_* field."""
    fields = _fields()
    refs = _refs()

    missing_length = _basis()
    missing_length["fields"].pop(LENGTH)
    detail = _refusal({**fields, "basis": missing_length}, refs).detail
    assert (detail.code, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        f"basis field {LENGTH} is missing (no default)",
    )

    for path in OFFSETS:
        missing_offset = _basis()
        missing_offset["fields"].pop(path)
        detail = _refusal({**fields, "basis": missing_offset}, refs).detail
        assert (detail.code, detail.message) == (
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {path} is missing (no default)",
        )

    unconfirmed_length = _basis()
    unconfirmed_length["fields"][LENGTH] = _field(5.0, confirmed=False)
    detail = _refusal({**fields, "basis": unconfirmed_length}, refs).detail
    assert detail.message == f"basis field {LENGTH} is not confirmed"

    for path in OFFSETS:
        unconfirmed_offset = _basis()
        unconfirmed_offset["fields"][path] = _field(0.0, confirmed=False)
        detail = _refusal({**fields, "basis": unconfirmed_offset}, refs).detail
        assert detail.message == f"basis field {path} is not confirmed"

    below = _basis(length=-0.5)
    detail = _refusal({**fields, "basis": below}, refs).detail
    assert (detail.code, detail.message) == (
        ErrorCode.OUT_OF_RANGE,
        f"basis field {LENGTH} must be a number >= 0",
    )

    no_basis_ref = {k: v for k, v in refs.items() if k != "basis"}
    detail = _refusal(fields, no_basis_ref).detail
    assert (detail.code, detail.message, detail.field) == (
        ErrorCode.INVALID_ARGUMENT,
        "the basis must be a record reference",
        "basis",
    )
