"""Hand-derived resize cases for spec 0010 AC9 and section 4.4.4."""

from __future__ import annotations

import copy
import math
from fractions import Fraction
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from pydantic import BaseModel

from eng_harness.calc import CalcInput, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.footing.resize import (
    ResizeAction,
    ResizeInput,
    _enlarge_plan,
    _fraction_mm,
    _increase_depth,
    _reduce_spacing,
    footing_resize,
)
from eng_harness.kinds.footing import DimRow, FootingDims

from . import FootingGoldenCase, input_meta, load_cases

CALC_ID = "harness.footing_resize"
KINDS = {
    "dims": "harness.footing_dims/1",
    "basis": "basis.design_basis/1",
    "engineer_plan": "basis.engineer_input/1",
    "engineer_depth": "basis.engineer_input/1",
    "engineer_spacing": "basis.engineer_input/1",
}
DIGEST = "ab" * 32
METHOD = "eng-harness spec 0010 §4.4.4"
STEMS = [
    "resize-actions",
    "resize-engineer-off-increment",
    "resize-engineer-ok",
    "resize-engineer-outside-and-off",
    "resize-engineer-outside-depth-high",
    "resize-engineer-outside-depth-low",
    "resize-engineer-outside-plan-high",
    "resize-engineer-outside-plan-low",
    "resize-engineer-outside-spacing-high",
    "resize-engineer-outside-spacing-low",
    "resize-limits",
]
BASIS_PATHS = (
    "foundation.plan_increment_mm",
    "foundation.min_plan_dimension_mm",
    "foundation.max_plan_dimension_mm",
    "foundation.depth_increment_mm",
    "foundation.min_depth_mm",
    "foundation.max_depth_mm",
    "reinforcement.spacing_increment_mm",
    "reinforcement.min_spacing_mm",
    "reinforcement.max_spacing_mm",
)


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


def run_case(case: FootingGoldenCase, trace: TraceBuilder | None = None) -> BaseModel:
    definition = REGISTRY[CALC_ID]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    raw = copy.deepcopy(case.input)
    raw["dims"] = _calc_meta("harness.footing_plan_size") | raw["dims"]
    return definition(
        input_type.model_validate(raw),
        input_meta(case.refs, KINDS),
        trace if trace is not None else TraceBuilder(),
    )


def _resize_input(case: FootingGoldenCase) -> ResizeInput:
    raw = copy.deepcopy(case.input)
    raw["dims"] = _calc_meta("harness.footing_plan_size") | raw["dims"]
    return ResizeInput.model_validate(raw)


def _call(inp: ResizeInput, case: FootingGoldenCase, trace: TraceBuilder | None = None) -> BaseModel:
    return footing_resize(inp, input_meta(case.refs, KINDS), trace if trace is not None else TraceBuilder())


def test_golden_cases() -> None:
    cases = load_cases("resize")
    assert set(cases) == set(STEMS)
    for stem, case in cases.items():
        assert run_case(case).model_dump(mode="json") == case.expected, stem


def test_golden_cases_report_status_and_flags() -> None:
    """Every action path records status and the three bound flags (spec §4.4.4 / Q13 / Q17)."""
    cases = load_cases("resize")
    for stem, case in cases.items():
        rows = run_case(case).model_dump(mode="json")["footings"]
        for expected, got in zip(case.expected["footings"], rows, strict=True):
            assert (got["status"], got["reason"]) == (expected["status"], expected["reason"]), stem
            assert (
                got["plan_at_max"],
                got["depth_at_max"],
                got["spacing_at_min"],
            ) == (
                expected["plan_at_max"],
                expected["depth_at_max"],
                expected["spacing_at_min"],
            ), stem
            assert got["source"] == expected["source"], stem


def test_trace_records_r1_r2_r3_and_basis_units() -> None:
    case = load_cases("resize")["resize-actions"]
    trace = TraceBuilder()
    run_case(case, trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    basis_ref = case.refs["basis"]
    inputs = {item.name: (item.value, item.unit, item.ref) for item in built.inputs}
    assert inputs["plan_increment_mm"] == (200, "mm", f"{basis_ref}#/fields/foundation.plan_increment_mm")
    assert inputs["max_plan_dimension_mm"] == (3000, "mm", f"{basis_ref}#/fields/foundation.max_plan_dimension_mm")
    assert inputs["depth_increment_mm"] == (50, "mm", f"{basis_ref}#/fields/foundation.depth_increment_mm")
    assert inputs["max_depth_mm"] == (800, "mm", f"{basis_ref}#/fields/foundation.max_depth_mm")
    assert inputs["spacing_increment_mm"] == (25, "mm", f"{basis_ref}#/fields/reinforcement.spacing_increment_mm")
    assert inputs["min_spacing_mm"] == (100, "mm", f"{basis_ref}#/fields/reinforcement.min_spacing_mm")
    assert inputs["footing_0_id"] == ("F1", None, f"{case.refs['dims']}#/footings/0/id")
    assert inputs["footing_0_L_mm"] == (2000.0, "mm", f"{case.refs['dims']}#/footings/0/Lx_mm")
    assert inputs["footing_0_h_mm"] == (500.0, "mm", f"{case.refs['dims']}#/footings/0/h_mm")
    assert inputs["footing_0_s_mm"] == (200.0, "mm", f"{case.refs['dims']}#/footings/0/s_mm")
    assert inputs["footing_0_action"] == ("enlarge_plan", None, None)
    assert inputs["footing_1_action"] == ("increase_depth", None, None)
    assert inputs["footing_2_action"] == ("reduce_bar_spacing", None, None)
    assert inputs["footing_3_action"] == ("none", None, None)
    assert {item.name: item.cited.value for item in built.constants} == {"zero": 0, "one": 1}

    steps = {step.name: (step.value, step.unit, step.formula, step.source, step.uses) for step in built.steps}
    assert steps["footing_0_next_plan_mm"] == (
        "2200",
        "mm",
        "(floor(L / i) + 1) * i on exact fractions",
        f"{METHOD} R1",
        ["footing_0_L_mm", "plan_increment_mm"],
    )
    assert steps["footing_0_plan_mm"] == (
        2200.0,
        "mm",
        "next multiple of plan_increment_mm above L",
        f"{METHOD} R1",
        ["footing_0_next_plan_mm"],
    )
    assert steps["footing_1_next_depth_mm"] == (
        "550",
        "mm",
        "h + depth_increment_mm",
        f"{METHOD} R2",
        ["footing_1_h_mm", "depth_increment_mm"],
    )
    assert steps["footing_1_depth_mm"] == (
        550.0,
        "mm",
        "h + depth_increment_mm",
        f"{METHOD} R2",
        ["footing_1_next_depth_mm"],
    )
    assert steps["footing_2_next_spacing_mm"] == (
        "175",
        "mm",
        "s - spacing_increment_mm",
        f"{METHOD} R3",
        ["footing_2_s_mm", "spacing_increment_mm"],
    )
    assert steps["footing_2_spacing_mm"] == (
        175.0,
        "mm",
        "s - spacing_increment_mm",
        f"{METHOD} R3",
        ["footing_2_next_spacing_mm"],
    )
    assert built.outputs == [
        "footing_0_plan_mm",
        "footing_1_depth_mm",
        "footing_2_spacing_mm",
        "footing_3_L_mm",
        "footing_3_h_mm",
        "footing_3_s_mm",
        "footing_4_plan_mm",
    ]


def test_trace_records_limit_reached_formulas() -> None:
    case = load_cases("resize")["resize-limits"]
    trace = TraceBuilder()
    run_case(case, trace)
    steps = {
        step.name: (step.value, step.unit, step.formula, step.source, step.uses)
        for step in trace.build(REGISTRY[CALC_ID], DIGEST).steps
    }
    assert steps["footing_0_next_plan_mm"] == (
        "3200",
        "mm",
        "(floor(L / i) + 1) * i on exact fractions",
        f"{METHOD} R1",
        ["footing_0_L_mm", "plan_increment_mm"],
    )
    assert steps["footing_0_plan_mm"] == (
        3000.0,
        "mm",
        "unchanged: next plan above max_plan_dimension_mm",
        f"{METHOD} R1",
        ["footing_0_next_plan_mm", "max_plan_dimension_mm"],
    )
    assert steps["footing_1_depth_mm"] == (
        800.0,
        "mm",
        "unchanged: next depth above max_depth_mm",
        f"{METHOD} R2",
        ["footing_1_next_depth_mm", "max_depth_mm"],
    )
    assert steps["footing_2_spacing_mm"] == (
        100.0,
        "mm",
        "unchanged: next spacing below min_spacing_mm",
        f"{METHOD} R3",
        ["footing_2_next_spacing_mm", "min_spacing_mm"],
    )


def test_trace_records_engineer_set_steps() -> None:
    case = load_cases("resize")["resize-engineer-outside-and-off"]
    trace = TraceBuilder()
    run_case(case, trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    inputs = {item.name: (item.value, item.unit, item.ref) for item in built.inputs}
    assert inputs["footing_0_engineer_plan_mm"] == (3500.0, "mm", case.refs["engineer_plan"])
    assert inputs["footing_0_engineer_depth_mm"] == (500.0, "mm", case.refs["engineer_depth"])
    assert inputs["footing_0_engineer_spacing_mm"] == (200.0, "mm", case.refs["engineer_spacing"])
    steps = {step.name: (step.value, step.unit, step.formula, step.source, step.uses) for step in built.steps}
    assert steps["footing_0_plan_mm"] == (
        3500.0,
        "mm",
        "engineer L; Lx = Ly = L",
        f"{METHOD} R4",
        ["footing_0_engineer_plan_mm"],
    )
    assert steps["footing_0_depth_mm"] == (
        500.0,
        "mm",
        "engineer h",
        f"{METHOD} R4",
        ["footing_0_engineer_depth_mm"],
    )
    assert steps["footing_0_spacing_mm"] == (
        200.0,
        "mm",
        "engineer s",
        f"{METHOD} R4",
        ["footing_0_engineer_spacing_mm"],
    )
    assert built.outputs == ["footing_0_plan_mm", "footing_0_depth_mm", "footing_0_spacing_mm"]


def test_land_on_depth_and_spacing_bounds_keeps_ok() -> None:
    """One increment that lands exactly on the bound stays OK with the flag cleared (spec §4.4.4)."""
    case = load_cases("resize")["resize-limits"]
    inp = _resize_input(case)
    # h = 750, di = 50 → 800 = max_depth; s = 125, si = 25 → 100 = min_spacing.
    footings = [
        DimRow.model_validate(
            {
                "id": "D1",
                "Lx_mm": 2000.0,
                "Ly_mm": 2000.0,
                "h_mm": 750.0,
                "s_mm": 200.0,
                "source": "calc",
                "plan_at_max": False,
                "depth_at_max": False,
                "spacing_at_min": False,
                "status": "OK",
                "reason": None,
            }
        ),
        DimRow.model_validate(
            {
                "id": "S1",
                "Lx_mm": 2000.0,
                "Ly_mm": 2000.0,
                "h_mm": 500.0,
                "s_mm": 125.0,
                "source": "calc",
                "plan_at_max": False,
                "depth_at_max": False,
                "spacing_at_min": False,
                "status": "OK",
                "reason": None,
            }
        ),
    ]
    out = _call(
        inp.model_copy(
            update={
                "dims": FootingDims.model_validate(_calc_meta("harness.footing_plan_size") | {"footings": footings}),
                "actions": {
                    "D1": ResizeAction.INCREASE_DEPTH,
                    "S1": ResizeAction.REDUCE_BAR_SPACING,
                },
            }
        ),
        case,
    ).model_dump()["footings"]
    assert (out[0]["h_mm"], out[0]["status"], out[0]["depth_at_max"]) == (800.0, "OK", False)
    assert (out[1]["s_mm"], out[1]["status"], out[1]["spacing_at_min"]) == (100.0, "OK", False)


@pytest.mark.parametrize(
    ("plan", "depth", "spacing"),
    [
        (1000.0, 500.0, 200.0),  # plan at min
        (3000.0, 500.0, 200.0),  # plan at max
        (2000.0, 400.0, 200.0),  # depth at min
        (2000.0, 800.0, 200.0),  # depth at max
        (2000.0, 500.0, 100.0),  # spacing at min
        (2000.0, 500.0, 300.0),  # spacing at max
    ],
)
def test_engineer_set_exact_bounds_are_ok(plan: float, depth: float, spacing: float) -> None:
    """Closed bounds of R4: values equal to min or max stay OK (amendment B-567)."""
    case = load_cases("resize")["resize-engineer-ok"]
    inp = _resize_input(case)
    out = _call(
        inp.model_copy(
            update={
                "engineer_plan": inp.engineer_plan.model_copy(update={"value": plan}),
                "engineer_depth": inp.engineer_depth.model_copy(update={"value": depth}),
                "engineer_spacing": inp.engineer_spacing.model_copy(update={"value": spacing}),
            }
        ),
        case,
    ).model_dump()["footings"][0]
    assert (out["Lx_mm"], out["Ly_mm"], out["h_mm"], out["s_mm"]) == (plan, plan, depth, spacing)
    assert (out["status"], out["reason"], out["source"]) == ("OK", None, "engineer")
    assert (out["plan_at_max"], out["depth_at_max"], out["spacing_at_min"]) == (False, False, False)


@pytest.mark.parametrize(
    ("plan", "depth", "spacing"),
    [
        (999.0, 500.0, 200.0),  # one below plan min
        (3001.0, 500.0, 200.0),  # one above plan max (on-grid would be 3000/3200; 3001 is off too)
        (2000.0, 399.0, 200.0),
        (2000.0, 801.0, 200.0),
        (2000.0, 500.0, 99.0),
        (2000.0, 500.0, 301.0),
    ],
)
def test_engineer_set_one_past_bound_is_outside(plan: float, depth: float, spacing: float) -> None:
    case = load_cases("resize")["resize-engineer-ok"]
    inp = _resize_input(case)
    out = _call(
        inp.model_copy(
            update={
                "engineer_plan": inp.engineer_plan.model_copy(update={"value": plan}),
                "engineer_depth": inp.engineer_depth.model_copy(update={"value": depth}),
                "engineer_spacing": inp.engineer_spacing.model_copy(update={"value": spacing}),
            }
        ),
        case,
    ).model_dump()["footings"][0]
    assert out["status"] == "OUTSIDE_BASIS_BOUNDS"
    assert out["source"] == "engineer"
    assert (out["Lx_mm"], out["Ly_mm"], out["h_mm"], out["s_mm"]) == (plan, plan, depth, spacing)


@pytest.mark.parametrize(
    ("path", "changes", "code", "message", "expected", "received", "hint"),
    [
        (
            "foundation.plan_increment_mm",
            None,
            ErrorCode.INVALID_ARGUMENT,
            "is missing or not confirmed",
            None,
            None,
            "confirm foundation.plan_increment_mm",
        ),
        (
            "foundation.min_depth_mm",
            {"confirmed": False},
            ErrorCode.INVALID_ARGUMENT,
            "is missing or not confirmed",
            None,
            None,
            "confirm foundation.min_depth_mm",
        ),
        (
            "reinforcement.max_spacing_mm",
            {"unit": "kN"},
            ErrorCode.UNIT_MISMATCH,
            "has the wrong unit",
            {"unit": "mm"},
            "kN",
            None,
        ),
        (
            "foundation.depth_increment_mm",
            {"value": True},
            ErrorCode.INVALID_ARGUMENT,
            "must be a finite number",
            None,
            None,
            None,
        ),
        (
            "foundation.plan_increment_mm",
            {"value": 0},
            ErrorCode.OUT_OF_RANGE,
            "is outside its physical bounds",
            {"gt": 0},
            0,
            None,
        ),
        (
            "foundation.max_plan_dimension_mm",
            {"value": -1},
            ErrorCode.OUT_OF_RANGE,
            "is outside its physical bounds",
            {"gt": 0},
            -1,
            None,
        ),
    ],
)
def test_invalid_basis_names_the_field(
    path: str,
    changes: dict[str, object] | None,
    code: ErrorCode,
    message: str,
    expected: object,
    received: object,
    hint: str | None,
) -> None:
    case = load_cases("resize")["resize-actions"]
    inp = _resize_input(case)
    fields = dict(inp.basis.fields)
    if changes is None:
        del fields[path]
    else:
        fields[path] = fields[path].model_copy(update=changes)
    basis = DesignBasis.model_construct(template=None, fields=fields)
    with pytest.raises(ContractError) as caught:
        _call(inp.model_copy(update={"basis": basis}), case)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (code, "basis", f"basis field {path} {message}")
    assert (detail.expected, detail.received, detail.hint) == (expected, received, hint)


@pytest.mark.parametrize("path", BASIS_PATHS)
def test_each_basis_path_missing_is_refused(path: str) -> None:
    case = load_cases("resize")["resize-actions"]
    inp = _resize_input(case)
    fields = dict(inp.basis.fields)
    del fields[path]
    basis = DesignBasis.model_construct(template=None, fields=fields)
    with pytest.raises(ContractError) as caught:
        _call(inp.model_copy(update={"basis": basis}), case)
    detail = caught.value.detail
    assert detail.code is ErrorCode.INVALID_ARGUMENT
    assert detail.field == "basis"
    assert detail.message == f"basis field {path} is missing or not confirmed"
    assert detail.hint == f"confirm {path}"


def _probe_row(
    footing_id: str,
    *,
    plan_mm: float = 2000.0,
    depth_mm: float = 500.0,
    spacing_mm: float = 200.0,
) -> DimRow:
    return DimRow.model_construct(
        id=footing_id,
        Lx_mm=plan_mm,
        Ly_mm=plan_mm,
        h_mm=depth_mm,
        s_mm=spacing_mm,
        source="calc",
        plan_at_max=False,
        depth_at_max=False,
        spacing_at_min=False,
        status="OK",
        reason=None,
    )


@pytest.mark.parametrize("field", ["Lx_mm", "h_mm", "s_mm"])
def test_fraction_mm_refuses_non_finite_with_exact_message(field: str) -> None:
    """Helper used by R1-R3: non-finite mm values name the footing and the field (spec 0010 §4.4.4)."""
    with pytest.raises(ContractError) as caught:
        _fraction_mm(math.inf, "F1", field)
    detail = caught.value.detail
    assert detail.code is ErrorCode.INVALID_ARGUMENT
    assert detail.field == "dims"
    assert detail.message == f"footing F1 has a non-finite {field}"


def test_enlarge_plan_passes_footing_id_and_field_into_fraction_mm() -> None:
    """R1 reads Lx/h/s through `_fraction_mm`; the field names and footing id must reach the refusal."""
    quantities = {
        "plan_increment_mm": Fraction(200),
        "max_plan_dimension_mm": Fraction(3000),
    }
    with pytest.raises(ContractError) as caught:
        _enlarge_plan(_probe_row("FX", plan_mm=math.inf), quantities, TraceBuilder(), "footing_0")
    assert caught.value.detail.message == "footing FX has a non-finite Lx_mm"
    with pytest.raises(ContractError) as caught_h:
        _enlarge_plan(_probe_row("FX", depth_mm=math.inf), quantities, TraceBuilder(), "footing_0")
    assert caught_h.value.detail.message == "footing FX has a non-finite h_mm"
    with pytest.raises(ContractError) as caught_s:
        _enlarge_plan(_probe_row("FX", spacing_mm=math.inf), quantities, TraceBuilder(), "footing_0")
    assert caught_s.value.detail.message == "footing FX has a non-finite s_mm"


def test_depth_and_spacing_helpers_pass_field_names() -> None:
    quantities = {
        "depth_increment_mm": Fraction(50),
        "max_depth_mm": Fraction(800),
        "spacing_increment_mm": Fraction(25),
        "min_spacing_mm": Fraction(100),
    }
    with pytest.raises(ContractError) as caught:
        _increase_depth(_probe_row("FY", depth_mm=math.inf), quantities, TraceBuilder(), "footing_0")
    assert caught.value.detail.message == "footing FY has a non-finite h_mm"
    with pytest.raises(ContractError) as caught_lx:
        _increase_depth(_probe_row("FY", plan_mm=math.inf), quantities, TraceBuilder(), "footing_0")
    assert caught_lx.value.detail.message == "footing FY has a non-finite Lx_mm"
    with pytest.raises(ContractError) as caught_s_on_depth:
        _increase_depth(_probe_row("FY", spacing_mm=math.inf), quantities, TraceBuilder(), "footing_0")
    assert caught_s_on_depth.value.detail.message == "footing FY has a non-finite s_mm"
    with pytest.raises(ContractError) as caught_s:
        _reduce_spacing(_probe_row("FY", spacing_mm=math.inf), quantities, TraceBuilder(), "footing_0")
    assert caught_s.value.detail.message == "footing FY has a non-finite s_mm"
    with pytest.raises(ContractError) as caught_plan:
        _reduce_spacing(_probe_row("FY", plan_mm=math.inf), quantities, TraceBuilder(), "footing_0")
    assert caught_plan.value.detail.message == "footing FY has a non-finite Lx_mm"
    with pytest.raises(ContractError) as caught_h:
        _reduce_spacing(_probe_row("FY", depth_mm=math.inf), quantities, TraceBuilder(), "footing_0")
    assert caught_h.value.detail.message == "footing FY has a non-finite h_mm"


def test_non_square_footing_is_refused() -> None:
    case = load_cases("resize")["resize-actions"]
    inp = _resize_input(case)
    row = inp.dims.footings[0].model_copy(update={"Ly_mm": 2100.0})
    dims = FootingDims.model_construct(footings=[row])
    with pytest.raises(ContractError) as caught:
        _call(inp.model_copy(update={"dims": dims, "actions": {row.id: ResizeAction.NONE}}), case)
    detail = caught.value.detail
    assert detail.code is ErrorCode.INVALID_ARGUMENT
    assert detail.field == "dims"
    assert detail.message == f"footing {row.id} is not square (FG-1)"


def test_missing_action_for_footing_is_refused() -> None:
    case = load_cases("resize")["resize-actions"]
    inp = _resize_input(case)
    with pytest.raises(ContractError) as caught:
        _call(inp.model_copy(update={"actions": {}}), case)
    detail = caught.value.detail
    assert detail.code is ErrorCode.INVALID_ARGUMENT
    assert detail.field == "actions"
    assert detail.message == f"actions has no entry for footing {inp.dims.footings[0].id}"


def test_unknown_action_footing_id_is_refused() -> None:
    case = load_cases("resize")["resize-engineer-ok"]
    inp = _resize_input(case)
    with pytest.raises(ContractError) as caught:
        _call(
            inp.model_copy(update={"actions": {"F1": ResizeAction.NONE, "EXTRA": ResizeAction.NONE}}),
            case,
        )
    detail = caught.value.detail
    assert detail.code is ErrorCode.INVALID_ARGUMENT
    assert detail.field == "actions"
    assert detail.message == "actions names unknown footing ids: EXTRA"


@pytest.mark.parametrize("name", ["dims", "basis", "engineer_plan", "engineer_depth", "engineer_spacing"])
def test_missing_record_reference_is_refused(name: str) -> None:
    case = load_cases("resize")["resize-engineer-ok"]
    inp = _resize_input(case)
    refs = {key: value for key, value in case.refs.items() if key != name}
    kinds = {key: value for key, value in KINDS.items() if key != name}
    with pytest.raises(ContractError) as caught:
        footing_resize(inp, input_meta(refs, kinds), TraceBuilder())
    detail = caught.value.detail
    assert detail.code is ErrorCode.INVALID_ARGUMENT
    assert detail.field == name
    assert detail.message == f"input {name} must be a record reference"


def test_one_increment_past_each_limit_sets_flag() -> None:
    """Past-bound steps leave size unchanged with LIMIT_REACHED and the matching flag."""
    case = load_cases("resize")["resize-limits"]
    rows = run_case(case).model_dump()["footings"]
    assert (rows[0]["Lx_mm"], rows[0]["status"], rows[0]["plan_at_max"]) == (3000.0, "LIMIT_REACHED", True)
    assert (rows[1]["h_mm"], rows[1]["status"], rows[1]["depth_at_max"]) == (800.0, "LIMIT_REACHED", True)
    assert (rows[2]["s_mm"], rows[2]["status"], rows[2]["spacing_at_min"]) == (100.0, "LIMIT_REACHED", True)
    # Land-on-max for plan stays OK with plan_at_max false until a later past-bound step.
    assert (rows[3]["Lx_mm"], rows[3]["status"], rows[3]["plan_at_max"]) == (3000.0, "OK", False)
