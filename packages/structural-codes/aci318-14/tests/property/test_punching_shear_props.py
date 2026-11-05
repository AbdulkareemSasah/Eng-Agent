"""Property tests of the punching shear check (plan 0002 T5; clause spec §8 property tests, PS-AC4).

Capacity is non-decreasing in `fc` and in `d`; demand is non-increasing in `d`; `vc <= vc_a` always; swapping `cx`
with `cy` together with `Lx` with `Ly` leaves the verdict unchanged. Inputs stay where every precondition holds
(normalweight, fc >= 17 MPa, FZ > 0, no base moment, perimeter on the footing). Comparisons allow 1e-9 MPa of
floating-point rounding.
"""

from typing import Any

from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from hypothesis import given, settings
from hypothesis import strategies as st
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14.checks.punching_shear import punching_shear

CHECK_ID = "aci318_14.22_6_5_2.punching_shear"
REGISTRY = Registry.of(
    [Pack("aci318_14", "ACI 318-14", "2014", "0.1.0.dev0", checks=(punching_shear,), approvals="approvals.yaml")]
)
FOOTING = Subject(kind=SubjectKind.FOOTING, id="F1")
_ROUND = 1e-9


def _result(inputs: dict[str, Any]) -> tuple[float, float, dict[str, float]]:
    """(demand, capacity, steps) of the single body verdict."""
    payload = evaluate(CHECK_ID, inputs, subject=FOOTING, registry=REGISTRY).payload
    (v,) = payload.verdicts
    assert v.status in (VerdictStatus.PASS, VerdictStatus.FAIL)
    assert v.demand is not None
    assert v.capacity is not None
    return v.demand.value, v.capacity.value, {s.name: s.value for s in payload.traces[0].steps}


@st.composite
def footings(draw: st.DrawFn) -> dict[str, Any]:
    """A footing under concentric load; `c + d + 200 <= 1600 < L`, so the perimeter stays inside when d grows."""
    return {
        "FX_kN": 0.0,
        "FY_kN": 0.0,
        "FZ_kN": draw(st.floats(200.0, 5000.0)),
        "MX_kNm": 0.0,
        "MY_kNm": 0.0,
        "Lx_mm": draw(st.floats(2000.0, 4000.0)),
        "Ly_mm": draw(st.floats(2000.0, 4000.0)),
        "cx_mm": draw(st.floats(300.0, 800.0)),
        "cy_mm": draw(st.floats(300.0, 800.0)),
        "d_mm": draw(st.floats(200.0, 600.0)),
        "reaction_height_mm": 0.0,
        "fc_MPa": draw(st.floats(17.0, 100.0)),
        "concrete_class": "normalweight",
    }


@settings(derandomize=True, max_examples=30, deadline=None)
@given(base=footings(), more=st.floats(0.0, 1.0))
def test_monotone_and_symmetric(base: dict[str, Any], more: float) -> None:
    """Monotone in `fc` and `d`, `vc <= vc_a`, and unchanged by the X/Y swap (PS-AC4)."""
    demand, capacity, steps = _result(base)
    s_demand, s_capacity, _ = _result({**base, "fc_MPa": base["fc_MPa"] * (1.0 + more)})
    d_demand, d_capacity, _ = _result({**base, "d_mm": base["d_mm"] + 200.0 * more})
    assert s_capacity >= capacity - _ROUND
    assert s_demand == demand
    assert d_capacity >= capacity - _ROUND
    assert d_demand <= demand + _ROUND
    assert steps["vc_MPa"] <= steps["vc_a_MPa"]
    swapped = {**base, "Lx_mm": base["Ly_mm"], "Ly_mm": base["Lx_mm"], "cx_mm": base["cy_mm"], "cy_mm": base["cx_mm"]}
    w_demand, w_capacity, _ = _result(swapped)
    assert abs(w_demand - demand) <= _ROUND
    assert abs(w_capacity - capacity) <= _ROUND
