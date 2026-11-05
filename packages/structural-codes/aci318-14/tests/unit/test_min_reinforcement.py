"""Rows, preconditions, scope and constants of the minimum flexural reinforcement check (plan 0002 T7; MR-AC2).

Inputs are the clause spec §8 common inputs; expected values are the spec's §4 results with its §8 tolerances
(1e-6 mm2 on areas, 1e-9 on ratios).
"""

import math
from typing import Any

import pytest
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
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
COMMON: dict[str, Any] = {
    "Lx_mm": 2500.0,
    "Ly_mm": 2500.0,
    "h_mm": 600.0,
    "As_x_mm2": 2800.0,
    "As_y_mm2": 2800.0,
    "fy_MPa": 420.0,
}
_AREA = 1e-6
_RATIO = 1e-9


def run(subject: Subject = FOOTING, **changes: Any) -> VerdictSet:
    """Evaluate the check on the common inputs with `changes` (trial mode)."""
    return evaluate(CHECK_ID, {**COMMON, **changes}, subject=subject, registry=REGISTRY).payload


def _steps(payload: VerdictSet) -> dict[str, float]:
    """Numeric steps of the single trace by name."""
    return {s.name: float(s.value) for s in payload.traces[0].steps}


def test_rows_and_preconditions() -> None:
    """BD-1: fy = 420 takes the second row, the next double below takes the first; BD-2: fy = 600 (MR-AC2)."""
    at_row = _steps(run(fy_MPa=420.0))
    assert at_row["rho_min_ratio"] == pytest.approx(0.0018, abs=_RATIO)
    below = _steps(run(fy_MPa=math.nextafter(420.0, 0.0)))
    assert below["rho_min_ratio"] == pytest.approx(0.0020, abs=_RATIO)
    payload = run(fy_MPa=600.0)
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NEEDS_ENGINEER]
    trace = payload.traces[0]
    assert any(m.startswith("FY_MAX (") for m in trace.messages)
    assert not {s.name for s in trace.steps} & {"Ag_x_mm2", "rho_min_ratio", "As_min_x_mm2", "As_min_y_mm2"}
    at_limit = run(fy_MPa=550.0)
    assert [v.status for v in at_limit.verdicts] == [VerdictStatus.PASS, VerdictStatus.PASS]


def test_member_scope() -> None:
    """A subject that is not a footing is NOT_APPLICABLE (clause spec §2, member scope)."""
    payload = run(subject=Subject(kind=SubjectKind.FRAME, id="C1"))
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NOT_APPLICABLE]


def test_two_directions_on_a_rectangular_footing() -> None:
    """X uses the width Ly and As_x, Y uses Lx and As_y (clause spec §4, direction rule).

    Hand values: Lx = 2000, Ly = 3000, h = 500, As_x = As_y = 2000, fy = 420; Ag_x = 3000 * 500 = 1.5e6 mm2,
    As_min_x = 0.0018 * 1.5e6 = 2700 mm2 (ratio 1.35, FAIL); Ag_y = 2000 * 500 = 1.0e6 mm2, As_min_y = 1800 mm2
    (ratio 0.9, PASS). A swapped width fails here.
    """
    payload = run(Lx_mm=2000.0, Ly_mm=3000.0, h_mm=500.0, As_x_mm2=2000.0, As_y_mm2=2000.0)
    x, y = payload.verdicts
    assert x.demand is not None
    assert x.capacity is not None
    assert y.demand is not None
    assert x.demand.value == pytest.approx(2700.0, abs=_AREA)
    assert x.demand.unit == "mm2"
    assert x.capacity.value == pytest.approx(2000.0, abs=_AREA)
    assert y.demand.value == pytest.approx(1800.0, abs=_AREA)
    assert x.ratio == pytest.approx(1.35, abs=_RATIO)
    assert y.ratio == pytest.approx(0.9, abs=_RATIO)
    assert [x.status, y.status] == [VerdictStatus.FAIL, VerdictStatus.PASS]
    assert x.governing
    assert x.clause == y.clause == "8.6.1.1"


def test_constants_and_trace() -> None:
    """The §5 constants are recorded with their citations, and the §6 trace names appear in order X, Y."""
    trace = run().traces[0]
    cited = {c.name: c.cited for c in trace.constants}
    for name, value in (("fy_row", 420.0), ("r1", 0.0020), ("r2", 0.0018), ("r3", 0.0014), ("fy_max", 550.0)):
        assert cited[name].value == pytest.approx(value)
    for name in ("fy_row", "r1", "r2", "r3"):
        assert cited[name].source.startswith("ACI 318-14 Table 8.6.1.1")
    assert cited["fy_row"].unit == "MPa"
    names = [s.name for s in trace.steps]
    order = ["rho_min_ratio", "Ag_x_mm2", "As_min_x_mm2", "Ag_y_mm2", "As_min_y_mm2", "ratio", "ratio_2"]
    assert [n for n in names if n in order] == order
