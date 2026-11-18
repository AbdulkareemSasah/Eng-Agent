"""Hand-derived plan-size cases for spec 0010 AC7 and section 4.4.2."""

import pytest
from eng_contract.errors import ContractError
from pydantic import BaseModel

from eng_harness.calc import NotImplementedGap, TraceBuilder
from eng_harness.calcs import REGISTRY

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
    return definition.fn(
        definition.input_type.model_validate(case.input),  # type: ignore[attr-defined]
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
