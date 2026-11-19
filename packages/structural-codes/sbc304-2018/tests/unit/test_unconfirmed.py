"""Unconfirmed rows use the core input and scope rules and stop at their declared gap (AC4, AC6, AC7)."""

import re
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import ParamSpec
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from structural_codes import evaluate
from structural_codes.applicability import Outcome
from structural_codes.check import Check
from structural_codes.errors import CheckDefinitionError, NotImplementedGap
from structural_codes.inputs import CheckInputs
from structural_codes.overlay import Overridden
from structural_codes.pack import Pack, Registry

from sbc304_2018._overlay import build_overlay
from sbc304_2018.clause_map import CLAUSE_MAP

_BASE_PACK = next(pack for pack in Registry.discover().packs if pack.name == "aci318_14")

# Inputs only, transcribed from the first hand-check case (HC-1) of each matching ACI clause spec §8 and
# aci318-14/tests/data/golden/verification/<check_id>.yaml. No SBC numeric result is expected.
_CASES: dict[str, tuple[str, dict[str, Any]]] = {
    "aci318_14.10_6_1_1.longitudinal_reinforcement_limits": ("frame", {"Ag_mm2": 250000, "Ast_mm2": 4000}),
    "aci318_14.13_2_7_1.flexure_at_column_face": (
        "footing",
        {
            "As_x_mm2": 2800,
            "As_y_mm2": 2800,
            "FX_kN": 0,
            "FY_kN": 0,
            "FZ_kN": 1700,
            "Lx_mm": 2500,
            "Ly_mm": 2500,
            "MX_kNm": 0,
            "MY_kNm": 0,
            "cx_mm": 400,
            "cy_mm": 400,
            "d_x_mm": 500,
            "d_y_mm": 500,
            "fc_MPa": 28,
            "fy_MPa": 420,
            "reaction_height_mm": 0,
        },
    ),
    "aci318_14.13_3_1_1.bearing_pressure_service": (
        "footing",
        {
            "FX_kN": 0.0,
            "FY_kN": 0.0,
            "FZ_kN": 1200.0,
            "Lx_mm": 2500.0,
            "Ly_mm": 2500.0,
            "MX_kNm": 0.0,
            "MY_kNm": 0.0,
            "allowable_kind": "gross",
            "gamma_c_kN_m3": 24.0,
            "gamma_s_kN_m3": 18.0,
            "h_mm": 600.0,
            "q_allow_kPa": 250.0,
            "reaction_height_mm": 0.0,
            "soil_depth_mm": 1000.0,
            "surcharge_kPa": 0.0,
        },
    ),
    "aci318_14.22_4_1_1.axial_flexure_uniaxial": (
        "frame",
        {
            "A_bar_mm2": 500,
            "Mu_kNm": 300,
            "Mu_other_kNm": 0,
            "Pu_kN": 1500,
            "b_mm": 500,
            "d_prime_mm": 60,
            "fc_MPa": 28,
            "fy_MPa": 420,
            "h_mm": 500,
            "k_factor": 1,
            "lu_mm": 3000,
            "n_bars_b": 3,
            "n_bars_h": 3,
            "transverse_kind": "tied",
        },
    ),
    "aci318_14.22_4_2_1.max_axial_strength": (
        "frame",
        {
            "Ast_mm2": 4000,
            "Pu_kN": 3000,
            "b_mm": 500,
            "fc_MPa": 28,
            "fy_MPa": 420,
            "h_mm": 500,
            "k_factor": 1,
            "lu_mm": 3000,
            "transverse_kind": "tied",
        },
    ),
    "aci318_14.22_5_5_1.one_way_shear": (
        "footing",
        {
            "FX_kN": 0,
            "FY_kN": 0,
            "FZ_kN": 1700,
            "Lx_mm": 2500,
            "Ly_mm": 2500,
            "MX_kNm": 0,
            "MY_kNm": 0,
            "concrete_class": "normalweight",
            "cx_mm": 400,
            "cy_mm": 400,
            "d_x_mm": 500,
            "d_y_mm": 500,
            "fc_MPa": 28,
            "reaction_height_mm": 0,
        },
    ),
    "aci318_14.22_6_5_2.punching_shear": (
        "footing",
        {
            "FX_kN": 0,
            "FY_kN": 0,
            "FZ_kN": 1700,
            "Lx_mm": 2500,
            "Ly_mm": 2500,
            "MX_kNm": 0,
            "MY_kNm": 0,
            "concrete_class": "normalweight",
            "cx_mm": 400,
            "cy_mm": 400,
            "d_mm": 500,
            "fc_MPa": 28,
            "reaction_height_mm": 0,
        },
    ),
    "aci318_14.25_4_2_3.development_length_bottom_bars": (
        "footing",
        {
            "Lx_mm": 2500,
            "Ly_mm": 2500,
            "coating": "uncoated",
            "concrete_class": "normalweight",
            "cover_x_mm": 75,
            "cover_y_mm": 75,
            "cx_mm": 400,
            "cy_mm": 400,
            "db_x_mm": 16,
            "db_y_mm": 16,
            "end_cover_mm": 75,
            "fc_MPa": 28,
            "fy_MPa": 420,
            "s_x_mm": 200,
            "s_y_mm": 200,
        },
    ),
    "aci318_14.8_6_1_1.min_flexural_reinforcement": (
        "footing",
        {"As_x_mm2": 2800, "As_y_mm2": 2800, "Lx_mm": 2500, "Ly_mm": 2500, "fy_MPa": 420, "h_mm": 600},
    ),
}


@pytest.fixture(scope="module")
def overlay_pack() -> tuple[Registry, dict[str, Check]]:
    checks, overlay = build_overlay(CLAUSE_MAP, _BASE_PACK)
    pack = Pack("sbc304_2018", "SBC 304-2018", "2018", "0.1.0.dev0", checks, "approvals.yaml", _BASE_PACK.name, overlay)
    return Registry.of((_BASE_PACK, pack)), {
        entry.base_check_id: entry.check for entry in overlay.entries if isinstance(entry, Overridden)
    }


@pytest.mark.parametrize("base", _BASE_PACK.checks, ids=lambda check: check.meta.check_id)
def test_needs_engineer_with_gap(base: Check, overlay_pack: tuple[Registry, dict[str, Check]]) -> None:
    registry, by_base = overlay_pack
    base_id = base.meta.check_id
    check = by_base[base_id]
    kind, inputs = _CASES[base_id]
    row = next(row for row in CLAUSE_MAP if row.base_check_id == base_id)
    clause = f"unconfirmed (ACI 318-14 {base.meta.clauses[0]})"
    token, short = base_id.split(".")[1:]
    check_id = f"sbc304_2018.unconfirmed_aci_318_14_{token}.{short}"
    expected_reason = (
        f"SBC_CLAUSE_UNCONFIRMED: SBC 304-2018 clause not confirmed for {base_id} (ACI 318-14 {base.meta.clauses[0]}); "
        f"to confirm: {row.confirm} and the common items of clause-map §3"
    )
    result = evaluate(check_id, inputs, subject=Subject(kind=SubjectKind(kind), id="test"), registry=registry)
    (verdict,) = result.payload.verdicts
    assert (verdict.check_id, verdict.code, verdict.clause) == (check_id, "SBC 304-2018", clause)
    assert verdict.status == VerdictStatus.NEEDS_ENGINEER
    assert verdict.demand is None
    assert verdict.capacity is None
    assert verdict.ratio is None
    (trace,) = result.payload.traces
    assert trace.messages[-1] == f"{row.gap_id} ({clause}): {expected_reason}"
    assert trace.steps == []
    assert trace.constants == []
    assert trace.outputs == []

    assert check.meta.pack == "sbc304_2018"
    assert check.meta.edition == "2018"
    assert check.meta.title == f"SBC 304-2018, unconfirmed: {base.meta.title}"
    assert check.meta.clauses == (clause,)
    assert check.meta.spec == "sbc304_2018/clause-map.md"
    (gap,) = check.meta.gaps
    assert (gap.id, gap.clause, gap.reason) == (row.gap_id, clause, expected_reason)
    (precondition,) = check.preconditions
    assert (precondition.id, precondition.outcome, precondition.clause, precondition.description) == (
        "SBC_CONFIRMED",
        Outcome.NEEDS_ENGINEER,
        clause,
        expected_reason,
    )
    with pytest.raises(NotImplementedGap) as caught:
        precondition.test(None, None)
    assert (caught.value.gap_id, caught.value.clause, caught.value.reason) == (row.gap_id, clause, expected_reason)
    with pytest.raises(CheckDefinitionError, match=r"^SBC unconfirmed check body is unreachable$"):
        check.body(None, None)


@pytest.mark.parametrize("base", _BASE_PACK.checks, ids=lambda check: check.meta.check_id)
def test_member_scope_copied(base: Check, overlay_pack: tuple[Registry, dict[str, Check]]) -> None:
    registry, by_base = overlay_pack
    check = by_base[base.meta.check_id]
    assert check.meta.members == base.meta.members
    _, inputs = _CASES[base.meta.check_id]
    subject = Subject(kind=SubjectKind.JOINT, id="out-of-scope")
    assert subject.kind not in base.meta.members
    result = evaluate(check.meta.check_id, inputs, subject=subject, registry=registry)
    (verdict,) = result.payload.verdicts
    assert verdict.status == VerdictStatus.NOT_APPLICABLE
    (trace,) = result.payload.traces
    assert trace.messages[-1].startswith("member scope (")
    assert re.search(r"\bSBC_(CLAUSE_UNCONFIRMED|ROW_MISSING)\b", "\n".join(trace.messages)) is None


@pytest.mark.parametrize("base", _BASE_PACK.checks, ids=lambda check: check.meta.check_id)
def test_inputs_match_base(base: Check, overlay_pack: tuple[Registry, dict[str, Check]]) -> None:
    registry, by_base = overlay_pack
    check = by_base[base.meta.check_id]
    assert check.inputs is base.inputs
    assert issubclass(check.inputs, CheckInputs)
    assert issubclass(base.inputs, CheckInputs)
    assert check.inputs.model_json_schema() == base.inputs.model_json_schema()
    kind, inputs = _CASES[base.meta.check_id]
    # Use the model's cited lower bound, then step below it to exercise the same contract error for both checks.
    field, minimum = next(
        (name, lower)
        for name, info in base.inputs.model_fields.items()
        if name in inputs
        and isinstance(spec := info.json_schema_extra, ParamSpec)
        and (lower := spec.ge if spec.gt is None else spec.gt) is not None
    )
    for check_id in (base.meta.check_id, check.meta.check_id):
        with pytest.raises(ContractError) as caught:
            evaluate(
                check_id,
                {**inputs, field: minimum - 1},
                subject=Subject(kind=SubjectKind(kind), id="test"),
                registry=registry,
            )
        assert caught.value.detail.code == ErrorCode.OUT_OF_RANGE
        assert caught.value.detail.field == field
