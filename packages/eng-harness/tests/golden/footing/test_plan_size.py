"""Hand-derived plan-size cases for spec 0010 AC7 and section 4.4.2."""

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from pydantic import BaseModel

from eng_harness.calc import CalcInput, NotImplementedGap, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.footing.plan_size import PlanSizeInput, footing_plan_size

from . import FootingGoldenCase, input_meta, load_cases

CALC_ID = "harness.footing_plan_size"
KINDS = {
    "subjects": "harness.footing_subjects/1",
    "reactions": "forces.joint_reactions/1",
    "service_cases": "basis.engineer_input/1",
    "basis": "basis.design_basis/1",
}


def run_case(case: FootingGoldenCase, trace: TraceBuilder | None = None) -> BaseModel:
    definition = REGISTRY[CALC_ID]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    return definition(
        input_type.model_validate(case.input),
        input_meta(case.refs, KINDS),
        trace if trace is not None else TraceBuilder(),
    )


def test_golden_cases() -> None:
    cases = load_cases("plan")
    assert set(cases) == {
        "plan-gross",
        "plan-net",
        "plan-overburden",
        "plan-overburden-equal",
        "plan-no-positive-multiple",
        "plan-equal-projection",
    }
    for stem, case in cases.items():
        expected = case.expected
        if "gap" in expected:
            with pytest.raises(NotImplementedGap) as gap:
                run_case(case)
            assert gap.value.code == "NOT_IMPLEMENTED"
            assert gap.value.evidence == (expected["gap"],)
        elif "error" in expected:
            with pytest.raises(ContractError) as failure:
                run_case(case)
            assert failure.value.detail.code == expected["error"]
            assert failure.value.detail.field == "basis"
            assert failure.value.detail.expected == expected["expected"]
            assert failure.value.detail.received == expected["received"]
        else:
            assert run_case(case).model_dump(mode="json") == expected, stem


def test_trace_records_service_loads_and_exact_arithmetic() -> None:
    case = load_cases("plan")["plan-gross"]
    trace = TraceBuilder()
    run_case(case, trace)
    built = trace.build(REGISTRY[CALC_ID], "ab" * 32)
    inputs = {item.name: (item.value, item.unit, item.ref) for item in built.inputs}
    basis_ref = case.refs["basis"]
    assert inputs["plan_shape"] == ("square", None, f"{basis_ref}#/fields/foundation.plan_shape")
    assert inputs["plan_increment_mm"] == (200, "mm", f"{basis_ref}#/fields/foundation.plan_increment_mm")
    assert inputs["service_cases"] == (
        case.input["service_cases"],
        None,
        f"{case.refs['service_cases']}#/fields/service_cases/value",
    )
    assert inputs["footing_0_id"] == ("F1", None, f"{case.refs['subjects']}#/subjects/0/id")
    assert inputs["footing_0_fz"] == ([576, 400], "kN", case.refs["reactions"])
    assert inputs["footing_5_fz"] == ([], "kN", case.refs["reactions"])
    assert {item.name: item.cited.value for item in built.constants} == {"mm_per_m": 1000, "zero": 0}

    steps = {step.name: (step.value, step.unit, step.formula, step.source, step.uses) for step in built.steps}
    method = "eng-harness spec 0010 §4.4.2"
    assert steps["overburden_kPa"] == (
        "40",
        "kPa",
        "(min_depth * gamma_c + soil_depth * gamma_s) / mm_per_m + surcharge",
        f"{method} P2 (BP S3)",
        [
            "min_depth_mm",
            "concrete_unit_weight_kN_m3",
            "soil_depth_above_footing_mm",
            "soil_unit_weight_kN_m3",
            "mm_per_m",
            "surcharge_kPa",
        ],
    )
    assert steps["q_net_kPa"] == (
        "160",
        "kPa",
        "allowable_bearing_pressure - overburden",
        f"{method} P2",
        ["allowable_bearing_pressure_kPa", "overburden_kPa"],
    )
    # 576 / 160 * 1,000,000 = 3,600,000 mm2; the 200 mm grid gives 2000 mm.
    assert steps["footing_0_required_area_mm2"] == (
        "3600000",
        "mm2",
        "max(service FZ) / q_net * mm_per_m^2 (exact fraction)",
        f"{method} P3",
        ["footing_0_fz", "q_net_kPa", "mm_per_m"],
    )
    assert steps["footing_0_side_mm"] == (
        2000,
        "mm",
        "least grid size satisfying area and minimum, capped at floor(max_plan / increment) * increment",
        f"{method} P4/P5",
        [
            "footing_0_fz",
            "allowable_bearing_kind",
            "q_net_kPa",
            "plan_increment_mm",
            "min_plan_dimension_mm",
            "footing_0_required_area_mm2",
            "max_plan_dimension_mm",
        ],
    )
    assert steps["footing_5_side_mm"] == (
        1000,
        "mm",
        "ceil(min_plan / increment) * increment",
        f"{method} P6",
        ["footing_5_fz", "allowable_bearing_kind", "q_net_kPa", "plan_increment_mm", "min_plan_dimension_mm"],
    )
    assert built.outputs == [*(f"footing_{i}_side_mm" for i in range(7)), "min_depth_mm", "max_spacing_mm"]


def test_fractional_grid_and_exact_maximum() -> None:
    case = load_cases("plan")["plan-gross"]
    raw = case.input
    raw["subjects"]["subjects"] = raw["subjects"]["subjects"][:1]
    fields = raw["basis"]["fields"]
    fields["foundation.plan_increment_mm"]["value"] = 200.5
    fields["foundation.max_plan_dimension_mm"]["value"] = 2005
    # 0.5*24 + 0*18 + 0 = 12 kPa. F1 still uses 576 kN.
    # (576/188) m2 is between 1.604^2 = 2.572816 and 1.8045^2 = 3.25622025.
    fields["foundation.soil_depth_above_footing_mm"]["value"] = 0
    fields["foundation.surcharge_kPa"]["value"] = 0
    row = run_case(case).model_dump()["footings"][0]
    assert (row["Lx_mm"], row["Ly_mm"]) == (1804.5, 1804.5)
    assert (row["status"], row["plan_at_max"]) == ("OK", False)

    # With a grid of 200 mm, 640/160 = 2^2 m2 exactly at the 2000 mm maximum.
    fields["foundation.soil_depth_above_footing_mm"]["value"] = 1000
    fields["foundation.surcharge_kPa"]["value"] = 10
    fields["foundation.plan_increment_mm"]["value"] = 200
    fields["foundation.max_plan_dimension_mm"]["value"] = 2000
    raw["reactions"]["rows"][0]["FZ_kN"] = 640
    row = run_case(case).model_dump()["footings"][0]
    assert (row["Lx_mm"], row["Ly_mm"]) == (2000, 2000)
    assert (row["status"], row["plan_at_max"]) == ("OK", False)


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
            "foundation.plan_increment_mm",
            {"confirmed": False},
            ErrorCode.INVALID_ARGUMENT,
            "is missing or not confirmed",
            None,
            None,
            "confirm foundation.plan_increment_mm",
        ),
        (
            "foundation.plan_increment_mm",
            {"unit": "kN"},
            ErrorCode.UNIT_MISMATCH,
            "has the wrong unit",
            {"unit": "mm"},
            "kN",
            None,
        ),
        (
            "foundation.plan_increment_mm",
            {"value": True},
            ErrorCode.INVALID_ARGUMENT,
            "must be a finite number",
            None,
            None,
            None,
        ),
        (
            "foundation.plan_shape",
            {"value": "rectangle"},
            ErrorCode.INVALID_ARGUMENT,
            "must be one of square, equal_projection",
            None,
            None,
            "choose one of square, equal_projection",
        ),
        (
            "foundation.allowable_bearing_kind",
            {"value": 1},
            ErrorCode.INVALID_ARGUMENT,
            "must be one of gross, net",
            None,
            None,
            "choose one of gross, net",
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
            "foundation.surcharge_kPa",
            {"value": -1},
            ErrorCode.OUT_OF_RANGE,
            "is outside its physical bounds",
            {"min": 0},
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
    case = load_cases("plan")["plan-gross"]
    inp = PlanSizeInput.model_validate(case.input)
    fields = dict(inp.basis.fields)
    if changes is None:
        del fields[path]
    else:
        fields[path] = fields[path].model_copy(update=changes)
    # Exercise the calc's own checks even when DesignBasis would refuse the field first.
    basis = DesignBasis.model_construct(template=None, fields=fields)
    with pytest.raises(ContractError) as caught:
        footing_plan_size(inp.model_copy(update={"basis": basis}), input_meta(case.refs, KINDS), TraceBuilder())
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (code, "basis", f"basis field {path} {message}")
    assert (detail.expected, detail.received, detail.hint) == (expected, received, hint)
