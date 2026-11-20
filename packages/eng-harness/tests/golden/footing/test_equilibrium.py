"""Golden cases of harness.safe_equilibrium (plan 0010 T10; spec 0010 AC25, section 4.9)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis

from eng_harness.calc import TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.footing.safe_equilibrium import EquilibriumInput, safe_equilibrium

from . import FootingGoldenCase, input_meta, load_cases

CALC_ID = "harness.safe_equilibrium"
KINDS = {
    "loads": "harness.joint_loads/1",
    "base_reactions": "harness.base_reactions/1",
    "safe_load_set": "model.load_set/1",
    "basis": "basis.design_basis/1",
}
STEMS = [
    "equilibrium-at-tolerance",
    "equilibrium-fail-outside",
    "equilibrium-pass-within",
    "equilibrium-self-weight-not-compared",
]
TOLERANCE = "checks.equilibrium_relative_tolerance_ratio"
DIGEST = "ab" * 32


def _run(case: FootingGoldenCase, trace: TraceBuilder | None = None, **changes: Any) -> dict[str, Any]:
    raw = copy.deepcopy(case.input) | changes
    result = safe_equilibrium(
        EquilibriumInput.model_validate(raw), input_meta(case.refs, KINDS), trace or TraceBuilder()
    )
    return result.model_dump(mode="json")


def _input(case: FootingGoldenCase) -> EquilibriumInput:
    return EquilibriumInput.model_validate(copy.deepcopy(case.input))


def _call(inp: EquilibriumInput, case: FootingGoldenCase, trace: TraceBuilder | None = None) -> Any:
    return safe_equilibrium(inp, input_meta(case.refs, KINDS), trace or TraceBuilder())


def test_golden_cases() -> None:
    """AC25: within and outside the tolerance; a self-weight pattern not compared; boundary inclusive."""
    cases = load_cases("equilibrium")
    assert sorted(cases) == STEMS
    actual = {stem: _run(case) for stem, case in cases.items()}
    assert {stem: body for stem, body in actual.items() if body != cases[stem].expected} == {}


def test_equilibrium_within_at_and_beyond_relative_tolerance() -> None:
    """Spec 0010 §4.9 step 6: ||R|-|A|| ≤ tol·|A| is PASS at and within; one past is FAIL."""
    cases = load_cases("equilibrium")
    within = _run(cases["equilibrium-pass-within"])
    assert within["patterns"][0]["status"] == "PASS"
    # Hand: |A|=1000, |R|=1010, tol=0.01 → limit=10; |1010-1000|=10 ≤ 10 → PASS
    at = _run(cases["equilibrium-at-tolerance"])
    assert (at["patterns"][0]["applied_kN"], at["patterns"][0]["reaction_kN"], at["patterns"][0]["status"]) == (
        -1000.0,
        -1010.0,
        "PASS",
    )
    # Hand: |R|=1020 → |1020-1000|=20 > 10 → FAIL
    outside = _run(cases["equilibrium-fail-outside"])
    assert (outside["patterns"][0]["reaction_kN"], outside["patterns"][0]["status"]) == (-1020.0, "FAIL")


def test_self_weight_pattern_is_not_compared() -> None:
    """Self-weight patterns (self_weight_ratio > 0) are NOT_COMPARED (spec 0010 §4.9 step 6)."""
    body = _run(load_cases("equilibrium")["equilibrium-self-weight-not-compared"])
    row = body["patterns"][0]
    assert (row["self_weight"], row["status"]) == (True, "NOT_COMPARED")


def test_union_of_patterns_counts_a_missing_side_as_zero() -> None:
    """Patterns are applied union reactions; a missing side is zero (spec 0010 §4.9 step 6).

    Hand: applied LIVE FZ = -500 kN only; no LIVE base reaction so A=-500, R=0;
    tol=0.01 so limit=5; |0-500|=500 > 5 so FAIL. DEAD from the pass-within golden stays PASS.
    """
    case = load_cases("equilibrium")["equilibrium-pass-within"]
    raw = copy.deepcopy(case.input)
    raw["loads"]["loads"].append(
        {
            "joint": "P1",
            "pattern": "LIVE",
            "FX_kN": 0.0,
            "FY_kN": 0.0,
            "FZ_kN": -500.0,
            "MX_kNm": 0.0,
            "MY_kNm": 0.0,
            "MZ_kNm": 0.0,
            "punch_x_mm": None,
            "punch_y_mm": None,
        }
    )
    raw["safe_load_set"]["patterns"].append({"name": "LIVE", "type": "live", "self_weight_ratio": 0.0})
    body = safe_equilibrium(
        EquilibriumInput.model_validate(raw), input_meta(case.refs, KINDS), TraceBuilder()
    ).model_dump(mode="json")
    by_name = {row["pattern"]: row for row in body["patterns"]}
    assert set(by_name) == {"DEAD", "LIVE"}
    assert by_name["DEAD"]["status"] == "PASS"
    assert (by_name["LIVE"]["applied_kN"], by_name["LIVE"]["reaction_kN"], by_name["LIVE"]["status"]) == (
        -500.0,
        0.0,
        "FAIL",
    )


def test_reaction_only_pattern_counts_applied_as_zero() -> None:
    """A reaction-only non-self-weight pattern has A=0; any nonzero R fails (magnitudes, §4.9 step 6).

    Hand: R = -40 kN, A = 0, tol = 0.01 → limit = 0; |40-0| = 40 > 0 → FAIL.
    """
    case = load_cases("equilibrium")["equilibrium-pass-within"]
    raw = copy.deepcopy(case.input)
    raw["base_reactions"]["rows"].append(
        {
            "case": {"case": "WIND", "case_type": "load_pattern", "step": None},
            "FX_kN": 0.0,
            "FY_kN": 0.0,
            "FZ_kN": -40.0,
            "MX_kNm": 0.0,
            "MY_kNm": 0.0,
            "MZ_kNm": 0.0,
        }
    )
    raw["safe_load_set"]["patterns"].append({"name": "WIND", "type": "other", "self_weight_ratio": 0.0})
    body = safe_equilibrium(
        EquilibriumInput.model_validate(raw), input_meta(case.refs, KINDS), TraceBuilder()
    ).model_dump(mode="json")
    wind = next(row for row in body["patterns"] if row["pattern"] == "WIND")
    assert (wind["applied_kN"], wind["reaction_kN"], wind["status"]) == (0.0, -40.0, "FAIL")


@pytest.mark.parametrize(
    ("changes", "code", "message", "expected", "received", "hint"),
    [
        (
            None,
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {TOLERANCE} is missing or not confirmed",
            None,
            None,
            f"confirm {TOLERANCE}",
        ),
        (
            {"confirmed": False},
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {TOLERANCE} is missing or not confirmed",
            None,
            None,
            f"confirm {TOLERANCE}",
        ),
        (
            {"unit": "mm"},
            ErrorCode.UNIT_MISMATCH,
            f"basis field {TOLERANCE} must have unit 1",
            {"unit": "1"},
            "mm",
            None,
        ),
        (
            {"value": True},
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {TOLERANCE} is not a number",
            None,
            None,
            None,
        ),
        (
            {"value": -0.01},
            ErrorCode.OUT_OF_RANGE,
            f"basis field {TOLERANCE} is below zero",
            {"min": 0},
            -0.01,
            None,
        ),
    ],
)
def test_equilibrium_tolerance_basis_refusals(
    changes: dict[str, object] | None,
    code: ErrorCode,
    message: str,
    expected: object,
    received: object,
    hint: str | None,
) -> None:
    """Spec 0003 §4.4 / 0010 §4.9: relative tolerance present, confirmed, unit 1, a number, >= 0."""
    case = load_cases("equilibrium")["equilibrium-pass-within"]
    inp = _input(case)
    fields = dict(inp.basis.fields)
    if changes is None:
        del fields[TOLERANCE]
    else:
        fields[TOLERANCE] = fields[TOLERANCE].model_copy(update=changes)
    basis = DesignBasis.model_construct(template=None, fields=fields)
    with pytest.raises(ContractError) as caught:
        _call(inp.model_copy(update={"basis": basis}), case)
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (code, "basis", message)
    assert (detail.expected, detail.received, detail.hint) == (expected, received, hint)


def test_equilibrium_tolerance_zero_passes_only_when_magnitudes_equal() -> None:
    """tol = 0 is allowed; PASS only when |R| == |A| (spec 0010 §4.9 step 6)."""
    case = load_cases("equilibrium")["equilibrium-pass-within"]
    inp = _input(case)
    fields = dict(inp.basis.fields)
    fields[TOLERANCE] = fields[TOLERANCE].model_copy(update={"value": 0.0})
    basis = DesignBasis.model_construct(template=None, fields=fields)
    # |R|=1004 ≠ |A|=1000 → FAIL at tol 0
    fail_body = _call(inp.model_copy(update={"basis": basis}), case).model_dump(mode="json")
    assert fail_body["tolerance"] == 0.0
    assert fail_body["patterns"][0]["status"] == "FAIL"
    # equal magnitudes → PASS
    raw = copy.deepcopy(case.input)
    raw["basis"]["fields"][TOLERANCE]["value"] = 0.0
    raw["base_reactions"]["rows"][0]["FZ_kN"] = -1000.0
    pass_body = safe_equilibrium(
        EquilibriumInput.model_validate(raw), input_meta(case.refs, KINDS), TraceBuilder()
    ).model_dump(mode="json")
    assert pass_body["patterns"][0]["status"] == "PASS"


def test_ok_trace_records_equilibrium_tolerance_input() -> None:
    """Successful runs record equilibrium_tolerance with unit 1 and the basis field ref."""
    case = load_cases("equilibrium")["equilibrium-pass-within"]
    trace = TraceBuilder()
    _run(case, trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    inputs = {item.name: (item.value, item.unit, item.ref) for item in built.inputs}
    assert inputs["equilibrium_tolerance"] == (
        0.01,
        "1",
        f"{case.refs['basis']}#/fields/{TOLERANCE}",
    )
