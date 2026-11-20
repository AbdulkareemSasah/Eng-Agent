"""Stress-block rows, gaps, preconditions and directions of the flexure check (plan 0002 T6; FL-AC2, FL-AC3).

Inputs are the clause spec §8 common inputs; expected values are the spec's §8 hand values with its tolerances
(0.001 kN.m on moments, 1e-4 mm on lengths, 1e-6 on ratios and strains).
"""

from typing import Any

import pytest
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14.checks.flexure import flexure_at_column_face

CHECK_ID = "aci318_14.13_2_7_1.flexure_at_column_face"
REGISTRY = Registry.of(
    [
        Pack(
            "aci318_14",
            "ACI 318-14",
            "2014",
            "0.1.0.dev0",
            checks=(flexure_at_column_face,),
            approvals="approvals.yaml",
        )
    ]
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
    "d_x_mm": 500.0,
    "d_y_mm": 500.0,
    "As_x_mm2": 2800.0,
    "As_y_mm2": 2800.0,
    "reaction_height_mm": 0.0,
    "fc_MPa": 28.0,
    "fy_MPa": 420.0,
}
_M_KNM = 0.001
_MM = 1e-4
_RATIO = 1e-6
_BODY = {"Mu_x_kNm", "Mu_y_kNm", "phiMn_x_kNm", "phiMn_y_kNm"}


def run(subject: Subject = FOOTING, **changes: Any) -> VerdictSet:
    """Evaluate the check on the common inputs with `changes` (trial mode)."""
    return evaluate(CHECK_ID, {**COMMON, **changes}, subject=subject, registry=REGISTRY).payload


def steps(payload: VerdictSet) -> dict[str, float]:
    """Numeric trace steps of the single trace by name."""
    return {s.name: float(s.value) for s in payload.traces[0].steps}


@pytest.mark.parametrize(
    ("fc", "beta1"),
    [(17.0, 0.85), (28.0, 0.85), (40.0, 0.764286), (55.0, 0.65), (80.0, 0.65)],
)
def test_beta1_rows(fc: float, beta1: float) -> None:
    """BD-1: beta1 is 0.85 at fc = 28 and 0.65 at fc = 55 (row boundaries exact), the middle row in between (FL-AC2)."""
    payload = run(fc_MPa=fc)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.PASS, VerdictStatus.PASS]
    assert steps(payload)["beta1_ratio"] == pytest.approx(beta1, abs=_RATIO)


def test_beta1_boundaries_are_exact() -> None:
    """At the two row boundaries the value is the row's constant itself, with no rounding (Table 22.2.2.4.3)."""
    assert steps(run(fc_MPa=28.0))["beta1_ratio"] == 0.85
    assert steps(run(fc_MPa=55.0))["beta1_ratio"] == 0.65


def test_gaps_and_preconditions() -> None:
    """BD-2: one NEEDS_ENGINEER verdict naming G-2 and 21.2.2 with eps_t_x_ratio recorded; BD-3 at fy = 550 (FL-AC3).

    The other BD-3 and BD-4 outcomes are in `test_preconditions`.
    """
    payload = run(As_x_mm2=40000.0, As_y_mm2=40000.0)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NEEDS_ENGINEER]
    trace = payload.traces[0]
    assert any(m.startswith("G-2 (21.2.2)") for m in trace.messages), trace.messages
    found = steps(payload)
    assert found["c_x_mm"] == pytest.approx(332.179931, abs=_MM)
    assert found["eps_t_x_ratio"] == pytest.approx(0.001516, abs=_RATIO)
    assert "phiMn_x_kNm" not in found
    at_limit = run(fy_MPa=550.0)
    assert [v.status for v in at_limit.verdicts] == [VerdictStatus.PASS, VerdictStatus.PASS]


def test_tension_controlled_limit_is_inclusive() -> None:
    """BD-2.b: eps_t = eps_tc exactly is tension-controlled, so both verdicts PASS (clause spec §4 step 6; FL-AC3).

    Hand values: c = 0.003 * 500 / 0.008 = 187.5 mm, a = 0.85 * c = 159.375 mm,
    As = a * 0.85 * 28 * 2500 / 420 = 22578.125 mm2; every step is exact in binary floating point.
    """
    payload = run(As_x_mm2=22578.125, As_y_mm2=22578.125)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.PASS, VerdictStatus.PASS]
    found = steps(payload)
    assert found["c_x_mm"] == 187.5
    assert found["eps_t_x_ratio"] == 0.005
    assert found["eps_t_y_ratio"] == 0.005
    assert found["phiMn_x_kNm"] == pytest.approx(3587.170166, abs=_M_KNM)


def test_just_below_tension_controlled_limit() -> None:
    """BD-2.c: As_x = 22650 mm2 gives eps_t_x = 0.004975 < eps_tc: one NEEDS_ENGINEER verdict naming G-2 (FL-AC3)."""
    payload = run(As_x_mm2=22650.0)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NEEDS_ENGINEER]
    assert any(m.startswith("G-2 (21.2.2)") for m in payload.traces[0].messages)
    found = steps(payload)
    assert found["eps_t_x_ratio"] == pytest.approx(0.004975, abs=_RATIO)
    assert "phiMn_x_kNm" not in found


def test_gap_in_y_direction_alone() -> None:
    """BD-2.d: As_y = 40000 mm2 alone; X passes its strain test, Y raises G-2 from its own depth (FL-AC3)."""
    payload = run(As_y_mm2=40000.0)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NEEDS_ENGINEER]
    messages = [m for m in payload.traces[0].messages if m.startswith("G-2 (21.2.2)")]
    assert len(messages) == 1
    assert "eps_t_y_ratio" in messages[0]
    found = steps(payload)
    assert found["c_y_mm"] == pytest.approx(332.179931, abs=_MM)
    assert found["eps_t_y_ratio"] == pytest.approx(0.001516, abs=_RATIO)
    assert found["eps_t_x_ratio"] == pytest.approx(0.061509, abs=_RATIO)
    assert found["phiMn_x_kNm"] == pytest.approx(518.740518, abs=_M_KNM)
    assert "phiMn_y_kNm" not in found


def test_gap_uses_each_direction_own_depth() -> None:
    """BD-2.e: d_x != d_y; only Y, with the smaller depth, falls below eps_tc and raises G-2 (§4 step 6; FL-AC3).

    Common inputs with As_x = As_y = 22578.125 mm2 and d_y = 450 mm: c = 187.5 mm in both directions;
    eps_t_x = 0.003 * (500 - 187.5) / 187.5 = 0.005 (tension-controlled, phiMn_x = 3587.170166 kN.m recorded);
    eps_t_y = 0.003 * (450 - 187.5) / 187.5 = 0.0042 < eps_tc, so the result is one NEEDS_ENGINEER verdict naming G-2.
    """
    payload = run(As_x_mm2=22578.125, As_y_mm2=22578.125, d_y_mm=450.0)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NEEDS_ENGINEER]
    assert any(m.startswith("G-2 (21.2.2)") and "eps_t_y_ratio" in m for m in payload.traces[0].messages)
    found = steps(payload)
    assert found["eps_t_x_ratio"] == pytest.approx(0.005, abs=_RATIO)
    assert found["phiMn_x_kNm"] == pytest.approx(3587.170166, abs=_M_KNM)
    assert found["c_y_mm"] == pytest.approx(187.5, abs=_MM)
    assert found["eps_t_y_ratio"] == pytest.approx(0.0042, abs=_RATIO)
    assert "phiMn_y_kNm" not in found


@pytest.mark.parametrize(
    ("changes", "precondition", "gap"),
    [
        ({"fy_MPa": 600.0}, "FY_MAX", None),
        ({"fc_MPa": 16.0}, "FC_MIN", None),
        ({"FZ_kN": 0.0}, "COMPRESSION", None),
        ({"FZ_kN": 100.0, "MY_kNm": 200.0}, "FULL_CONTACT", "G-1"),
    ],
)
def test_preconditions(changes: dict[str, Any], precondition: str, gap: str | None) -> None:
    """BD-3, BD-4: one NEEDS_ENGINEER verdict naming the precondition (and gap); the body does not run (FL-AC3)."""
    payload = run(**changes)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NEEDS_ENGINEER]
    trace = payload.traces[0]
    note = next(m for m in trace.messages if m.startswith(f"{precondition} ("))
    if gap is not None:
        assert gap in note
    assert not {s.name for s in trace.steps} & _BODY


def test_member_scope() -> None:
    """A subject that is not a footing is NOT_APPLICABLE (clause spec §2, member scope)."""
    payload = run(subject=Subject(kind=SubjectKind.FRAME, id="C1"))
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NOT_APPLICABLE]


def test_hc1_values_and_trace() -> None:
    """HC-1 values; the §5 constants are recorded with their citations; X then Y verdicts in kN.m at 13.2.7.1."""
    payload = run()
    found = steps(payload)
    assert found["Lp_x_mm"] == pytest.approx(1050.0, abs=_MM)
    assert found["a_x_mm"] == pytest.approx(19.764706, abs=_MM)
    assert found["eps_t_x_ratio"] == pytest.approx(0.061509, abs=_RATIO)
    assert found["Mn_x_kNm"] == pytest.approx(576.378353, abs=_M_KNM)
    x, y = payload.verdicts
    assert x.demand is not None
    assert x.capacity is not None
    assert x.demand.unit == x.capacity.unit == "kN.m"
    assert x.demand.value == pytest.approx(374.85, abs=_M_KNM)
    assert x.capacity.value == pytest.approx(518.740518, abs=_M_KNM)
    assert x.ratio == pytest.approx(0.722616, abs=_RATIO)
    assert y.ratio == pytest.approx(0.722616, abs=_RATIO)
    assert x.clause == y.clause == "13.2.7.1"
    cited = {c.name: c.cited for c in payload.traces[0].constants}
    expected = {
        "phi_tc": (0.90, "ACI 318-14 Table 21.2.2"),
        "eps_tc": (0.005, "ACI 318-14 Table 21.2.2"),
        "eps_cu": (0.003, "ACI 318-14 22.2.2.1"),
        "alpha_1": (0.85, "ACI 318-14 22.2.2.4.1"),
        "beta1_hi": (0.85, "ACI 318-14 Table 22.2.2.4.3"),
        "beta1_lo": (0.65, "ACI 318-14 Table 22.2.2.4.3"),
        "fy_max": (550.0, "ACI 318-14 Table 20.2.2.4(a)"),
        "fc_min": (17.0, "ACI 318-14 Table 19.2.1.1"),
        "k_kilo_milli": (1.0e-6, "SI prefixes"),  # spec §5 k_kNm; its suffix would fix kN.m (core AC10)
    }
    for name, (value, source) in expected.items():
        assert cited[name].value == pytest.approx(value), name
        assert cited[name].source.startswith(source), name
    names = [s.name for s in payload.traces[0].steps]
    order = ["q_avg_kPa", "Mu_x_kNm", "Mu_y_kNm", "beta1_ratio", "a_x_mm", "c_x_mm", "eps_t_x_ratio", "Mn_x_kNm"]
    order += ["phiMn_x_kNm", "a_y_mm", "phiMn_y_kNm"]
    assert [n for n in names if n in order] == order


# Every recorded quantity in each row of Table 22.2.2.4.3, X and Y, with d_x != d_y, Lx != Ly and As_x/Ly != As_y/Lx
# so that a swapped direction, a fixed beta1 in c or alpha_1 in place of beta1 changes at least one value.
# Common inputs except Lx = 2000, Ly = 3000, d_x = 500, d_y = 450 mm, As_x = 3000, As_y = 2500 mm2 (clause spec §4):
# Mu_x = 3.0 * (1700/6.0) * 0.8^2 / 2 = 272.0, Mu_y = 2.0 * (1700/6.0) * 1.3^2 / 2 = 478.833333 kN.m;
# a_x = As_x fy / (0.85 fc Ly), a_y = As_y fy / (0.85 fc Lx); c = a / beta1; eps_t = 0.003 (d - c) / c;
# Mn = As fy (d - a/2) 1e-6; phiMn = 0.9 Mn; ratio = Mu / phiMn. Values rounded to 6 decimals.
_ROW_INPUTS: dict[str, Any] = {
    "Lx_mm": 2000.0,
    "Ly_mm": 3000.0,
    "d_x_mm": 500.0,
    "d_y_mm": 450.0,
    "As_x_mm2": 3000.0,
    "As_y_mm2": 2500.0,
}
_ROW_QUANTITIES: tuple[tuple[str, float], ...] = (("a_{}_mm", _MM), ("c_{}_mm", _MM), ("eps_t_{}_ratio", _RATIO))
_ROW_QUANTITIES += (("Mn_{}_kNm", _M_KNM), ("phiMn_{}_kNm", _M_KNM))


@pytest.mark.parametrize(
    ("fc", "beta1", "x_row", "y_row"),
    [
        (
            25.0,
            0.85,
            (19.764706, 23.252595, 0.061509, 617.548235, 555.793412, 0.489390),
            (24.705882, 29.065744, 0.043446, 459.529412, 413.576471, 1.157787),
        ),
        (
            40.0,
            0.764286,
            (12.352941, 16.162727, 0.089806, 622.217647, 559.995882, 0.485718),
            (15.441176, 20.203408, 0.063820, 464.393382, 417.954044, 1.145660),
        ),
        (
            60.0,
            0.65,
            (8.235294, 12.669683, 0.115393, 624.811765, 562.330588, 0.483701),
            (10.294118, 15.837104, 0.082243, 467.095588, 420.386029, 1.139032),
        ),
    ],
)
def test_every_quantity_in_each_beta1_row(
    fc: float, beta1: float, x_row: tuple[float, ...], y_row: tuple[float, ...]
) -> None:
    """Rows fc <= 28, between and >= 55 of Table 22.2.2.4.3: a, c, eps_t, Mn, phiMn and the ratio, X and Y (§4).

    Each row tuple is (a, c, eps_t, Mn, phiMn, ratio) of its direction.
    """
    payload = run(fc_MPa=fc, **_ROW_INPUTS)
    found = steps(payload)
    assert found["beta1_ratio"] == pytest.approx(beta1, abs=_RATIO)
    x, y = payload.verdicts
    demands = {"x": 272.0, "y": 478.833333}
    for s, row, verdict in (("x", x_row, x), ("y", y_row, y)):
        for (name, tol), value in zip(_ROW_QUANTITIES, row[:-1], strict=True):
            assert found[name.format(s)] == pytest.approx(value, abs=tol), name.format(s)
        assert verdict.demand is not None
        assert verdict.demand.value == pytest.approx(demands[s], abs=_M_KNM), s
        assert verdict.ratio == pytest.approx(row[-1], abs=_RATIO), s
    assert [x.status, y.status] == [VerdictStatus.PASS, VerdictStatus.FAIL]


def test_gap_at_upper_beta1_row_uses_beta1_in_c() -> None:
    """BD-2.f: fc = 55 (beta1 = 0.65), d_x = 600, d_y = 500 mm, As = 38958.33 mm2 both ways; Y alone raises G-2.

    a = 38958.33 * 420 / (0.85 * 55 * 2500) = 139.999988 mm; c = a / 0.65 = 215.384597 mm in both directions;
    eps_t_x = 0.003 * (600 - c) / c = 0.005357 (tension-controlled, phiMn_x = 0.9 * As fy (600 - a/2) 1e-6
    = 7804.911920 kN.m); eps_t_y = 0.003 * (500 - c) / c = 0.003964 < eps_tc. With c = a / 0.85 (164.705868 mm) the
    Y strain would read 0.006107 and the section would wrongly pass with phi = 0.90.
    """
    payload = run(fc_MPa=55.0, d_x_mm=600.0, As_x_mm2=38958.33, As_y_mm2=38958.33)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NEEDS_ENGINEER]
    assert any(m.startswith("G-2 (21.2.2)") and "eps_t_y_ratio" in m for m in payload.traces[0].messages)
    found = steps(payload)
    assert found["c_x_mm"] == pytest.approx(215.384597, abs=_MM)
    assert found["eps_t_x_ratio"] == pytest.approx(0.005357, abs=_RATIO)
    assert found["phiMn_x_kNm"] == pytest.approx(7804.911920, abs=_M_KNM)
    assert found["c_y_mm"] == pytest.approx(215.384597, abs=_MM)
    assert found["eps_t_y_ratio"] == pytest.approx(0.003964, abs=_RATIO)
    assert "phiMn_y_kNm" not in found


def test_rectangular_plan_uses_the_width_across_each_direction() -> None:
    """Asymmetric hand check: b = Ly with d_x and As_x for X, b = Lx with d_y and As_y for Y (clause spec §4).

    Common inputs except Lx = 2000, Ly = 3000, d_x = 500, d_y = 450 mm, As_x = 3000, As_y = 2000 mm2; hand values:
    q0 = 1700 / 6.0 = 283.333 kPa; Mu_x = 3.0 * q0 * 0.8^2 / 2 = 272.0; Mu_y = 2.0 * q0 * 1.3^2 / 2 = 478.833 kN.m;
    a_x = 3000*420 / (0.85*28*3000) = 17.647059 mm = a_y; phiMn_x = 0.9 * 1260000 * (500 - a_x/2) * 1e-6 = 556.994118;
    phiMn_y = 0.9 * 840000 * (450 - a_y/2) * 1e-6 = 333.529412 kN.m; Y fails (ratio 1.435655) and governs.
    Strains (§4 step 6, dt = d_x for X and d_y for Y): c = 17.647059 / 0.85 = 20.761246 mm in both directions;
    eps_t_x = 0.003 * (500 - c) / c = 0.069250; eps_t_y = 0.003 * (450 - c) / c = 0.062025.
    """
    payload = run(Lx_mm=2000.0, Ly_mm=3000.0, d_x_mm=500.0, d_y_mm=450.0, As_x_mm2=3000.0, As_y_mm2=2000.0)
    found = steps(payload)
    assert found["c_x_mm"] == pytest.approx(20.761246, abs=_MM)
    assert found["c_y_mm"] == pytest.approx(20.761246, abs=_MM)
    assert found["eps_t_x_ratio"] == pytest.approx(0.069250, abs=_RATIO)
    assert found["eps_t_y_ratio"] == pytest.approx(0.062025, abs=_RATIO)
    x, y = payload.verdicts
    assert x.demand is not None
    assert x.capacity is not None
    assert y.demand is not None
    assert y.capacity is not None
    assert x.demand.value == pytest.approx(272.0, abs=_M_KNM)
    assert y.demand.value == pytest.approx(478.833333, abs=_M_KNM)
    assert x.capacity.value == pytest.approx(556.994118, abs=_M_KNM)
    assert y.capacity.value == pytest.approx(333.529412, abs=_M_KNM)
    assert y.ratio == pytest.approx(1.435655, abs=_RATIO)
    assert [x.status, y.status] == [VerdictStatus.PASS, VerdictStatus.FAIL]
    assert y.governing
    assert not x.governing
