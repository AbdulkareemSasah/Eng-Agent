"""Shared footing statics FS S1 to S5 and the two exact integrals (plan 0002 T2; bearing spec §4.1, BP-AC5).

Expected values are the hand values of the clause specs' §8 (bearing HC-1 to HC-3 and BD-1, one-way shear HC-1, HC-2
and BD-1, flexure HC-1 and HC-2) and, for the S2 terms in `MX` and `FY`, the S2 equation applied by hand. Tolerances
are those of the specs' §8: 0.01 kPa on pressures, 0.001 kN on shears, 0.001 kN.m on moments; section properties
and lengths are exact up to float rounding.
"""

import math
from typing import Any

import pytest
from eng_contract.cited import Cited
from eng_contract.envelope import LiteralInput
from eng_contract.params import ValidatedInput
from eng_contract.verdicts import Subject, SubjectKind
from structural_codes.errors import CheckDefinitionError
from structural_codes.inputs import bounded
from structural_codes.trace import TraceRecorder

from aci318_14._footing import FootingLoads, ServiceFooting, face_moments, one_way_shears, statics

_POSITIVE = Cited(value=0, unit="mm", source="Geometry: test input, a length is positive")
_P_KPA = 0.01
_V_KN = 0.001
_M_KNM = 0.001
_EXACT = 1e-12

# Bearing spec §8 common inputs.
_SERVICE = {
    "FX_kN": 0.0,
    "FY_kN": 0.0,
    "FZ_kN": 1200.0,
    "MX_kNm": 0.0,
    "MY_kNm": 0.0,
    "Lx_mm": 2500.0,
    "Ly_mm": 2500.0,
    "reaction_height_mm": 0.0,
    "h_mm": 600.0,
    "soil_depth_mm": 1000.0,
    "gamma_c_kN_m3": 24.0,
    "gamma_s_kN_m3": 18.0,
    "surcharge_kPa": 0.0,
}


class _Strength(FootingLoads):
    """Strength-form inputs with the column and depth fields the integrals read (one-way and flexure specs §3)."""

    cx_mm: float = bounded(gt=_POSITIVE, unit="mm")
    cy_mm: float = bounded(gt=_POSITIVE, unit="mm")
    d_x_mm: float = bounded(gt=_POSITIVE, unit="mm")
    d_y_mm: float = bounded(gt=_POSITIVE, unit="mm")


# One-way shear and flexure specs §8 common inputs.
_FACTORED = {
    "FX_kN": 0.0,
    "FY_kN": 0.0,
    "FZ_kN": 1700.0,
    "MX_kNm": 0.0,
    "MY_kNm": 0.0,
    "Lx_mm": 2500.0,
    "Ly_mm": 2500.0,
    "reaction_height_mm": 0.0,
    "cx_mm": 400.0,
    "cy_mm": 400.0,
    "d_x_mm": 500.0,
    "d_y_mm": 500.0,
}


def recorder(model_cls: type[Any], **values: float) -> tuple[Any, TraceRecorder]:
    """Return the validated model and a recorder over it, every field given as a literal."""
    model = model_cls(**values)
    provenance = {name: LiteralInput(literal=value) for name, value in values.items()}
    t = TraceRecorder(
        ValidatedInput(model, provenance),
        calc_id="aci318_14.13_3_1_1.statics_test",
        calc_version="0.1.0.dev0",
        content_sha256="0" * 64,
        subject=Subject(kind=SubjectKind.FOOTING, id="F1"),
    )
    return model, t


def _steps(t: TraceRecorder) -> dict[str, float]:
    trace = t.to_trace(outputs=[], status=None)
    return {s.name: float(s.value) for s in trace.steps}


@pytest.mark.parametrize(
    ("case", "changes", "expected"),
    [
        (
            "HC-1",
            {},
            {"W_kN": 202.5, "N_kN": 1402.5, "Mbx_kNm": 0.0, "Mby_kNm": 0.0, "q_avg_kPa": 224.4, "q_max_kPa": 224.4},
        ),
        ("HC-2", {"MY_kNm": 150.0}, {"Mby_kNm": -150.0, "q_max_kPa": 282.0, "q_min_kPa": 166.8}),
        ("HC-3", {"FX_kN": 40.0, "reaction_height_mm": 600.0}, {"Mby_kNm": -24.0, "q_max_kPa": 233.616}),
        ("BD-1", {"FZ_kN": 200.0, "MY_kNm": 300.0}, {"N_kN": 402.5, "q_min_kPa": -50.8, "q_max_kPa": 179.6}),
        # S2 by hand: Mbx = -MX + e*FY = 30 + 0.5*10 = 35 kN.m; 35 / 2.6041667 m3 = 13.44 kPa.
        (
            "S2-X",
            {"MX_kNm": -30.0, "FY_kN": 10.0, "reaction_height_mm": 500.0},
            {"Mbx_kNm": 35.0, "Mby_kNm": 0.0, "q_max_kPa": 237.84, "q_min_kPa": 210.96},
        ),
    ],
)
def test_s1_to_s5(case: str, changes: dict[str, float], expected: dict[str, float]) -> None:
    """Each FS step equals its hand value on the bearing hand-check inputs (BP-AC5)."""
    model, t = recorder(ServiceFooting, **{**_SERVICE, **changes})
    statics(model, t)
    steps = _steps(t)
    assert steps["A_mm2"] == pytest.approx(6.25e6, rel=_EXACT)
    assert steps["Sx_mm3"] == pytest.approx(2500.0**3 / 6, rel=_EXACT)
    assert steps["Sy_mm3"] == pytest.approx(2500.0**3 / 6, rel=_EXACT)
    assert steps["Ix_mm4"] == pytest.approx(2500.0**4 / 12, rel=_EXACT)
    assert steps["Iy_mm4"] == pytest.approx(2500.0**4 / 12, rel=_EXACT)
    assert steps["W_kN"] == pytest.approx(202.5, abs=_V_KN)
    for name, value in expected.items():
        assert steps[name] == pytest.approx(value, abs=_P_KPA), (case, name)
    assert steps["q_max_kPa"] + steps["q_min_kPa"] == pytest.approx(2 * steps["q_avg_kPa"], abs=_P_KPA)


def test_statics_records_only_the_bearing_constants() -> None:
    """Statics record the constants of bearing spec §5 and nothing else (so BP-AC3 can hold)."""
    model, t = recorder(ServiceFooting, **_SERVICE)
    statics(model, t)
    trace = t.to_trace(outputs=[], status=None)
    assert {c.name: c.cited.value for c in trace.constants} == {"k_m": 0.001, "c_S": 6, "c_I": 12}
    sources = {s.name: s.source for s in trace.steps}
    assert sources["A_mm2"].startswith("FS S1")
    assert sources["Mby_kNm"].startswith("FS S2")
    assert sources["N_kN"].startswith("FS S3")
    assert sources["q_max_kPa"].startswith("FS S5")


def test_strength_form_uses_the_column_load_only() -> None:
    """S3 strength form: N = FZ, no weight step; q_avg is the net factored pressure q0 (one-way spec HC-1)."""
    model, t = recorder(_Strength, **_FACTORED)
    statics(model, t)
    steps = _steps(t)
    assert "W_kN" not in steps
    assert steps["N_kN"] == 1700.0
    assert steps["q_avg_kPa"] == pytest.approx(272.0, abs=_P_KPA)


def test_soil_weight_and_surcharge_enter_w() -> None:
    """S3 service form: W = A*(h*gamma_c + soil_depth*gamma_s) + A*surcharge (6.25 m2 * (14.4 + 18 + 10) kPa)."""
    model, t = recorder(ServiceFooting, **{**_SERVICE, "surcharge_kPa": 10.0})
    statics(model, t)
    assert _steps(t)["W_kN"] == pytest.approx(265.0, abs=_V_KN)


@pytest.mark.parametrize(
    ("changes", "lc", "xbar", "vu_x", "vu_y"),
    [
        ({}, 550.0, 975.0, 374.0, 374.0),  # one-way HC-1
        ({"MY_kNm": 200.0}, 550.0, 975.0, 456.368, 374.0),  # one-way HC-2
        ({"MX_kNm": 200.0}, 550.0, 975.0, 374.0, 456.368),  # HC-2 turned by 90 degrees: Y uses |Mbx| and Ix
        ({"d_x_mm": 1100.0, "d_y_mm": 1100.0}, -50.0, 1275.0, 0.0, 0.0),  # one-way BD-1, E-1
    ],
)
def test_one_way_shear_integral(changes: dict[str, float], lc: float, xbar: float, vu_x: float, vu_y: float) -> None:
    """The exact shear beyond the section at d (one-way spec §4 steps 2 and 3)."""
    model, t = recorder(_Strength, **{**_FACTORED, **changes})
    statics(model, t)
    assert one_way_shears(t) == pytest.approx((vu_x, vu_y), abs=_V_KN)
    steps = _steps(t)
    assert steps["Lc_x_mm"] == pytest.approx(lc, abs=_EXACT)
    assert steps["Lc_y_mm"] == pytest.approx(lc, abs=_EXACT)
    assert steps["xbar_x_mm"] == pytest.approx(xbar, abs=_EXACT)
    assert steps["Vu_x_kN"] == pytest.approx(vu_x, abs=_V_KN)
    assert steps["Vu_y_kN"] == pytest.approx(vu_y, abs=_V_KN)
    assert {c.name for c in t.to_trace(outputs=[], status=None).constants} == {"k_m", "c_S", "c_I", "c_half"}


@pytest.mark.parametrize(
    ("changes", "lp", "mu_x", "mu_y"),
    [
        ({}, 1050.0, 374.85, 374.85),  # flexure HC-1
        ({"MY_kNm": 200.0}, 1050.0, 451.0548, 374.85),  # flexure HC-2
        ({"MX_kNm": -200.0}, 1050.0, 374.85, 451.0548),  # HC-2 turned: Y uses |Mbx| and Ix
        ({"cx_mm": 3000.0, "cy_mm": 3000.0}, -250.0, 0.0, 0.0),  # no cantilever beyond the face: no moment
    ],
)
def test_face_moment_integral(changes: dict[str, float], lp: float, mu_x: float, mu_y: float) -> None:
    """The exact moment of the pressure beyond the column face about it (flexure spec §4 steps 2 and 3)."""
    model, t = recorder(_Strength, **{**_FACTORED, **changes})
    statics(model, t)
    assert face_moments(t) == pytest.approx((mu_x, mu_y), abs=_M_KNM)
    steps = _steps(t)
    assert steps["Lp_x_mm"] == pytest.approx(lp, abs=_EXACT)
    assert steps["Lp_y_mm"] == pytest.approx(lp, abs=_EXACT)
    assert steps["Mu_x_kNm"] == pytest.approx(mu_x, abs=_M_KNM)
    names = {c.name for c in t.to_trace(outputs=[], status=None).constants}
    assert names == {"k_m", "c_S", "c_I", "c_half", "c_third"}


def test_integrals_need_the_statics_first() -> None:
    """An integral before the statics is a definition error, never a silent default."""
    _, t = recorder(_Strength, **_FACTORED)
    with pytest.raises(CheckDefinitionError):
        one_way_shears(t)


def test_signs_of_moments_do_not_change_pressures() -> None:
    """S4 and S5 take absolute values: flipping MX and MY with e = 0 leaves q_max and q_min unchanged."""
    results = []
    for sign in (1.0, -1.0):
        model, t = recorder(ServiceFooting, **{**_SERVICE, "MX_kNm": 40.0 * sign, "MY_kNm": 150.0 * sign})
        statics(model, t)
        steps = _steps(t)
        results.append((steps["q_max_kPa"], steps["q_min_kPa"]))
    assert math.isclose(results[0][0], results[1][0], abs_tol=_EXACT)
    assert math.isclose(results[0][1], results[1][1], abs_tol=_EXACT)
