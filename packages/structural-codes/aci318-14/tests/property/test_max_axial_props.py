"""Property tests of the maximum axial strength check (plan 0004 T2; clause spec §8 property tests, MA-AC4).

`phiPn_max` is strictly increasing in `fc`, in `Ast` (for `fy > alpha_1*fc`), and in `b` and `h`; spiral capacity
exceeds tied for the same section; demand is independent of the section. Inputs stay where every precondition holds.
Comparisons allow 1e-9 of relative floating-point rounding.
"""

from typing import Any

from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from hypothesis import given, settings
from hypothesis import strategies as st
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14.checks.max_axial import max_axial_strength

CHECK_ID = "aci318_14.22_4_2_1.max_axial_strength"
REGISTRY = Registry.of(
    [
        Pack(
            "aci318_14",
            "ACI 318-14",
            "2014",
            "0.1.0.dev0",
            checks=(max_axial_strength,),
            approvals="approvals.yaml",
        )
    ]
)
FRAME = Subject(kind=SubjectKind.FRAME, id="C1")
_ROUND = 1e-9
_ALPHA_FC = 0.85 * 28.0


def _demand_capacity(inputs: dict[str, Any]) -> tuple[float, float]:
    """Demand and capacity of the single body verdict."""
    payload = evaluate(CHECK_ID, inputs, subject=FRAME, registry=REGISTRY).payload
    v = payload.verdicts[0]
    assert v.status in (VerdictStatus.PASS, VerdictStatus.FAIL)
    assert v.demand is not None
    assert v.capacity is not None
    return v.demand.value, v.capacity.value


@st.composite
def columns(draw: st.DrawFn) -> dict[str, Any]:
    """A short rectangular column with asymmetric plan and reinforcement within every precondition."""
    b = draw(st.floats(350.0, 700.0))
    h = draw(st.floats(450.0, 900.0))
    ag = b * h
    ast = draw(st.floats(2000.0, ag * 0.075))
    fy = draw(st.floats(max(300.0, _ALPHA_FC + 1.0), 550.0))
    pu = draw(st.floats(0.0, 2500.0))
    return {
        "Pu_kN": pu,
        "b_mm": b,
        "h_mm": h,
        "Ast_mm2": ast,
        "fc_MPa": draw(st.floats(17.0, 55.0)),
        "fy_MPa": fy,
        "transverse_kind": "tied",
        "k_factor": 1.0,
        "lu_mm": 3000.0,
    }


def _ge(a: float, b: float) -> bool:
    """`a >= b` within the relative rounding allowance."""
    return a >= b - _ROUND * max(1.0, abs(b))


@settings(derandomize=True, max_examples=40, deadline=None)
@given(base=columns(), more=st.floats(0.0, 1.0))
def test_monotone(base: dict[str, Any], more: float) -> None:
    """Each §8 monotone input raised alone moves capacity and demand as stated (MA-AC4)."""
    ref_d, ref_c = _demand_capacity(base)
    _, stronger = _demand_capacity({**base, "fc_MPa": base["fc_MPa"] * (1.0 + more)})
    _, more_steel = _demand_capacity({**base, "Ast_mm2": base["Ast_mm2"] * (1.0 + more)})
    _, wider = _demand_capacity({**base, "b_mm": base["b_mm"] * (1.0 + more)})
    _, deeper = _demand_capacity({**base, "h_mm": base["h_mm"] * (1.0 + more)})
    _, spiral_c = _demand_capacity({**base, "transverse_kind": "spiral"})
    _, tied_c = _demand_capacity({**base, "transverse_kind": "tied"})
    assert _ge(stronger, ref_c)
    assert _demand_capacity({**base, "fc_MPa": base["fc_MPa"] * (1.0 + more)})[0] == ref_d
    assert _ge(more_steel, ref_c)
    assert _ge(wider, ref_c)
    assert _ge(deeper, ref_c)
    assert spiral_c > tied_c + _ROUND
    pu_hold = {**base, "b_mm": base["b_mm"] * (1.0 + more)}
    assert _demand_capacity(pu_hold)[0] == ref_d
