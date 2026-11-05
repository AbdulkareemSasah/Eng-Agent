"""Property tests of the minimum flexural reinforcement check (plan 0002 T7; clause spec §8 property tests, MR-AC3).

`As_min` is non-decreasing in `h` and in the width across each direction; `rho_min` is non-increasing in `fy` and
never below `r3 = 0.0014` for `fy >= 420`. Inputs stay where `FY_MAX` holds (fy <= 550 MPa). Comparisons allow 1e-9
of relative floating-point rounding.
"""

from typing import Any

from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from hypothesis import given, settings
from hypothesis import strategies as st
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14.checks.min_reinforcement import min_flexural_reinforcement

CHECK_ID = "aci318_14.8_6_1_1.min_flexural_reinforcement"
REGISTRY = Registry.of(
    [
        Pack(
            "aci318_14",
            "ACI 318-14",
            "2014",
            "0.1.0.dev0",
            checks=(min_flexural_reinforcement,),
            approvals="approvals.yaml",
        )
    ]
)
FOOTING = Subject(kind=SubjectKind.FOOTING, id="F1")
_ROUND = 1e-9


def _result(inputs: dict[str, Any]) -> tuple[list[float], float]:
    """(As_min per verdict X then Y, rho_min); every verdict is a body verdict."""
    payload = evaluate(CHECK_ID, inputs, subject=FOOTING, registry=REGISTRY).payload
    demands = []
    for v in payload.verdicts:
        assert v.status in (VerdictStatus.PASS, VerdictStatus.FAIL)
        assert v.demand is not None
        demands.append(v.demand.value)
    rho = next(float(s.value) for s in payload.traces[0].steps if s.name == "rho_min_ratio")
    return demands, rho


@st.composite
def footings(draw: st.DrawFn) -> dict[str, Any]:
    """A rectangular footing with bottom bars in both directions and fy within FY_MAX."""
    return {
        "Lx_mm": draw(st.floats(1000.0, 5000.0)),
        "Ly_mm": draw(st.floats(1000.0, 5000.0)),
        "h_mm": draw(st.floats(300.0, 1500.0)),
        "As_x_mm2": draw(st.floats(500.0, 20000.0)),
        "As_y_mm2": draw(st.floats(500.0, 20000.0)),
        "fy_MPa": draw(st.floats(200.0, 550.0)),
    }


def _le(a: float, b: float) -> bool:
    """`a <= b` within the relative rounding allowance."""
    return a <= b + _ROUND * max(1.0, abs(b))


@settings(derandomize=True, max_examples=40, deadline=None)
@given(base=footings(), more=st.floats(0.0, 1.0))
def test_monotone(base: dict[str, Any], more: float) -> None:
    """Each §8 monotone input raised alone moves `As_min` and `rho_min` as stated (MR-AC3)."""
    (ax, ay), rho = _result(base)
    (tx, ty), _ = _result({**base, "h_mm": base["h_mm"] * (1.0 + more)})
    (wx, _wy), _ = _result({**base, "Ly_mm": base["Ly_mm"] * (1.0 + more)})
    (_lx, ly), _ = _result({**base, "Lx_mm": base["Lx_mm"] * (1.0 + more)})
    _, rho_up = _result({**base, "fy_MPa": base["fy_MPa"] + (550.0 - base["fy_MPa"]) * more})
    assert _le(ax, tx)
    assert _le(ay, ty)
    assert _le(ax, wx)
    assert _le(ay, ly)
    assert _le(rho_up, rho)
    if base["fy_MPa"] >= 420.0:
        assert rho >= 0.0014 - _ROUND
