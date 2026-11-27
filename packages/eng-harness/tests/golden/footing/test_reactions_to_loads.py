"""Golden cases of harness.reactions_to_joint_loads (plan 0010 T10; spec 0010 AC24, section 4.9)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis

from eng_harness.calc import TraceBuilder
from eng_harness.calcs import REGISTRY
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
LENGTH = "compare.length_mm"
DIGEST = "ab" * 32


def _run(case: FootingGoldenCase, trace: TraceBuilder | None = None, **changes: Any) -> dict[str, Any]:
    raw = copy.deepcopy(case.input) | changes
    result = reactions_to_joint_loads(
        ReactionsInput.model_validate(raw), input_meta(case.refs, KINDS), trace or TraceBuilder()
    )
    return result.model_dump(mode="json")


def _input(case: FootingGoldenCase) -> ReactionsInput:
    return ReactionsInput.model_validate(copy.deepcopy(case.input))


def _call(inp: ReactionsInput, case: FootingGoldenCase, trace: TraceBuilder | None = None) -> Any:
    return reactions_to_joint_loads(inp, input_meta(case.refs, KINDS), trace or TraceBuilder())


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


def test_every_status_and_reason_of_section_4_9() -> None:
    """Spec 0010 §4.9: OK; NEEDS_ENGINEER with UNMATCHED / PATTERN_MISSING / COMBO_CONFLICT; DOUBLE_MATCH."""
    cases = load_cases("loads")
    assert cases["loads-basic-negation"].expected["status"] == "OK"
    assert cases["loads-basic-negation"].expected["reason"] is None
    for stem, reason in (
        ("loads-unmatched", "UNMATCHED"),
        ("loads-pattern-missing", "PATTERN_MISSING"),
        ("loads-combo-conflict", "COMBO_CONFLICT"),
    ):
        body = _run(cases[stem])
        assert (body["status"], body["reason"], body["loads"], body["combinations_to_add"]) == (
            "NEEDS_ENGINEER",
            reason,
            [],
            [],
        )
        assert body["axes"] == "global"
    with pytest.raises(ContractError) as caught:
        _run(cases["loads-double-match"])
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.hint) == (
        ErrorCode.INVALID_ARGUMENT,
        "points",
        "DOUBLE_MATCH",
    )
    assert detail.received == ["P1", "P2"]
    assert "matches more than one SAFE point" in detail.message


def test_sign_negation_of_every_component() -> None:
    """Spec 0010 §4.9 M3: loads are the negatives of FX..MZ; punch dimensions null (SG-7)."""
    body = _run(load_cases("loads")["loads-basic-negation"])
    load = body["loads"][0]
    assert (load["FX_kN"], load["FY_kN"], load["FZ_kN"]) == (-10.0, 20.0, -100.0)
    assert (load["MX_kNm"], load["MY_kNm"], load["MZ_kNm"]) == (-1.0, 2.0, -3.0)
    assert load["punch_x_mm"] is None
    assert load["punch_y_mm"] is None


def test_match_at_and_just_beyond_tolerance() -> None:
    """Boundary inclusive at compare.length_mm; one step beyond is UNMATCHED (spec 0010 §4.9 M2)."""
    cases = load_cases("loads")
    at = _run(cases["loads-match-at-tolerance"])
    assert (at["status"], at["reason"], at["loads"][0]["joint"], at["loads"][0]["FZ_kN"]) == (
        "OK",
        None,
        "P1",
        -50.0,
    )
    beyond = _run(cases["loads-unmatched"])
    assert (beyond["status"], beyond["reason"]) == ("NEEDS_ENGINEER", "UNMATCHED")


def test_unmatched_with_both_plan_offsets_uses_sum_of_squares() -> None:
    """Plan distance is dx^2 + dy^2 (not dx^2 - dy^2); (8, 8) mm with tol 10 mm is unmatched.

    Hand derivation: 8^2 + 8^2 = 128 > 10^2 = 100 → UNMATCHED (spec 0010 §4.9 M2).
    """
    case = load_cases("loads")["loads-unmatched"]
    raw = copy.deepcopy(case.input)
    raw["safe_points"]["points"][0]["x_mm"] = 8.0
    raw["safe_points"]["points"][0]["y_mm"] = 8.0
    body = reactions_to_joint_loads(
        ReactionsInput.model_validate(raw), input_meta(case.refs, KINDS), TraceBuilder()
    ).model_dump(mode="json")
    assert (body["status"], body["reason"], body["loads"]) == ("NEEDS_ENGINEER", "UNMATCHED", [])


def test_chosen_cases_filter_transferred_patterns() -> None:
    """M1: only load_pattern / load_case items of the chosen combinations transfer."""
    body = _run(load_cases("loads")["loads-chosen-cases-only"])
    assert [row["pattern"] for row in body["loads"]] == ["DEAD"]
    assert body["status"] == "OK"


def test_unknown_chosen_case_is_invalid_argument() -> None:
    """A chosen case that is not an ETABS combination is INVALID_ARGUMENT (spec 0010 §4.9 M1)."""
    case = load_cases("loads")["loads-basic-negation"]
    inp = _input(case).model_copy(update={"cases": ["NO_SUCH_COMBO"]})
    with pytest.raises(ContractError) as caught:
        _call(inp, case)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.received) == (
        ErrorCode.INVALID_ARGUMENT,
        "cases",
        "NO_SUCH_COMBO",
    )
    assert detail.message == "chosen case NO_SUCH_COMBO is not an ETABS combination"


def test_two_missing_combinations_are_both_listed_to_add() -> None:
    """Step 2: every chosen ETABS combination absent from SAFE is listed; continue, do not stop at the first."""
    case = load_cases("loads")["loads-basic-negation"]
    raw = copy.deepcopy(case.input)
    raw["etabs_load_set"]["combinations"].append(
        {
            "name": "S2",
            "type": "linear_add",
            "items": [
                {
                    "case": {"case": "DEAD", "case_type": "load_pattern", "step": None},
                    "scale_ratio": 1.0,
                }
            ],
        }
    )
    raw["cases"] = ["S1", "S2"]
    body = reactions_to_joint_loads(
        ReactionsInput.model_validate(raw), input_meta(case.refs, KINDS), TraceBuilder()
    ).model_dump(mode="json")
    assert body["status"] == "OK"
    assert [combo["name"] for combo in body["combinations_to_add"]] == ["S1", "S2"]


@pytest.mark.parametrize(
    ("changes", "code", "message", "expected", "received", "hint"),
    [
        (
            None,
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {LENGTH} is missing or not confirmed",
            None,
            None,
            f"confirm {LENGTH}",
        ),
        (
            {"confirmed": False},
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {LENGTH} is missing or not confirmed",
            None,
            None,
            f"confirm {LENGTH}",
        ),
        (
            {"unit": "kN"},
            ErrorCode.UNIT_MISMATCH,
            f"basis field {LENGTH} must be in mm",
            {"unit": "mm"},
            "kN",
            None,
        ),
        (
            {"value": True},
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {LENGTH} is not a number",
            None,
            None,
            None,
        ),
        (
            {"value": -1.0},
            ErrorCode.OUT_OF_RANGE,
            f"basis field {LENGTH} is below zero",
            {"min": 0},
            -1.0,
            None,
        ),
    ],
)
def test_compare_length_basis_refusals(
    changes: dict[str, object] | None,
    code: ErrorCode,
    message: str,
    expected: object,
    received: object,
    hint: str | None,
) -> None:
    """Spec 0003 §4.4 / 0010 §4.9: compare.length_mm present, confirmed, in mm, a number, >= 0."""
    case = load_cases("loads")["loads-basic-negation"]
    inp = _input(case)
    fields = dict(inp.basis.fields)
    if changes is None:
        del fields[LENGTH]
    else:
        fields[LENGTH] = fields[LENGTH].model_copy(update=changes)
    basis = DesignBasis.model_construct(template=None, fields=fields)
    with pytest.raises(ContractError) as caught:
        _call(inp.model_copy(update={"basis": basis}), case)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (code, "basis", message)
    assert (detail.expected, detail.received, detail.hint) == (expected, received, hint)


def test_compare_length_zero_is_accepted_when_points_coincide() -> None:
    """compare.length_mm = 0 is allowed (spec 0003 §4.4 >= 0); coincident points still match."""
    case = load_cases("loads")["loads-basic-negation"]
    inp = _input(case)
    fields = dict(inp.basis.fields)
    fields[LENGTH] = fields[LENGTH].model_copy(update={"value": 0.0})
    basis = DesignBasis.model_construct(template=None, fields=fields)
    body = _call(inp.model_copy(update={"basis": basis}), case).model_dump(mode="json")
    assert (body["status"], body["loads"][0]["joint"]) == ("OK", "P1")


def test_soft_outcome_trace_records_status_uses() -> None:
    """Soft §4.9 outcomes record the status step with uses pointing at the preceding soft step."""
    case = load_cases("loads")["loads-unmatched"]
    trace = TraceBuilder()
    _run(case, trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    steps = {step.name: (step.value, step.formula, step.source, list(step.uses)) for step in built.steps}
    assert steps["unmatched_subject"][0] == "J1"
    assert steps["status"] == (
        "NEEDS_ENGINEER",
        "engineering soft outcome UNMATCHED",
        "spec 0010 4.9",
        ["unmatched_subject"],
    )
    assert built.outputs == ["status"]


def test_ok_trace_records_compare_length_input() -> None:
    """Successful runs record compare_length with unit mm and the basis field ref (spec 0003 §4.4)."""
    case = load_cases("loads")["loads-basic-negation"]
    trace = TraceBuilder()
    _run(case, trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    inputs = {item.name: (item.value, item.unit, item.ref) for item in built.inputs}
    assert inputs["compare_length"] == (10.0, "mm", f"{case.refs['basis']}#/fields/{LENGTH}")
    assert inputs["chosen_cases"][0] == 1
