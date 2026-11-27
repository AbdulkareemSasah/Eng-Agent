"""Property tests of the longitudinal reinforcement limits check (plan 0004 T4; clause spec §8, RL-AC3).

The minimum verdict ratio is non-increasing in `Ast`; the maximum verdict ratio is non-decreasing in `Ast`; both
verdict ratios are unchanged (within 1e-12 relative) when `Ag` and `Ast` are scaled together. Inputs satisfy
`STEEL_IN_SECTION` (`Ast < Ag`).
"""

from typing import Any

from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from hypothesis import given, settings
from hypothesis import strategies as st
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14.checks.reinforcement_limits import longitudinal_reinforcement_limits

CHECK_ID = "aci318_14.10_6_1_1.longitudinal_reinforcement_limits"
REGISTRY = Registry.of(
    [
        Pack(
            "aci318_14",
            "ACI 318-14",
            "2014",
            "0.1.0.dev0",
            checks=(longitudinal_reinforcement_limits,),
            approvals="approvals.yaml",
        )
    ]
)
COLUMN = Subject(kind=SubjectKind.FRAME, id="C1")
_ROUND = 1e-12


def _ratios(inputs: dict[str, Any]) -> tuple[float, float]:
    """(minimum verdict ratio, maximum verdict ratio); every verdict is a body verdict."""
    payload = evaluate(CHECK_ID, inputs, subject=COLUMN, registry=REGISTRY).payload
    for v in payload.verdicts:
        assert v.status in (VerdictStatus.PASS, VerdictStatus.FAIL)
        assert v.ratio is not None
    r1 = next(float(s.value) for s in payload.traces[0].steps if s.name == "ratio")
    r2 = next(float(s.value) for s in payload.traces[0].steps if s.name == "ratio_2")
    return r1, r2


@st.composite
def columns(draw: st.DrawFn) -> dict[str, Any]:
    """A column section with longitudinal steel strictly inside the gross area."""
    ag = draw(st.floats(50000.0, 2.0e6))
    ast = draw(st.floats(100.0, ag * 0.5))
    return {"Ag_mm2": ag, "Ast_mm2": ast}


def _close(a: float, b: float) -> bool:
    """Relative equality within the §8 scaling tolerance."""
    scale = max(1.0, abs(a), abs(b))
    return abs(a - b) <= _ROUND * scale


@settings(derandomize=True, max_examples=40, deadline=None)
@given(base=columns(), more=st.floats(0.0, 1.0))
def test_monotone_and_scale(base: dict[str, Any], more: float) -> None:
    """§8 monotonicity in `Ast` and invariance under uniform scaling of `Ag` and `Ast` (RL-AC3)."""
    r_min, r_max = _ratios(base)
    ast_up = base["Ast_mm2"] * (1.0 + more * 0.5)
    if ast_up < base["Ag_mm2"]:
        r_min_up, r_max_up = _ratios({**base, "Ast_mm2": ast_up})
        assert r_min_up <= r_min + _ROUND
        assert r_max_up + _ROUND >= r_max
    factor = 1.0 + more
    r_min_s, r_max_s = _ratios({"Ag_mm2": base["Ag_mm2"] * factor, "Ast_mm2": base["Ast_mm2"] * factor})
    assert _close(r_min_s, r_min)
    assert _close(r_max_s, r_max)
