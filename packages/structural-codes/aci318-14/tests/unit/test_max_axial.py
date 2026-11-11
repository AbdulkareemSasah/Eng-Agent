"""Preconditions, scope and constants of the maximum axial strength check (plan 0004 T2; MA-AC2).

Inputs are the clause spec §8 common inputs; expected values are the spec's §4 results with its §8 tolerances
(0.001 kN on forces, 1e-6 on ratios).
"""

from typing import Any

import pytest
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
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
COMMON: dict[str, Any] = {
    "Pu_kN": 3000.0,
    "b_mm": 500.0,
    "h_mm": 500.0,
    "Ast_mm2": 4000.0,
    "fc_MPa": 28.0,
    "fy_MPa": 420.0,
    "transverse_kind": "tied",
    "k_factor": 1.0,
    "lu_mm": 3000.0,
}
_V_KN = 0.001
_RATIO = 1e-6
_BODY = {"Ag_mm2", "Po_kN", "Pn_max_kN", "phiPn_max_kN", "phi_ratio"}


def run(subject: Subject = FRAME, **changes: Any) -> VerdictSet:
    """Evaluate the check on the common inputs with `changes` (trial mode)."""
    return evaluate(CHECK_ID, {**COMMON, **changes}, subject=subject, registry=REGISTRY).payload


@pytest.mark.parametrize(
    ("changes", "precondition", "gap"),
    [
        ({"lu_mm": 3301.0}, "SHORT_COLUMN", "G-2"),
        ({"Pu_kN": -1.0}, "AXIAL_COMPRESSION", "G-1"),
        ({"Ast_mm2": 250000.0}, "STEEL_IN_SECTION", None),
        ({"fc_MPa": 16.0}, "FC_MIN", None),
        ({"fy_MPa": 600.0}, "FY_MAX", None),
    ],
)
def test_preconditions(changes: dict[str, Any], precondition: str, gap: str | None) -> None:
    """BD-1 to BD-3: one NEEDS_ENGINEER verdict naming the precondition (and gap where stated); the body does not run.

    At lu = 3300 mm, Pu = 0, and fy = 550 MPa the normal verdict is produced (MA-AC2).
    """
    payload = run(**changes)
    assert len(payload.verdicts) == 1
    assert payload.verdicts[0].status is VerdictStatus.NEEDS_ENGINEER
    trace = payload.traces[0]
    note = next(m for m in trace.messages if m.startswith(f"{precondition} ("))
    if gap is not None:
        assert gap in note
    steps = {s.name for s in trace.steps}
    assert not steps & _BODY
    at_limit = run(lu_mm=3300.0)
    assert at_limit.verdicts[0].status is VerdictStatus.PASS
    assert at_limit.verdicts[0].ratio == pytest.approx(0.765678, abs=_RATIO)
    zero_axial = run(Pu_kN=0.0)
    assert zero_axial.verdicts[0].status is VerdictStatus.PASS
    assert zero_axial.verdicts[0].ratio == pytest.approx(0.0, abs=_RATIO)
    at_fy = run(fy_MPa=550.0)
    assert at_fy.verdicts[0].status is VerdictStatus.PASS
