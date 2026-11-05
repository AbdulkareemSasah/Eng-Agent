"""Property tests of the development length check (plan 0002 T8; clause spec §8 property tests, DL-AC4).

`ld` (the demand) is non-increasing in `fc`, in `cover` and in `s`, non-decreasing in `fy` and `db`, and never below
`ld_min = 300 mm` (25.4.2.1(b)); the capacity `la` does not depend on the bars. Swapping the X and Y data together
swaps the two verdicts. Inputs stay where every precondition holds (normalweight, uncoated, 17 <= fc, fy <= 550 MPa,
la > 0). Comparisons allow 1e-9 mm of floating-point rounding.
"""

from typing import Any

from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from hypothesis import given, settings
from hypothesis import strategies as st
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14.checks.development_length import development_length_bottom_bars

CHECK_ID = "aci318_14.25_4_2_3.development_length_bottom_bars"
_PACK = Pack(
    "aci318_14",
    "ACI 318-14",
    "2014",
    "0.1.0.dev0",
    checks=(development_length_bottom_bars,),
    approvals="approvals.yaml",
)
REGISTRY = Registry.of([_PACK])
FOOTING = Subject(kind=SubjectKind.FOOTING, id="F1")
_ROUND = 1e-9
_LD_MIN = 300.0  # ACI 318-14 25.4.2.1(b), clause spec §5


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
    """A footing whose bar ends pass the column face (L/2 - c/2 - end_cover >= 400 mm before any change)."""
    return {
        "Lx_mm": draw(st.floats(2000.0, 4000.0)),
        "Ly_mm": draw(st.floats(2000.0, 4000.0)),
        "cx_mm": draw(st.floats(300.0, 800.0)),
        "cy_mm": draw(st.floats(300.0, 800.0)),
        "db_x_mm": draw(st.floats(10.0, 36.0)),
        "db_y_mm": draw(st.floats(10.0, 36.0)),
        "s_x_mm": draw(st.floats(75.0, 400.0)),
        "s_y_mm": draw(st.floats(75.0, 400.0)),
        "cover_x_mm": draw(st.floats(25.0, 100.0)),
        "cover_y_mm": draw(st.floats(25.0, 100.0)),
        "end_cover_mm": draw(st.floats(25.0, 100.0)),
        "fc_MPa": draw(st.floats(17.0, 100.0)),
        "fy_MPa": draw(st.floats(280.0, 500.0)),
        "concrete_class": "normalweight",
        "coating": "uncoated",
    }


@settings(derandomize=True, max_examples=30, deadline=None)
@given(base=footings(), more=st.floats(0.0, 1.0))
def test_monotone(base: dict[str, Any], more: float) -> None:
    """Each §8 monotone input raised alone moves ld as stated; ld >= 300 mm always (DL-AC4)."""
    ref = _pairs(base)
    lower = {
        "fc": _pairs({**base, "fc_MPa": base["fc_MPa"] * (1.0 + more)}),
        "cover": _pairs(
            {**base, "cover_x_mm": base["cover_x_mm"] + 50.0 * more, "cover_y_mm": base["cover_y_mm"] + 50.0 * more}
        ),
        "s": _pairs({**base, "s_x_mm": base["s_x_mm"] * (1.0 + more), "s_y_mm": base["s_y_mm"] * (1.0 + more)}),
    }
    higher = {
        "fy": _pairs({**base, "fy_MPa": base["fy_MPa"] + 50.0 * more}),
        "db": _pairs({**base, "db_x_mm": base["db_x_mm"] * (1.0 + more), "db_y_mm": base["db_y_mm"] * (1.0 + more)}),
    }
    for k in range(2):
        assert ref[k][0] >= _LD_MIN - _ROUND
        for name, pairs in lower.items():
            assert pairs[k][0] <= ref[k][0] + _ROUND, name
            assert pairs[k][1] == ref[k][1], name
        for name, pairs in higher.items():
            assert pairs[k][0] >= ref[k][0] - _ROUND, name
            assert pairs[k][1] == ref[k][1], name


@settings(derandomize=True, max_examples=20, deadline=None)
@given(base=footings())
def test_swap_symmetry(base: dict[str, Any]) -> None:
    """Swapping the X and Y data together swaps the two verdicts (clause spec §4, direction Y)."""
    pairs: list[tuple[str, str]] = [("Lx_mm", "Ly_mm"), ("cx_mm", "cy_mm"), ("db_x_mm", "db_y_mm")]
    pairs += [("s_x_mm", "s_y_mm"), ("cover_x_mm", "cover_y_mm")]
    swapped = dict(base)
    for a, b in pairs:
        swapped[a], swapped[b] = base[b], base[a]
    x, y = _pairs(base)
    sx, sy = _pairs(swapped)
    for p, q in ((x, sy), (y, sx)):
        assert abs(p[0] - q[0]) <= _ROUND * max(1.0, abs(p[0]))
        assert abs(p[1] - q[1]) <= _ROUND * max(1.0, abs(p[1]))
