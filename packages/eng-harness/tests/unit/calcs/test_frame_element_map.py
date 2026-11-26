"""Calc `harness.frame_element_map` basis refusals (plan 0011 T12; spec 0011 AC29, §4.11)."""

from pathlib import Path
from typing import Any

import pytest
from eng_contract.envelope import Provenance
from eng_contract.errors import ContractError, ErrorCode, ErrorDetail
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.params import InputPolicy, validate_input
from eng_contract.store import LocationClass, ResultStore, Workspace

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.frame_element_map import FrameElementMapInput

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


def _placement(fid: str, x: float) -> dict[str, Any]:
    return {**_frame(fid), "i": _point(x, 0.0, 0.0), "j": _point(x, 0.0, 3000.0)}


def test_offset_translation_is_exact() -> None:
    """§4.11 M1/M2 (0003 P2): translated ends stay exact fractions, so float rounding cannot pull d² onto t².

    In units of 2^-46 mm: 1234.5678 = 86874985688181456, 100.7 = 7086132538690765, 1340.2678 = 94312961947760544,
    so dx = 94312961947760544 - 93961118226872221 = 351843720888323 > 5 = 351843720888320 and d² > t² = 25.
    """
    fields = {
        **_fields(),
        "frames": {"frames": [_placement("F1", 1234.5678)]},
        "elements": {"frames": [_placement("U1", 1340.2678)]},
        "basis": _basis(offsets=(100.7, 0.0, 0.0)),
    }
    out = _run(fields, _refs())
    assert out["pairs"] == []
    assert out["unmatched_frames"] == [{"frame_id": "F1"}]
    assert out["unmatched_elements"] == [{"unique_id": "U1"}]


def test_link_to_frame_outside_frames_is_ignored() -> None:
    """§4.11 M4: only a link naming a frame of `frames` can conflict; a beam link beside selected columns does not."""
    fields = {**_fields(), "links": {"U1": "F1", "U9": "B7"}}
    out = _run(fields, _refs())
    assert out["conflicts"] == []
    assert [(p["frame_id"], p["unique_id"], p["basis"]) for p in out["pairs"]] == [("F1", "U1", "both")]


def test_basis_non_numeric_refused() -> None:
    """§4.11 / 0003 §4.4: a basis field with a non-numeric value is refused (a wrong unit fails basis validation)."""
    fields = _fields()
    refs = _refs()
    for path in (LENGTH, *OFFSETS):
        not_number = _basis()
        not_number["fields"][path] = _field("five")
        detail = _refusal({**fields, "basis": not_number}, refs).detail
        assert detail.code == ErrorCode.INVALID_ARGUMENT
        assert detail.message.startswith(f"basis field {path} must be a number")


@pytest.mark.parametrize("path", [LENGTH, *OFFSETS])
@pytest.mark.parametrize("defect", ["missing", "unconfirmed", "non-numeric"])
def test_basis_refusal_detail(path: str, defect: str) -> None:
    fields = _fields()
    basis_fields = fields["basis"]["fields"]
    if defect == "missing":
        del basis_fields[path]
        reason = "is missing (no default)"
    elif defect == "unconfirmed":
        basis_fields[path]["confirmed"] = False
        reason = "is not confirmed"
    else:
        basis_fields[path]["value"] = "five"
        reason = "must be a number >= 0" if path == LENGTH else "must be a number"

    assert _refusal(fields, _refs()).detail == ErrorDetail(
        code=ErrorCode.INVALID_ARGUMENT,
        message=f"basis field {path} {reason}",
        field=f"basis.fields.{path}",
        hint=f"set and confirm {path} in the design basis",
        retryable=False,
    )


@pytest.mark.parametrize("path", [LENGTH, *OFFSETS])
def test_calc_refuses_wrong_basis_unit(path: str) -> None:
    inp = FrameElementMapInput.model_validate(_fields())
    # DesignBasis validation rejects the unit first. Copy the validated models to exercise the calc's own guard.
    basis_fields = inp.basis.fields.copy()
    basis_fields[path] = basis_fields[path].model_copy(update={"unit": "m"})
    basis = inp.basis.model_copy(update={"fields": basis_fields})
    meta = InputMeta.model_validate({"refs": _refs()})
    with pytest.raises(ContractError) as caught:
        REGISTRY[CALC_ID](inp.model_copy(update={"basis": basis}), meta, TraceBuilder())
    assert caught.value.detail == ErrorDetail(
        code=ErrorCode.INVALID_ARGUMENT,
        message=f"basis field {path} must be in mm, not m",
        field=f"basis.fields.{path}",
        hint=f"set and confirm {path} in the design basis",
        retryable=False,
    )


def test_negative_length_refusal_detail() -> None:
    fields = {**_fields(), "basis": _basis(length=-0.5)}
    assert _refusal(fields, _refs()).detail == ErrorDetail(
        code=ErrorCode.OUT_OF_RANGE,
        message="basis field compare.length_mm must be a number >= 0",
        field="basis.fields.compare.length_mm",
        expected={"min": 0, "unit": "mm"},
        received=-0.5,
        hint="set and confirm compare.length_mm in the design basis",
        retryable=False,
    )


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("frames", "a placement must be a record reference"),
        ("elements", "a placement must be a record reference"),
        ("structure", "a placement must be a record reference"),
        ("basis", "the basis must be a record reference"),
    ],
)
def test_missing_reference_detail(name: str, message: str) -> None:
    refs = _refs()
    del refs[name]
    assert _refusal(_fields(), refs).detail == ErrorDetail(
        code=ErrorCode.INVALID_ARGUMENT,
        message=message,
        field=name,
        retryable=False,
    )


@pytest.mark.parametrize(
    ("name", "wrong_name", "expected_kind", "actual_kind"),
    [
        ("frames", "basis", FP, "basis.design_basis/1"),
        ("elements", "basis", FP, "basis.design_basis/1"),
        ("structure", "frames", RS, FP),
        ("basis", "frames", "basis.design_basis/1", FP),
    ],
)
def test_wrong_reference_kind_detail(
    tmp_path: Path, name: str, wrong_name: str, expected_kind: str, actual_kind: str
) -> None:
    clock = FixedClock(1, 1)
    store = ResultStore(
        Workspace(root=tmp_path, classification=LocationClass.LOCAL),
        HARNESS_KINDS,
        SeededIdSource(b"frame-element-map", clock),
        clock,
    )
    producer = Provenance(tool="harness", tool_version="test", inputs={}, started_at=clock.now(), duration_ms=0)
    fields = _fields()
    refs = {key: store.put(ref["kind"], fields[key], producer).result_id for key, ref in _refs().items()}
    refs[name] = refs[wrong_name]
    with pytest.raises(ContractError) as caught:
        validate_input(
            _input_type(),
            {key: {"$ref": result_id} for key, result_id in refs.items()},
            source=store,
            current_revision=lambda _: None,
            policy=InputPolicy(require_refs=True),
        )
    assert caught.value.detail == ErrorDetail(
        code=ErrorCode.REF_KIND_MISMATCH,
        message=f"result kind {actual_kind} is not accepted",
        field=name,
        expected={"kinds": [expected_kind]},
        received=actual_kind,
        retryable=False,
    )


@pytest.mark.parametrize("limit", [0.0, 5.0])
def test_match_at_inclusive_length_limit(limit: float) -> None:
    # Coincident ends at zero, and a synthetic 3-4-5 triangle at the positive limit.
    x, y = (0.0, 0.0) if limit == 0.0 else (3.0, 4.0)
    element = {**_frame("U1"), "i": _point(x, y, 0.0), "j": _point(x, y, 3000.0)}
    fields = {**_fields(), "elements": {"frames": [element]}, "basis": _basis(length=limit)}
    pairs = _run(fields, _refs())["pairs"]
    assert [(p["frame_id"], p["unique_id"], p["lower_distance_mm"], p["upper_distance_mm"]) for p in pairs] == [
        ("F1", "U1", limit, limit)
    ]


def test_trace_records_basis_values_units_and_pointers() -> None:
    fields = {**_fields(), "basis": _basis(offsets=(-1.5, 0.0, 2.5))}
    refs = _refs()
    trace = TraceBuilder()
    definition = REGISTRY[CALC_ID]
    definition(_input_type().model_validate(fields), InputMeta.model_validate({"refs": refs}), trace)
    inputs = trace.build(definition, REGISTRY.content_hash(CALC_ID)).inputs
    basis_id = refs["basis"]["result_id"]
    entries = {entry.name: (entry.value, entry.unit, entry.ref) for entry in inputs}
    assert entries["compare_length_mm"] == (5.0, "mm", f"{basis_id}#/fields/compare.length_mm")
    assert entries["mapping_offset_x_mm"] == (-1.5, "mm", f"{basis_id}#/fields/mapping.offset_x_mm")
    assert entries["mapping_offset_y_mm"] == (0.0, "mm", f"{basis_id}#/fields/mapping.offset_y_mm")
    assert entries["mapping_offset_z_mm"] == (2.5, "mm", f"{basis_id}#/fields/mapping.offset_z_mm")
