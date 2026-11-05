"""Preconditions, the moment-transfer gap and constants of the punching shear check (plan 0002 T5; PS-AC2, PS-AC3).

Inputs are the clause spec §8 common inputs; expected values are the spec's §8 hand values with its tolerances
(1e-5 MPa on stresses, 0.001 kN on forces, 1e-6 on ratios).
"""

from typing import Any

import pytest
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14.checks.punching_shear import punching_shear

CHECK_ID = "aci318_14.22_6_5_2.punching_shear"
REGISTRY = Registry.of(
    [Pack("aci318_14", "ACI 318-14", "2014", "0.1.0.dev0", checks=(punching_shear,), approvals="approvals.yaml")]
)
FOOTING = Subject(kind=SubjectKind.FOOTING, id="F1")
COMMON: dict[str, Any] = {
    "FX_kN": 0.0,
    "FY_kN": 0.0,
    "FZ_kN": 1700.0,
    "MX_kNm": 0.0,
    "MY_kNm": 0.0,
    "Lx_mm": 2500.0,
    "Ly_mm": 2500.0,
    "cx_mm": 400.0,
    "cy_mm": 400.0,
    "d_mm": 500.0,
    "reaction_height_mm": 0.0,
    "fc_MPa": 28.0,
    "concrete_class": "normalweight",
}
_V_KN = 0.001
_STRESS = 1e-5
_RATIO = 1e-6
_BODY = {"b1_mm", "bo_mm", "Vu_kN", "vu_MPa", "phivc_MPa"}


def run(subject: Subject = FOOTING, **changes: Any) -> VerdictSet:
    """Evaluate the check on the common inputs with `changes` (trial mode)."""
    return evaluate(CHECK_ID, {**COMMON, **changes}, subject=subject, registry=REGISTRY).payload


@pytest.mark.parametrize(
    ("changes", "precondition", "gap"),
    [
        ({"d_mm": 2200.0}, "PERIMETER_INSIDE", "G-3"),
        ({"Ly_mm": 800.0}, "PERIMETER_INSIDE", "G-3"),
        ({"Lx_mm": 1200.0, "Ly_mm": 3000.0, "cx_mm": 900.0, "cy_mm": 300.0}, "PERIMETER_INSIDE", "G-3"),
        ({"Lx_mm": 3000.0, "Ly_mm": 1200.0, "cx_mm": 300.0, "cy_mm": 900.0}, "PERIMETER_INSIDE", "G-3"),
        ({"concrete_class": "sand_lightweight"}, "NORMALWEIGHT", "G-1"),
        ({"concrete_class": "lightweight"}, "NORMALWEIGHT", "G-1"),
        ({"fc_MPa": 16.0}, "FC_MIN", None),
        ({"FZ_kN": 0.0}, "COMPRESSION", None),
        ({"FZ_kN": 100.0, "MY_kNm": 200.0}, "FULL_CONTACT", "G-2"),
    ],
)
def test_preconditions(changes: dict[str, Any], precondition: str, gap: str | None) -> None:
    """BD-1 and BD-3: one NEEDS_ENGINEER verdict naming the precondition (and gap); the body does not run (PS-AC2)."""
    payload = run(**changes)
    assert len(payload.verdicts) == 1
    assert payload.verdicts[0].status is VerdictStatus.NEEDS_ENGINEER
    trace = payload.traces[0]
    note = next(m for m in trace.messages if m.startswith(f"{precondition} ("))
    if gap is not None:
        assert gap in note
    assert not {s.name for s in trace.steps} & _BODY


def test_limits_give_normal_verdicts() -> None:
    """At `fc = 17 MPa` and at `cx + d = Lx`, `cy + d = Ly` (E-1) the body runs; at equality `Vu = 0`, PASS (PS-AC2)."""
    at_fc = run(fc_MPa=17.0)
    assert [v.status for v in at_fc.verdicts] == [VerdictStatus.PASS]
    edge = run(d_mm=2100.0)
    (verdict,) = edge.verdicts
    assert verdict.status is VerdictStatus.PASS
    assert verdict.ratio == pytest.approx(0.0, abs=_RATIO)
    steps = {s.name: s.value for s in edge.traces[0].steps}
    assert steps["Vu_kN"] == pytest.approx(0.0, abs=_V_KN)


@pytest.mark.parametrize(
    "changes",
    [
        {"Lx_mm": 1400.0, "Ly_mm": 3000.0, "cx_mm": 900.0, "cy_mm": 300.0},
        {"Lx_mm": 3000.0, "Ly_mm": 1400.0, "cx_mm": 300.0, "cy_mm": 900.0},
    ],
)
def test_one_direction_at_the_limit(changes: dict[str, Any]) -> None:
    """E-1 in one direction only: `c + d = L` along the long column side, the other well inside; the body runs.

    Hand values (clause spec §4): b1*b2 = 1400*800 mm2, A = 4.2e6 mm2, Vu = 1700*(4.2e6 - 1.12e6)/4.2e6 kN,
    bo = 4400 mm, vu = Vu/(bo*d), beta = 3 so expression (b) governs as in HC-2: phivc = 1.124444 MPa.
    """
    payload = run(**changes)
    (verdict,) = payload.verdicts
    assert verdict.status is VerdictStatus.PASS
    assert verdict.ratio == pytest.approx(0.503953, abs=_RATIO)
    steps = {s.name: s.value for s in payload.traces[0].steps}
    assert steps["Vu_kN"] == pytest.approx(1246.666667, abs=_V_KN)
    assert steps["vu_MPa"] == pytest.approx(0.566667, abs=_STRESS)


@pytest.mark.parametrize(
    "changes",
    [
        {"MX_kNm": 10.0},
        {"MY_kNm": 10.0},
        {"FY_kN": 5.0, "reaction_height_mm": 600.0},
    ],
)
def test_moment_transfer_gap(changes: dict[str, Any]) -> None:
    """BD-2: a non-zero base moment gives one NEEDS_ENGINEER verdict naming G-4 and 8.4.4.2 (PS-AC3)."""
    payload = run(**changes)
    (verdict,) = payload.verdicts
    assert verdict.status is VerdictStatus.NEEDS_ENGINEER
    trace = payload.traces[0]
    assert any("G-4" in m and "8.4.4.2" in m for m in trace.messages)
    names = {s.name for s in trace.steps}
    assert {"Mbx_kNm", "Mby_kNm"} <= names
    assert not names & _BODY


def test_member_scope() -> None:
    """A subject that is not a footing is NOT_APPLICABLE (clause spec §2, member scope)."""
    payload = run(subject=Subject(kind=SubjectKind.FRAME, id="C1"))
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NOT_APPLICABLE]


def test_verdict_and_trace() -> None:
    """HC-1: one verdict, demand vu and capacity phivc in MPa at clause 22.6.5.2; §6 trace names in order."""
    payload = run()
    (verdict,) = payload.verdicts
    assert verdict.demand is not None
    assert verdict.capacity is not None
    assert verdict.demand.unit == verdict.capacity.unit == "MPa"
    assert verdict.demand.value == pytest.approx(0.822044, abs=_STRESS)
    assert verdict.capacity.value == pytest.approx(1.309647, abs=_STRESS)
    assert verdict.ratio == pytest.approx(0.627684, abs=_RATIO)
    assert verdict.clause == "22.6.5.2"
    assert verdict.status is VerdictStatus.PASS
    trace = payload.traces[0]
    names = [s.name for s in trace.steps]
    order = ["q_min_kPa", "b1_mm", "b2_mm", "bo_mm", "Vu_kN", "vu_MPa", "sf", "beta_ratio"]
    order += ["vc_a_MPa", "vc_b_MPa", "vc_c_MPa", "vc_MPa", "phivc_MPa"]
    assert [n for n in names if n in order] == order
    steps = {s.name: s for s in trace.steps}
    assert steps["sf"].unit is None
    assert steps["sf"].value == pytest.approx(28.0**0.5, abs=1e-9)
    assert steps["beta_ratio"].value == pytest.approx(1.0, abs=_RATIO)


def test_sf_cap() -> None:
    """At `fc = 80 MPa`, `sf` is capped at `sf_max = 8.3` (22.6.3.1): `phivc = 0.75*0.33*8.3 = 2.054250 MPa`."""
    payload = run(fc_MPa=80.0)
    steps = {s.name: s.value for s in payload.traces[0].steps}
    assert steps["sf"] == pytest.approx(8.3, abs=1e-9)
    assert steps["phivc_MPa"] == pytest.approx(2.054250, abs=_STRESS)


def test_constants() -> None:
    """The §5 constants are recorded with their citations."""
    trace = run().traces[0]
    cited = {c.name: c.cited for c in trace.constants}
    expected = {
        "phi_v": (0.75, "ACI 318-14 Table 21.2.1"),
        "c_a": (0.33, "ACI 318-14 Table 22.6.5.2 (a)"),
        "c_b": (0.17, "ACI 318-14 Table 22.6.5.2 (b)"),
        "c_b2": (2, "ACI 318-14 Table 22.6.5.2 (b)"),
        "c_c": (0.083, "ACI 318-14 Table 22.6.5.2 (c)"),
        "c_c2": (2, "ACI 318-14 Table 22.6.5.2 (c)"),
        "alphas": (40, "ACI 318-14 22.6.5.3"),
        "lambda_nw": (1.0, "ACI 318-14 19.2.4.2"),
        "sf_max": (8.3, "ACI 318-14 "),
        "fc_min": (17, "ACI 318-14 Table 19.2.1.1"),
        "c_perim": (2, "Geometry"),
        "k_kilo": (0.001, "SI prefix kilo"),
    }
    for name, (value, source) in expected.items():
        assert cited[name].value == pytest.approx(value), name
        assert cited[name].source.startswith(source), name
