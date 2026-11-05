"""Property tests of the flexure check (plan 0002 T6; clause spec §8 property tests, FL-AC4).

Capacity is non-decreasing in `As` (while tension-controlled), in `d` and in `fc`; demand is non-decreasing in `FZ`
and `|MY|` and independent of `As`, `fc` and `fy`. Inputs stay where every precondition holds and the section is
tension-controlled: reinforcement ratio 0.0018 to 0.004, at most doubled, with fy <= 550 MPa and fc >= 17 MPa keeps
c/d <= 0.008*550/(0.85*17*0.85) = 0.358 < 0.375. Comparisons allow 1e-9 kN.m of floating-point rounding.
"""

from typing import Any

from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from hypothesis import given, settings
from hypothesis import strategies as st
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
_ROUND = 1e-9


def _pairs(inputs: dict[str, Any]) -> list[tuple[float, float]]:
    """(demand, capacity) per verdict, X then Y; every verdict is a body verdict."""
    payload = evaluate(CHECK_ID, inputs, subject=FOOTING, registry=REGISTRY).payload
    out = []
    for v in payload.verdicts:
        assert v.status in (VerdictStatus.PASS, VerdictStatus.FAIL)
        assert v.demand is not None
        assert v.capacity is not None
        out.append((v.demand.value, v.capacity.value))
    return out


@st.composite
def footings(draw: st.DrawFn) -> dict[str, Any]:
    """A rectangular footing in full contact (|MY| <= 0.95*FZ*Lx/6) with a tension-controlled section."""
    lx = draw(st.floats(1500.0, 4000.0))
    ly = draw(st.floats(1500.0, 4000.0))
    fz = draw(st.floats(200.0, 5000.0))
    d_x = draw(st.floats(200.0, 900.0))
    d_y = draw(st.floats(200.0, 900.0))
    return {
        "FX_kN": 0.0,
        "FY_kN": 0.0,
        "FZ_kN": fz,
        "MX_kNm": 0.0,
        "MY_kNm": draw(st.floats(0.0, 0.95)) * fz * lx / 6000.0,
        "Lx_mm": lx,
        "Ly_mm": ly,
        "cx_mm": draw(st.floats(300.0, 800.0)),
        "cy_mm": draw(st.floats(300.0, 800.0)),
        "d_x_mm": d_x,
        "d_y_mm": d_y,
        "As_x_mm2": draw(st.floats(0.0018, 0.004)) * ly * d_x,
        "As_y_mm2": draw(st.floats(0.0018, 0.004)) * lx * d_y,
        "reaction_height_mm": 0.0,
        "fc_MPa": draw(st.floats(17.0, 100.0)),
        "fy_MPa": draw(st.floats(280.0, 550.0)),
    }


@settings(derandomize=True, max_examples=30, deadline=None)
@given(base=footings(), more=st.floats(0.0, 1.0))
def test_monotone(base: dict[str, Any], more: float) -> None:
    """Each §8 monotone input raised alone moves capacity and demand as stated (FL-AC4)."""
    ref = _pairs(base)
    grow = 1.0 + more
    steel = _pairs({**base, "As_x_mm2": base["As_x_mm2"] * grow, "As_y_mm2": base["As_y_mm2"] * grow})
    deeper = _pairs({**base, "d_x_mm": base["d_x_mm"] + 200.0 * more, "d_y_mm": base["d_y_mm"] + 200.0 * more})
    stronger = _pairs({**base, "fc_MPa": base["fc_MPa"] * grow})
    weaker_steel = _pairs({**base, "fy_MPa": base["fy_MPa"] / grow})
    heavier = _pairs({**base, "FZ_kN": base["FZ_kN"] * grow})
    bent = _pairs({**base, "MY_kNm": base["MY_kNm"] * (1.0 - more)})
    for k in range(2):
        for changed in (steel, deeper, stronger):
            assert changed[k][1] >= ref[k][1] - _ROUND
        for unchanged in (steel, stronger, weaker_steel):
            assert unchanged[k][0] == ref[k][0]
        assert heavier[k][0] >= ref[k][0] - _ROUND
        assert bent[k][0] <= ref[k][0] + _ROUND
