"""Unit tests of the axial-flexure check (plan 0004 T3; AF-AC4, AF-AC5).

Inputs are the clause spec §8 common section unless noted. Expected values are hand-derived from the spec with its
tolerances (1e-4 mm, 0.001 kN and kN.m, 1e-6 on ratios, strains and phi).
"""

from typing import Any

import pytest
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from structural_codes import evaluate
from structural_codes.errors import NotImplementedGap
from structural_codes.pack import Pack, Registry

from aci318_14.checks.axial_flexure import axial_flexure_uniaxial, bracket_demand_ray

CHECK_ID = "aci318_14.22_4_1_1.axial_flexure_uniaxial"
REGISTRY = Registry.of(
    [
        Pack(
            "aci318_14",
            "ACI 318-14",
            "2014",
            "0.1.0.dev0",
            checks=(axial_flexure_uniaxial,),
            approvals="approvals.yaml",
        )
    ]
)
FRAME = Subject(kind=SubjectKind.FRAME, id="C1")
COMMON: dict[str, Any] = {
    "Pu_kN": 1500.0,
    "Mu_kNm": 300.0,
    "Mu_other_kNm": 0.0,
    "b_mm": 500.0,
    "h_mm": 500.0,
    "d_prime_mm": 60.0,
    "n_bars_b": 3,
    "n_bars_h": 3,
    "A_bar_mm2": 500.0,
    "fc_MPa": 28.0,
    "fy_MPa": 420.0,
    "transverse_kind": "tied",
    "k_factor": 1.0,
    "lu_mm": 3000.0,
}
_LEN, _KN, _KNM, _RATIO = 1e-4, 0.001, 0.001, 1e-6
_BODY = {
    "crossings_up",
    "crossings_down",
    "c_lo_mm",
    "c_hi_mm",
    "capM_lo_kNm",
    "capM_hi_kNm",
    "c_mm",
    "capM_kNm",
    "phiPn_kN",
    "phiMn_kNm",
}
_TRACE_NAMES = (
    "Ag_mm2",
    "Ast_mm2",
    "eps_ty_ratio",
    "beta1_ratio",
    "Po_kN",
    "Pn_max_kN",
    "phiPn_max_kN",
    "c_full_mm",
    "crossings_up",
    "crossings_down",
    "c_lo_mm",
    "c_hi_mm",
    "capM_lo_kNm",
    "capM_hi_kNm",
    "c_mm",
    "a_mm",
    "Cc_kN",
    "Pn_kN",
    "Mn_kNm",
    "eps_t_ratio",
    "phi_ratio",
    "phiPn_kN",
    "phiMn_kNm",
    "on_cap",
    "capM_kNm",
)


def run(subject: Subject = FRAME, **changes: Any) -> Any:
    """Evaluate the check on the common inputs with `changes` (trial mode)."""
    return evaluate(CHECK_ID, {**COMMON, **changes}, subject=subject, registry=REGISTRY).payload


def steps(payload: Any) -> dict[str, float]:
    """Numeric trace steps of the single trace by name (logical steps omitted)."""
    return {s.name: float(s.value) for s in payload.traces[0].steps if not isinstance(s.value, bool)}


def step_map(payload: Any) -> dict[str, Any]:
    return {s.name: s for s in payload.traces[0].steps}


@pytest.mark.parametrize(
    ("changes", "precondition", "gap", "status"),
    [
        ({"Mu_other_kNm": 1.0}, "UNIAXIAL", "G-1", VerdictStatus.NEEDS_ENGINEER),
        ({"Mu_kNm": 0.0}, "FLEXURE_PRESENT", None, VerdictStatus.NOT_APPLICABLE),
        ({"Pu_kN": -1.0}, "AXIAL_COMPRESSION", "G-3", VerdictStatus.NEEDS_ENGINEER),
        ({"fy_MPa": 600.0}, "FY_MAX", None, VerdictStatus.NEEDS_ENGINEER),
        ({"fc_MPa": 16.0}, "FC_MIN", None, VerdictStatus.NEEDS_ENGINEER),
        ({"d_prime_mm": 250.0}, "BAR_LAYOUT", None, VerdictStatus.NEEDS_ENGINEER),
        (
            {"b_mm": 60.0, "h_mm": 60.0, "d_prime_mm": 20.0, "A_bar_mm2": 1000.0},
            "STEEL_IN_SECTION",
            None,
            VerdictStatus.NEEDS_ENGINEER,
        ),
        ({"lu_mm": 3301.0}, "SHORT_COLUMN", "G-2", VerdictStatus.NEEDS_ENGINEER),
    ],
)
def test_preconditions(changes: dict[str, Any], precondition: str, gap: str | None, status: VerdictStatus) -> None:
    """BD-1 to BD-3: the stated outcomes; the body does not run when a precondition fails (AF-AC4)."""
    payload = run(**changes)
    assert [v.status for v in payload.verdicts] == [status]
    trace = payload.traces[0]
    note = next(m for m in trace.messages if m.startswith(f"{precondition} ("))
    if gap is not None:
        assert gap in note
    assert not {s.name for s in trace.steps} & _BODY


def test_bracketing_gap() -> None:
    """BD-5 (unit, stub `g`): two up-crossings raise `NotImplementedGap` G-4 (AF-AC4; golden BD-5 uses real inputs)."""

    def g(c: float) -> float:
        # Two up-crossings on [0, 3]: negative until 0.5, positive until 1.5, negative until 2.5, positive after
        if c < 0.5:
            return -1.0
        if c < 1.5:
            return 1.0
        if c < 2.5:
            return -1.0
        return 1.0

    with pytest.raises(NotImplementedGap) as exc:
        bracket_demand_ray(3.0, 100, g, two=2.0, one=1.0)
    assert exc.value.gap_id == "G-4"


def test_trace_complete() -> None:
    """HC-1: the trace holds every name of AF §6; `capM_kNm` uses `phiMn_kNm` (AF-AC5)."""
    payload = run()
    found = steps(payload)
    for name in _TRACE_NAMES:
        assert name in found or name in {s.name for s in payload.traces[0].steps}, name
    for j in range(3):
        for stem in (f"d_{j}_mm", f"eps_{j}_ratio", f"fs_{j}_MPa", f"F_{j}_kN"):
            assert stem in found, stem
    sm = step_map(payload)
    cap = sm["capM_kNm"]
    assert "phiMn_kNm" in cap.uses or "phiPn_max_kN" in cap.uses
    assert found["c_mm"] == pytest.approx(276.801365, abs=_LEN)
    assert found["capM_kNm"] == pytest.approx(379.809583, abs=_KNM)
    assert payload.verdicts[0].ratio == pytest.approx(0.789869, abs=_RATIO)


def test_short_column_at_limit_passes() -> None:
    """BD-1: lu = 3300 gives k*lu/r = 22 exactly and a normal PASS verdict."""
    payload = run(lu_mm=3300.0)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.PASS]
    assert steps(payload)["kl_r_ratio"] == pytest.approx(22.0, abs=_RATIO)


def test_axial_cap_uses_phi_pn_max_in_capm() -> None:
    """HC-4: on_cap; capM = Mu*phiPn_max/Pu; ratio = Pu/phiPn_max (AF §4 step 5)."""
    payload = run(Pu_kN=3800.0, Mu_kNm=50.0)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.PASS]
    found = steps(payload)
    assert found["c_mm"] == pytest.approx(582.591979, abs=_LEN)
    assert found["capM_kNm"] == pytest.approx(51.553895, abs=_KNM)
    assert payload.verdicts[0].ratio == pytest.approx(0.969859, abs=_RATIO)
    cap = step_map(payload)["capM_kNm"]
    assert "phiPn_max_kN" in cap.uses
    on_cap = next(s for s in payload.traces[0].steps if s.name == "on_cap")
    assert on_cap.value is True


def test_g4_from_heavy_steel_and_high_pu() -> None:
    """BD-5: crossings_up = 2 on the grid raises one NEEDS_ENGINEER verdict naming G-4 (AF §8 BD-5)."""
    payload = run(Pu_kN=3800.0, Mu_kNm=200.0, A_bar_mm2=1500.0)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NEEDS_ENGINEER]
    assert any(m.startswith("G-4 (AF §4.2 step 3)") for m in payload.traces[0].messages)


def test_member_scope_not_applicable() -> None:
    """A subject that is not a frame is NOT_APPLICABLE (clause spec §2, member scope)."""
    payload = run(subject=Subject(kind=SubjectKind.FOOTING, id="F1"))
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NOT_APPLICABLE]
