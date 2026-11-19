"""Hand-derived resize cases for spec 0010 AC9 and section 4.4.4."""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel

from eng_harness.calc import CalcInput, TraceBuilder
from eng_harness.calcs import REGISTRY

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


def test_golden_cases() -> None:
    cases = load_cases("resize")
    assert set(cases) == set(STEMS)
    for stem, case in cases.items():
        assert run_case(case).model_dump(mode="json") == case.expected, stem
