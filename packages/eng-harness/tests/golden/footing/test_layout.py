"""Golden cases of harness.footing_layout (plan 0010 T5; spec 0010 AC8, section 4.4.3)."""

import copy
from typing import Any

import pytest
from eng_contract.errors import ContractError

from eng_harness.calc import TraceBuilder
from eng_harness.calcs.footing.layout import LayoutInput, footing_layout

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
            if actual != case.expected:
                failures[stem] = actual
    assert failures == {}
