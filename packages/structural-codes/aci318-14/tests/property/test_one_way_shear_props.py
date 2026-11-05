"""Property tests of the one-way shear check (plan 0002 T4; clause spec §8 property tests, OS-AC4).

Capacity is non-decreasing in `fc` and in `d`; demand is non-increasing in `d` and non-decreasing in `FZ` and `|MY|`;
swapping the X and Y data together swaps the two verdicts. Inputs stay where every precondition holds (normalweight,
fc >= 17 MPa, FZ > 0, full contact). Comparisons allow 1e-9 kN of floating-point rounding.
"""

from typing import Any

from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from hypothesis import given, settings
from hypothesis import strategies as st
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14.checks.one_way_shear import one_way_shear

CHECK_ID = "aci318_14.22_5_5_1.one_way_shear"
REGISTRY = Registry.of(
    [Pack("aci318_14", "ACI 318-14", "2014", "0.1.0.dev0", checks=(one_way_shear,), approvals="approvals.yaml")]
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
    """A rectangular footing in full contact under FZ and MY (|MY| <= 0.95*FZ*Lx/6 keeps q_min > 0 with margin)."""
    lx = draw(st.floats(1500.0, 4000.0))
    ly = draw(st.floats(1500.0, 4000.0))
    fz = draw(st.floats(200.0, 5000.0))
    my = draw(st.floats(0.0, 0.95)) * fz * lx / 6000.0
    return {
        "FX_kN": 0.0,
        "FY_kN": 0.0,
        "FZ_kN": fz,
        "MX_kNm": 0.0,
        "MY_kNm": my,
        "Lx_mm": lx,
        "Ly_mm": ly,
        "cx_mm": draw(st.floats(300.0, 800.0)),
        "cy_mm": draw(st.floats(300.0, 800.0)),
        "d_x_mm": draw(st.floats(200.0, 900.0)),
        "d_y_mm": draw(st.floats(200.0, 900.0)),
        "reaction_height_mm": 0.0,
        "fc_MPa": draw(st.floats(17.0, 100.0)),
        "concrete_class": "normalweight",
    }


@settings(derandomize=True, max_examples=30, deadline=None)
@given(base=footings(), more=st.floats(0.0, 1.0))
def test_monotone(base: dict[str, Any], more: float) -> None:
    """Each §8 monotone input raised alone moves capacity and demand as stated (OS-AC4)."""
    ref = _pairs(base)
    stronger = _pairs({**base, "fc_MPa": base["fc_MPa"] * (1.0 + more)})
    deeper = _pairs({**base, "d_x_mm": base["d_x_mm"] + 200.0 * more, "d_y_mm": base["d_y_mm"] + 200.0 * more})
    heavier = _pairs({**base, "FZ_kN": base["FZ_kN"] * (1.0 + more), "MY_kNm": base["MY_kNm"]})
    bent = _pairs({**base, "MY_kNm": base["MY_kNm"] * (1.0 - more)})
    for k in range(2):
        assert stronger[k][1] >= ref[k][1] - _ROUND
        assert stronger[k][0] == ref[k][0]
        assert deeper[k][1] >= ref[k][1] - _ROUND
        assert deeper[k][0] <= ref[k][0] + _ROUND
        assert heavier[k][0] >= ref[k][0] - _ROUND
        assert bent[k][0] <= ref[k][0] + _ROUND


@settings(derandomize=True, max_examples=20, deadline=None)
@given(base=footings())
def test_swap_symmetry(base: dict[str, Any]) -> None:
    """Swapping the X and Y data together swaps the two verdicts (clause spec §8)."""
    swapped = {
        **base,
        "Lx_mm": base["Ly_mm"],
        "Ly_mm": base["Lx_mm"],
        "cx_mm": base["cy_mm"],
        "cy_mm": base["cx_mm"],
        "d_x_mm": base["d_y_mm"],
        "d_y_mm": base["d_x_mm"],
        "MX_kNm": base["MY_kNm"],
        "MY_kNm": base["MX_kNm"],
    }
    x, y = _pairs(base)
    sx, sy = _pairs(swapped)
    for a, b in ((x, sy), (y, sx)):
        assert abs(a[0] - b[0]) <= _ROUND * max(1.0, abs(a[0]))
        assert abs(a[1] - b[1]) <= _ROUND * max(1.0, abs(a[1]))
