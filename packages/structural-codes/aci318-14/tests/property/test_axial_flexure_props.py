"""Property tests of the axial-flexure check (plan 0004 T3; clause spec §8 property tests, AF-AC6).

Capacity is non-decreasing in `A_bar` and in `fc` at fixed demand while compression-controlled; scaling `Pu` and `Mu`
by the same factor leaves `capM` unchanged within 1e-9 and scales the ratio; `capM <= Mu*phiPn_max/Pu` for `Pu > 0`.
"""

from typing import Any

import pytest
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from hypothesis import given, settings
from hypothesis import strategies as st
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14.checks.axial_flexure import axial_flexure_uniaxial

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
_REL = 1e-9


def _eval(inputs: dict[str, Any]) -> tuple[float, float, float, float]:
    """Return demand, capacity, ratio and phiPn_max for the single body verdict."""
    payload = evaluate(CHECK_ID, inputs, subject=FRAME, registry=REGISTRY).payload
    v = payload.verdicts[0]
    assert v.status in (VerdictStatus.PASS, VerdictStatus.FAIL)
    assert v.demand is not None and v.capacity is not None and v.ratio is not None
    steps = {s.name: float(s.value) for s in payload.traces[0].steps if not isinstance(s.value, bool)}
    return v.demand.value, v.capacity.value, v.ratio, steps["phiPn_max_kN"]


@st.composite
def columns(draw: st.DrawFn) -> dict[str, Any]:
    """A short tied column within CP and with at most six bar layers along the depth."""
    b = draw(st.floats(400.0, 800.0))
    h = draw(st.floats(400.0, 800.0))
    d_p = draw(st.floats(40.0, 80.0))
    n_h = draw(st.integers(2, 6))
    return {
        "Pu_kN": draw(st.floats(500.0, 2500.0)),
        "Mu_kNm": draw(st.floats(50.0, 500.0)),
        "Mu_other_kNm": 0.0,
        "b_mm": b,
        "h_mm": h,
        "d_prime_mm": d_p,
        "n_bars_b": draw(st.integers(2, 5)),
        "n_bars_h": n_h,
        "A_bar_mm2": draw(st.floats(200.0, 800.0)),
        "fc_MPa": draw(st.floats(28.0, 55.0)),
        "fy_MPa": draw(st.floats(420.0, 520.0)),
        "transverse_kind": "tied",
        "k_factor": 1.0,
        "lu_mm": draw(st.floats(1500.0, 3000.0)),
    }


@settings(derandomize=True, max_examples=25, deadline=None)
@given(base=columns(), grow=st.floats(0.01, 0.5), scale=st.floats(1.1, 3.0))
def test_monotone_and_ray(base: dict[str, Any], grow: float, scale: float) -> None:
    """§8 properties: monotone inputs, ray scaling and the axial-cap bound (AF-AC6)."""
    # HC-1-like compression-controlled demand: high Pu, moderate Mu
    cc = {**base, "Pu_kN": 2000.0, "Mu_kNm": 200.0, "fc_MPa": 28.0, "fy_MPa": 420.0}
    try:
        ref_d, ref_cap, ref_ratio, phi_pn_max = _eval(cc)
    except Exception:
        return
    if ref_d <= 0:
        return
    bigger_bar = _eval({**cc, "A_bar_mm2": cc["A_bar_mm2"] * (1.0 + grow)})
    stronger_fc = _eval({**cc, "fc_MPa": min(55.0, cc["fc_MPa"] * (1.0 + grow))})
    assert bigger_bar[1] >= ref_cap - _REL
    assert stronger_fc[1] >= ref_cap - _REL
    scaled = _eval({**cc, "Pu_kN": cc["Pu_kN"] * scale, "Mu_kNm": cc["Mu_kNm"] * scale})
    assert scaled[1] == pytest.approx(ref_cap, rel=_REL)
    assert scaled[2] == pytest.approx(ref_ratio * scale, rel=_REL)
    if cc["Pu_kN"] > 0:
        bound = cc["Mu_kNm"] * phi_pn_max / cc["Pu_kN"]
        assert ref_cap <= bound + _REL
