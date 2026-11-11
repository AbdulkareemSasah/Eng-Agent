"""Rows, preconditions, scope and constants of the longitudinal reinforcement limits check (plan 0004 T4; RL-AC2).

Inputs are the clause spec §8 HC-1 values; expected values are the spec's §4 results with its §8 tolerances
(1e-6 mm2 on areas, 1e-9 on ratios).
"""

from typing import Any

import pytest
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
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
COMMON: dict[str, Any] = {"Ag_mm2": 250000.0, "Ast_mm2": 4000.0}
_AREA = 1e-6
_RATIO = 1e-9


def run(subject: Subject = COLUMN, **changes: Any) -> VerdictSet:
    """Evaluate the check on the common inputs with `changes` (trial mode)."""
    return evaluate(CHECK_ID, {**COMMON, **changes}, subject=subject, registry=REGISTRY).payload


def _steps(payload: VerdictSet) -> dict[str, float]:
    """Numeric steps of the single trace by name."""
    return {s.name: float(s.value) for s in payload.traces[0].steps}


def test_limits_and_preconditions() -> None:
    """BD-1: Ast at and just below the minimum; BD-2: at and just above the maximum; BD-3: Ast = Ag (RL-AC2)."""
    # Ag = 250000 => As_min = 2500, As_max = 20000 (0.01·Ag, 0.08·Ag).
    at_min = run(Ast_mm2=2500.0)
    assert [v.status for v in at_min.verdicts] == [VerdictStatus.PASS, VerdictStatus.PASS]
    assert _steps(at_min)["ratio"] == pytest.approx(1.0, abs=_RATIO)
    below_min = run(Ast_mm2=2499.0)
    assert below_min.verdicts[0].status == VerdictStatus.FAIL
    assert _steps(below_min)["ratio"] == pytest.approx(2500.0 / 2499.0, abs=_RATIO)
    at_max = run(Ast_mm2=20000.0)
    assert [v.status for v in at_max.verdicts] == [VerdictStatus.PASS, VerdictStatus.PASS]
    assert _steps(at_max)["ratio_2"] == pytest.approx(1.0, abs=_RATIO)
    above_max = run(Ast_mm2=20001.0)
    assert above_max.verdicts[1].status == VerdictStatus.FAIL
    assert _steps(above_max)["ratio_2"] == pytest.approx(20001.0 / 20000.0, abs=_RATIO)
    equal_areas = run(Ag_mm2=250000.0, Ast_mm2=250000.0)
    assert [v.status for v in equal_areas.verdicts] == [VerdictStatus.NEEDS_ENGINEER]
    trace = equal_areas.traces[0]
    assert any(m.startswith("STEEL_IN_SECTION (") for m in trace.messages)
    assert not {s.name for s in trace.steps} & {"As_min_mm2", "As_max_mm2", "rho_ratio"}


def test_member_scope() -> None:
    """A subject that is not a frame is NOT_APPLICABLE (clause spec §2, member scope)."""
    payload = run(subject=Subject(kind=SubjectKind.FOOTING, id="F1"))
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NOT_APPLICABLE]


def test_gross_area_not_from_plan_dimensions() -> None:
    """Limits use `Ag_mm2` directly (400 mm x 625 mm = 250000 mm2), not an implicit b·h swap.

    Hand values: Ag = 400 * 625 = 250000, Ast = 5000; As_min = 2500, As_max = 20000; rho = 0.02; ratios 0.5 and 0.25.
    """
    payload = run(Ag_mm2=250000.0, Ast_mm2=5000.0)
    vmin, vmax = payload.verdicts
    assert vmin.demand is not None
    assert vmin.capacity is not None
    assert vmax.demand is not None
    assert vmax.capacity is not None
    assert vmin.demand.value == pytest.approx(2500.0, abs=_AREA)
    assert vmin.capacity.value == pytest.approx(5000.0, abs=_AREA)
    assert vmax.demand.value == pytest.approx(5000.0, abs=_AREA)
    assert vmax.capacity.value == pytest.approx(20000.0, abs=_AREA)
    assert vmin.ratio == pytest.approx(0.5, abs=_RATIO)
    assert vmax.ratio == pytest.approx(0.25, abs=_RATIO)
    assert [vmin.status, vmax.status] == [VerdictStatus.PASS, VerdictStatus.PASS]


def test_constants_and_trace() -> None:
    """The §5 constants are recorded with their citations, and the §6 trace names appear in order."""
    trace = run().traces[0]
    cited = {c.name: c.cited for c in trace.constants}
    for name, value in (("rho_min", 0.01), ("rho_max", 0.08)):
        assert cited[name].value == pytest.approx(value)
        assert cited[name].source.startswith("ACI 318-14 10.6.1.1")
    names = [s.name for s in trace.steps]
    order = ["As_min_mm2", "As_max_mm2", "rho_ratio", "ratio", "ratio_2"]
    assert [n for n in names if n in order] == order
