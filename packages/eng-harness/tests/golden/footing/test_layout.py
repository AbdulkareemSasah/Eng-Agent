"""Golden cases and contract of harness.footing_layout (plan 0010 T5; spec 0010 AC8, section 4.4.3)."""

import copy
import math
import sys
from collections.abc import Mapping
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from eng_contract.canonical import canonical_json
from eng_contract.envelope import FailureEnvelope, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.basis import BasisField, DesignBasis
from eng_contract.store import LocationClass, ResultStore, Workspace
from pydantic import JsonValue

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.footing.layout import BASIS_FIELDS, LayoutInput, footing_layout
from eng_harness.kinds.footing import FootingDesign, FootingDims, FootingSubjects
from eng_harness.ports import RunClass

from . import FootingGoldenCase, input_meta, load_cases

CALC_ID = "harness.footing_layout"
KINDS = {
    "dims": "harness.footing_dims/1",
    "subjects": "harness.footing_subjects/1",
    "basis": "basis.design_basis/1",
}
STEMS = [
    "layout-depth-out-of-range",
    "layout-span-below-and-multiple",
    "layout-span-zero-and-negative",
    "layout-x-bottom-top",
    "layout-y-bottom-base",
]
DIGEST = "ab" * 32
_SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"
# L2 binary64 roundoff bound: As = n * pi * db^2 / 4 = coeff * pi.
# In IEEE 754 binary64 (unit roundoff u = 2^-53 = sys.float_info.epsilon / 2), math.pi approximates pi to within u,
# and evaluating coeff * pi adds at most 3u more relative error across float operations (1u for single final float).
# Bound 4u = 2 * sys.float_info.epsilon = 2^-51 covers both true value and any conforming binary64 evaluation order.
_AREA_REL_TOL = 2.0 * sys.float_info.epsilon
_AREA_KEYS = (("As_x_mm2", "As_x_pi_coeff"), ("As_y_mm2", "As_y_pi_coeff"))


def _calc_meta(calc_id: str) -> dict[str, Any]:
    return {
        "calc": {"id": calc_id, "version": 1, "content_sha256": DIGEST, "status": "draft"},
        "draft": True,
        "trace": {
            "calc_id": calc_id,
            "calc_version": "1",
            "content_sha256": DIGEST,
            "inputs": [],
            "constants": [],
            "steps": [],
            "outputs": [],
        },
    }


def _run(case: FootingGoldenCase, trace: TraceBuilder | None = None, **changes: Any) -> dict[str, Any]:
    raw = copy.deepcopy(case.input) | changes
    raw["dims"] = _calc_meta("harness.footing_plan_size") | raw["dims"]
    raw["subjects"] = _calc_meta("harness.footing_subjects") | raw["subjects"]
    result = footing_layout(LayoutInput.model_validate(raw), input_meta(case.refs, KINDS), trace or TraceBuilder())
    return result.model_dump(mode="json")


def _basis(overrides: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "reinforcement.bar_diameter_mm": {
            "value": 16.0,
            "unit": "mm",
            "source": _SRC,
            "confirmed": True,
            "citation": None,
        },
        "reinforcement.bottom_layer": {
            "value": "x_bottom",
            "unit": None,
            "source": _SRC,
            "confirmed": True,
            "citation": None,
        },
        "durability.cover_footing_mm": {
            "value": 75.0,
            "unit": "mm",
            "source": _SRC,
            "confirmed": True,
            "citation": None,
        },
        "foundation.reaction_point": {
            "value": "top_of_footing",
            "unit": None,
            "source": _SRC,
            "confirmed": True,
            "citation": None,
        },
    }
    for path, patch in (overrides or {}).items():
        fields[path] = fields[path] | patch
    return {"template": None, "fields": fields}


def _row_mismatch(actual_row: Mapping[str, Any], expected_row: Mapping[str, Any]) -> dict[str, Any] | None:
    area_out_keys = {out_k for out_k, _ in _AREA_KEYS}
    coeff_keys = {coeff_k for _, coeff_k in _AREA_KEYS}
    actual_rest = {k: v for k, v in actual_row.items() if k not in area_out_keys}
    expected_rest = {k: v for k, v in expected_row.items() if k not in coeff_keys}
    if actual_rest != expected_rest:
        return {"actual": dict(actual_row), "expected": dict(expected_row)}
    for out_key, coeff_key in _AREA_KEYS:
        if out_key not in actual_row or coeff_key not in expected_row:
            return {"actual": dict(actual_row), "expected": dict(expected_row)}
        actual_area = actual_row[out_key]
        coeff = expected_row[coeff_key]
        if coeff == 0:
            if actual_area != 0.0:
                return {"field": out_key, "actual": actual_area, "expected": 0.0}
        else:
            ref_area = coeff * math.pi
            if abs(actual_area - ref_area) > _AREA_REL_TOL * ref_area:
                return {"field": out_key, "actual": actual_area, "expected_pi_coeff": coeff}
    return None


def test_golden_cases() -> None:
    """AC8 and plan T5: golden cases for both layers, both reaction points, exact multiple, below s, <= 0, and L3."""
    cases = load_cases("layout")
    assert sorted(cases) == STEMS
    failures: dict[str, Any] = {}
    for stem, case in cases.items():
        if "error_code" in case.expected:
            with pytest.raises(ContractError) as caught:
                _run(case)
            if (caught.value.detail.code.value, caught.value.detail.field) != (
                case.expected["error_code"],
                case.expected["field"],
            ):
                failures[stem] = (caught.value.detail.code.value, caught.value.detail.field)
        else:
            actual = _run(case)
            actual_rows = actual.get("footings", [])
            expected_rows = case.expected["footings"]
            if set(actual) != set(case.expected) or len(actual_rows) != len(expected_rows):
                failures[stem] = actual
            elif row_diffs := [
                diff
                for act_row, exp_row in zip(actual_rows, expected_rows, strict=True)
                if (diff := _row_mismatch(act_row, exp_row)) is not None
            ]:
                failures[stem] = row_diffs
    assert failures == {}


def test_trace_records_inputs_constants_and_steps() -> None:
    case = load_cases("layout")["layout-x-bottom-top"]
    trace = TraceBuilder()
    _run(case, trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    inputs = {item.name: item for item in built.inputs}
    assert inputs["dims"].value == 2
    assert inputs["dims"].ref == case.refs["dims"]
    assert inputs["subjects"].value == 2
    assert inputs["subjects"].ref == case.refs["subjects"]
    assert (inputs["bar_diameter_mm"].value, inputs["bar_diameter_mm"].unit) == (16.0, "mm")
    assert inputs["bar_diameter_mm"].ref == f"{case.refs['basis']}#/fields/reinforcement.bar_diameter_mm"
    assert (inputs["bottom_layer"].value, inputs["bottom_layer"].unit) == ("x_bottom", None)
    assert (inputs["cover_footing_mm"].value, inputs["cover_footing_mm"].unit) == (75.0, "mm")
    assert (inputs["reaction_point"].value, inputs["reaction_point"].unit) == ("top_of_footing", None)
    constants = {c.name: c.cited for c in built.constants}
    assert constants["pi"].value == math.pi
    assert "circle" in constants["pi"].source
    assert {
        name: constants[name].value
        for name in ("zero_mm", "zero_count", "zero_area", "one", "two", "three", "four", "max_safe_int")
    } == {
        "zero_mm": 0,
        "zero_count": 0,
        "zero_area": 0.0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "max_safe_int": 2**53 - 1,
    }
    steps = {step.name: step for step in built.steps}
    assert [(n, steps[n].value) for n in ("footings", "width_too_small")] == [("footings", 2), ("width_too_small", 0)]
    assert steps["footings"].source == "spec 0010 4.4.3 L1 to L5"
    assert steps["width_too_small"].source == "spec 0010 4.4.3 L1"
    assert built.outputs == ["footings"]


@pytest.mark.parametrize(
    ("path", "patch", "code"),
    [
        ("reinforcement.bar_diameter_mm", {"confirmed": False}, ErrorCode.INVALID_ARGUMENT),
        ("reinforcement.bar_diameter_mm", {"value": "16"}, ErrorCode.INVALID_ARGUMENT),
        ("reinforcement.bar_diameter_mm", {"value": True}, ErrorCode.INVALID_ARGUMENT),
        ("reinforcement.bar_diameter_mm", {"value": 0.0}, ErrorCode.OUT_OF_RANGE),
        ("reinforcement.bar_diameter_mm", {"value": -16.0}, ErrorCode.OUT_OF_RANGE),
        ("durability.cover_footing_mm", {"confirmed": False}, ErrorCode.INVALID_ARGUMENT),
        ("durability.cover_footing_mm", {"value": False}, ErrorCode.INVALID_ARGUMENT),
        ("durability.cover_footing_mm", {"value": -0.5}, ErrorCode.OUT_OF_RANGE),
        ("reinforcement.bottom_layer", {"confirmed": False}, ErrorCode.INVALID_ARGUMENT),
        ("reinforcement.bottom_layer", {"unit": "mm"}, ErrorCode.UNIT_MISMATCH),
        ("reinforcement.bottom_layer", {"value": 1}, ErrorCode.INVALID_ARGUMENT),
        ("reinforcement.bottom_layer", {"value": "z_bottom"}, ErrorCode.INVALID_ARGUMENT),
        ("foundation.reaction_point", {"confirmed": False}, ErrorCode.INVALID_ARGUMENT),
        ("foundation.reaction_point", {"unit": "mm"}, ErrorCode.UNIT_MISMATCH),
        ("foundation.reaction_point", {"value": True}, ErrorCode.INVALID_ARGUMENT),
        ("foundation.reaction_point", {"value": "mid_depth"}, ErrorCode.INVALID_ARGUMENT),
    ],
)
def test_basis_fields_are_checked(path: str, patch: dict[str, Any], code: ErrorCode) -> None:
    case = load_cases("layout")["layout-x-bottom-top"]
    with pytest.raises(ContractError) as caught:
        _run(case, basis=_basis({path: patch}))
    assert caught.value.detail.code is code
    assert caught.value.detail.field == "basis"


@pytest.mark.parametrize("path", ["reinforcement.bar_diameter_mm", "durability.cover_footing_mm"])
def test_length_basis_unit_mismatch_is_refused(path: str) -> None:
    case = load_cases("layout")["layout-x-bottom-top"]
    raw_basis = _basis()
    fields = {key: BasisField.model_validate(val) for key, val in raw_basis["fields"].items() if key != path}
    fields[path] = BasisField.model_construct(value=16.0, unit="deg", source=_SRC, confirmed=True, citation=None)
    inp = LayoutInput.model_construct(
        dims=FootingDims.model_validate(_calc_meta("harness.footing_plan_size") | case.input["dims"]),
        subjects=FootingSubjects.model_validate(_calc_meta("harness.footing_subjects") | case.input["subjects"]),
        basis=DesignBasis.model_construct(template=None, fields=fields),
    )
    with pytest.raises(ContractError) as caught:
        footing_layout(inp, input_meta(case.refs, KINDS), TraceBuilder())
    assert caught.value.detail.code is ErrorCode.UNIT_MISMATCH
    assert caught.value.detail.field == "basis"


@pytest.mark.parametrize("missing", BASIS_FIELDS)
def test_missing_basis_field_is_refused(missing: str) -> None:
    assert BASIS_FIELDS == (
        "reinforcement.bar_diameter_mm",
        "reinforcement.bottom_layer",
        "durability.cover_footing_mm",
        "foundation.reaction_point",
    )
    case = load_cases("layout")["layout-x-bottom-top"]
    basis = _basis()
    del basis["fields"][missing]
    with pytest.raises(ContractError) as caught:
        _run(case, basis=basis)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "basis"


def test_zero_cover_is_accepted() -> None:
    case = load_cases("layout")["layout-span-below-and-multiple"]
    dims = copy.deepcopy(case.input["dims"])
    # J1: Lx=316, Ly=200, h=300, s=200; c=0, db=16:
    # span_x=184 (n_x=2, s_x=184), span_y=300 (n_y=ceil(300/200)+1=3, s_y=150)
    dims["footings"] = [dims["footings"][0]]
    out = _run(case, dims=dims, basis=_basis({"durability.cover_footing_mm": {"value": 0.0}}))
    row = out["footings"][0]
    assert (row["cover_mm"], row["end_cover_mm"]) == (0.0, 0.0)
    assert (row["n_x"], row["s_x_mm"], row["n_y"], row["s_y_mm"]) == (2, 184.0, 3, 150.0)
    assert (row["d_x_mm"], row["d_y_mm"], row["d_mm"]) == (292.0, 276.0, 284.0)


@pytest.mark.parametrize("bottom_layer", ["x_bottom", "y_bottom"])
@pytest.mark.parametrize("depth", [104.0, 105.0])
def test_depth_without_room_for_both_layers_is_refused(bottom_layer: str, depth: float) -> None:
    case = load_cases("layout")["layout-depth-out-of-range"]
    dims = copy.deepcopy(case.input["dims"])
    dims["footings"][0]["h_mm"] = depth
    with pytest.raises(ContractError) as caught:
        _run(
            case,
            dims=dims,
            basis=_basis(
                {
                    "reinforcement.bar_diameter_mm": {"value": 20.0},
                    "reinforcement.bottom_layer": {"value": bottom_layer},
                    "durability.cover_footing_mm": {"value": 75.0},
                }
            ),
        )
    assert caught.value.detail.code is ErrorCode.OUT_OF_RANGE
    assert caught.value.detail.field == "dims"
    assert caught.value.detail.expected == {"min_depth_exclusive_mm": 105.0}
    assert caught.value.detail.received == depth


def test_depth_just_above_threshold_is_accepted() -> None:
    case = load_cases("layout")["layout-depth-out-of-range"]
    dims = copy.deepcopy(case.input["dims"])
    dims["footings"][0]["h_mm"] = 106.0
    out = _run(
        case,
        dims=dims,
        basis=_basis(
            {
                "reinforcement.bar_diameter_mm": {"value": 20.0},
                "reinforcement.bottom_layer": {"value": "x_bottom"},
                "durability.cover_footing_mm": {"value": 75.0},
            }
        ),
    )
    row = out["footings"][0]
    assert (row["d_x_mm"], row["d_y_mm"], row["d_mm"]) == (21.0, 1.0, 11.0)


def test_width_too_small_in_y_direction_only_and_status_handling() -> None:
    case = load_cases("layout")["layout-span-zero-and-negative"]
    dims = copy.deepcopy(case.input["dims"])
    # J1: Lx = 166 (span_y = 0), Ly = 466 (span_x = 300 > 0; calculated s_x would be 150.0 != 200.0), s = 200
    # -> WIDTH_TOO_SMALL applies before computing spacing in either direction: n = 0, s_x = s_y = 200.0, As = 0.0
    # J2: valid spans, status OUTSIDE_BASIS_BOUNDS is preserved
    dims["footings"] = [
        dims["footings"][0] | {"Lx_mm": 166.0, "Ly_mm": 466.0, "status": "OK", "reason": None},
        dims["footings"][1] | {"Lx_mm": 566.0, "Ly_mm": 566.0, "status": "OUTSIDE_BASIS_BOUNDS", "reason": None},
    ]
    trace = TraceBuilder()
    out = _run(case, trace=trace, dims=dims)
    r1, r2 = out["footings"]
    assert (
        r1["status"],
        r1["reason"],
        r1["n_x"],
        r1["s_x_mm"],
        r1["As_x_mm2"],
        r1["n_y"],
        r1["s_y_mm"],
        r1["As_y_mm2"],
    ) == ("NEEDS_ENGINEER", "WIDTH_TOO_SMALL", 0, 200.0, 0.0, 0, 200.0, 0.0)
    assert (r2["status"], r2["reason"], r2["n_x"], r2["n_y"]) == ("OUTSIDE_BASIS_BOUNDS", None, 3, 3)
    steps = {s.name: s.value for s in trace.build(REGISTRY[CALC_ID], DIGEST).steps}
    assert steps == {"footings": 2, "width_too_small": 1}


def test_unknown_footing_id_empty_dims_and_missing_meta_refs() -> None:
    case = load_cases("layout")["layout-x-bottom-top"]
    empty = _run(case, dims={"footings": []})
    assert empty == {"footings": []}

    bad_dims = copy.deepcopy(case.input["dims"])
    bad_dims["footings"][0]["id"] = "J_UNKNOWN"
    bad_dims["footings"] = [bad_dims["footings"][0]]
    with pytest.raises(ContractError) as caught:
        _run(case, dims=bad_dims)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "dims"

    for omitted in ("dims", "subjects", "basis"):
        refs = {k: v for k, v in case.refs.items() if k != omitted}
        raw = copy.deepcopy(case.input)
        raw["dims"] = _calc_meta("harness.footing_plan_size") | raw["dims"]
        raw["subjects"] = _calc_meta("harness.footing_subjects") | raw["subjects"]
        with pytest.raises(ContractError) as ref_caught:
            footing_layout(LayoutInput.model_validate(raw), input_meta(refs, KINDS), TraceBuilder())
        assert ref_caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
        assert ref_caught.value.detail.field == omitted


def _build_port(tmp_path: Path) -> tuple[HarnessCalcPort, ResultStore, Provenance]:
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"harness", clock)
    store = ResultStore(Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, ids, clock)
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=FixedClock(1, 1).now(), duration_ms=0)
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(
        REGISTRY,
        approvals,
        store,
        CalcSettings(max_items=1000),
        RunClass.TRIAL,
        clock,
        ids,
        basis_fields={CALC_ID: BASIS_FIELDS},
    )
    return port, store, producer


def _store_port_args(
    store: ResultStore,
    producer: Provenance,
    dims_payload: dict[str, Any],
    subjects_payload: dict[str, Any],
    basis: dict[str, Any],
) -> dict[str, JsonValue]:
    payloads = {
        "dims": _calc_meta("harness.footing_plan_size") | dims_payload,
        "subjects": _calc_meta("harness.footing_subjects") | subjects_payload,
        "basis": basis,
    }
    return {name: {"$ref": store.put(kind, payloads[name], producer).result_id} for name, kind in KINDS.items()}


def test_run_through_the_calc_port(tmp_path: Path) -> None:
    port, store, producer = _build_port(tmp_path)
    case = load_cases("layout")["layout-x-bottom-top"]
    args = _store_port_args(store, producer, case.input["dims"], case.input["subjects"], case.input["basis"])
    info = port.describe(CALC_ID)
    assert info.basis_fields == BASIS_FIELDS
    assert {name: sorted(rule.kinds) for name, rule in info.ref_rules.items()} == {n: [k] for n, k in KINDS.items()}
    out = port.run(CALC_ID, args)
    assert isinstance(out, SuccessEnvelope)
    assert out.kind == "harness.footing_design/1"
    stored = FootingDesign.model_validate(store.payload(out.result_id))
    assert stored.draft is True
    assert [f.id for f in stored.footings] == ["J1", "J2"]
    assert stored.trace.calc_id == CALC_ID
    literal = port.run(CALC_ID, args | {"basis": case.input["basis"]})
    assert isinstance(literal, FailureEnvelope)
    assert literal.error.code is ErrorCode.INVALID_ARGUMENT


def test_calc_port_refuses_bar_count_above_contract_limit(tmp_path: Path) -> None:
    port, store, producer = _build_port(tmp_path)
    case = load_cases("layout")["layout-x-bottom-top"]
    subjects = {"subjects": [case.input["subjects"]["subjects"][0]], "excluded": []}

    # 400 mm span with spacing 2^-45 mm gives 400 * 2^45 + 1 bars > 2^53 - 1
    dims_small_s = copy.deepcopy(case.input["dims"])
    dims_small_s["footings"] = [dims_small_s["footings"][0] | {"Lx_mm": 566.0, "Ly_mm": 566.0, "s_mm": 2.0**-45}]
    args_small_s = _store_port_args(store, producer, dims_small_s, subjects, case.input["basis"])
    out_small_s = port.run(CALC_ID, args_small_s)
    assert isinstance(out_small_s, FailureEnvelope)
    assert out_small_s.error.code is ErrorCode.OUT_OF_RANGE
    assert out_small_s.error.field == "dims"
    assert out_small_s.error.expected == {"max_count": 2**53 - 1}
    assert canonical_json(out_small_s.model_dump(mode="json"))

    # Exact boundary: 2^53 - 1 is accepted, 2^53 is refused
    max_safe_basis = _basis(
        {"reinforcement.bar_diameter_mm": {"value": 2.0}, "durability.cover_footing_mm": {"value": 0.0}}
    )
    dims_at_limit = copy.deepcopy(case.input["dims"])
    dims_at_limit["footings"] = [
        dims_at_limit["footings"][0] | {"Lx_mm": 100.0, "Ly_mm": float(2**53), "h_mm": 100.0, "s_mm": 1.0}
    ]
    out_at_limit = port.run(CALC_ID, _store_port_args(store, producer, dims_at_limit, subjects, max_safe_basis))
    assert isinstance(out_at_limit, SuccessEnvelope)
    stored = FootingDesign.model_validate(store.payload(out_at_limit.result_id))
    assert stored.footings[0].n_x == 2**53 - 1

    over_limit_basis = _basis(
        {"reinforcement.bar_diameter_mm": {"value": 1.0}, "durability.cover_footing_mm": {"value": 0.0}}
    )
    out_over_limit = port.run(CALC_ID, _store_port_args(store, producer, dims_at_limit, subjects, over_limit_basis))
    assert isinstance(out_over_limit, FailureEnvelope)
    assert out_over_limit.error.code is ErrorCode.OUT_OF_RANGE
    assert out_over_limit.error.field == "dims"


def test_calc_port_large_finite_area_and_overflow_refusal(tmp_path: Path) -> None:
    port, store, producer = _build_port(tmp_path)
    case = load_cases("layout")["layout-x-bottom-top"]
    subjects = {"subjects": [case.input["subjects"]["subjects"][0]], "excluded": []}

    # db = 8e153 mm, n = 2 gives finite area ~1.0053e308 mm2 (would overflow pi * db^2 before / 4)
    finite_basis = _basis(
        {"reinforcement.bar_diameter_mm": {"value": 8e153}, "durability.cover_footing_mm": {"value": 0.0}}
    )
    dims_finite = copy.deepcopy(case.input["dims"])
    dims_finite["footings"] = [
        dims_finite["footings"][0] | {"Lx_mm": 3e154, "Ly_mm": 3e154, "h_mm": 2e154, "s_mm": 3e154}
    ]
    out_finite = port.run(CALC_ID, _store_port_args(store, producer, dims_finite, subjects, finite_basis))
    assert isinstance(out_finite, SuccessEnvelope)
    stored = FootingDesign.model_validate(store.payload(out_finite.result_id))
    row = stored.footings[0]
    assert (row.n_x, row.n_y) == (2, 2)
    expected_area = float(Fraction(2) * Fraction(8e153) ** 2 * Fraction(math.pi) / Fraction(4))
    assert math.isfinite(row.As_x_mm2)
    assert math.isfinite(row.As_y_mm2)
    assert abs(row.As_x_mm2 - expected_area) <= _AREA_REL_TOL * expected_area
    assert abs(row.As_y_mm2 - expected_area) <= _AREA_REL_TOL * expected_area

    # db = 1.5e154 mm, n = 2 overflows binary64 -> OUT_OF_RANGE on field dims
    overflow_basis = _basis(
        {"reinforcement.bar_diameter_mm": {"value": 1.5e154}, "durability.cover_footing_mm": {"value": 0.0}}
    )
    dims_overflow = copy.deepcopy(case.input["dims"])
    dims_overflow["footings"] = [
        dims_overflow["footings"][0] | {"Lx_mm": 4e154, "Ly_mm": 4e154, "h_mm": 4e154, "s_mm": 4e154}
    ]
    out_overflow = port.run(CALC_ID, _store_port_args(store, producer, dims_overflow, subjects, overflow_basis))
    assert isinstance(out_overflow, FailureEnvelope)
    assert out_overflow.error.code is ErrorCode.OUT_OF_RANGE
    assert out_overflow.error.field == "dims"
