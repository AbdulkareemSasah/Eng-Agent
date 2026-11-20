"""Golden cases of harness.reactions_to_joint_loads (plan 0010 T10; spec 0010 AC24, section 4.9)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from eng_contract.errors import ContractError

from eng_harness.calc import TraceBuilder
from eng_harness.calcs.footing.reactions_to_loads import ReactionsInput, reactions_to_joint_loads

from . import FootingGoldenCase, input_meta, load_cases

CALC_ID = "harness.reactions_to_joint_loads"
KINDS = {
    "reactions": "forces.joint_reactions/1",
    "subjects": "harness.footing_subjects/1",
    "etabs_load_set": "model.load_set/1",
    "safe_points": "harness.model_points/1",
    "safe_load_set": "model.load_set/1",
    "cases": "basis.engineer_input/1",
    "basis": "basis.design_basis/1",
}
STEMS = [
    "loads-basic-negation",
    "loads-chosen-cases-only",
    "loads-combo-conflict",
    "loads-double-match",
    "loads-match-at-tolerance",
    "loads-pattern-missing",
    "loads-unmatched",
]


def _run(case: FootingGoldenCase, trace: TraceBuilder | None = None, **changes: Any) -> dict[str, Any]:
    raw = copy.deepcopy(case.input) | changes
    result = reactions_to_joint_loads(
        ReactionsInput.model_validate(raw), input_meta(case.refs, KINDS), trace or TraceBuilder()
    )
    return result.model_dump(mode="json")


def test_golden_cases() -> None:
    """AC24: negation, matching, unmatched, double match, missing pattern, chosen combinations only."""
    cases = load_cases("loads")
    assert sorted(cases) == STEMS
    failures: dict[str, Any] = {}
    for stem, case in cases.items():
        if "error_code" in case.expected:
            with pytest.raises(ContractError) as caught:
                _run(case)
            detail = caught.value.detail
            got = (detail.code.value, detail.field, detail.hint)
            want = (case.expected["error_code"], case.expected["field"], case.expected.get("hint"))
            if got != want:
                failures[stem] = {"got": got, "want": want}
        else:
            actual = _run(case)
            if actual != case.expected:
                failures[stem] = actual
    assert failures == {}
