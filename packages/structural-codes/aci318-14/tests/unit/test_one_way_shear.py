"""Preconditions, gaps, directions and constants of the one-way shear check (plan 0002 T4; OS-AC2, OS-AC3).

Inputs are the clause spec §8 common inputs; expected values are the spec's §8 hand values with its tolerances
(0.001 kN on shears, 1e-6 on ratios).
"""

from typing import Any

import pytest
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14.checks.one_way_shear import one_way_shear

CHECK_ID = "aci318_14.22_5_5_1.one_way_shear"
REGISTRY = Registry.of(
    [Pack("aci318_14", "ACI 318-14", "2014", "0.1.0.dev0", checks=(one_way_shear,), approvals="approvals.yaml")]
)
FOOTING = Subject(kind=SubjectKind.FOOTING, id="F1")
COMMON: dict[str, Any] = {
    "FX_kN": 0.0,
    "FY_kN": 0.0,
    "FZ_kN": 1700.0,
    "MX_kNm": 0.0,
    "MY_kNm": 0.0,
    "Lx_mm": 2500.0,
    "Ly_mm": 2500.0,
    "cx_mm": 400.0,
    "cy_mm": 400.0,
    "d_x_mm": 500.0,
    "d_y_mm": 500.0,
    "reaction_height_mm": 0.0,
    "fc_MPa": 28.0,
    "concrete_class": "normalweight",
}
_V_KN = 0.001
_RATIO = 1e-6


def run(subject: Subject = FOOTING, **changes: Any) -> VerdictSet:
    """Evaluate the check on the common inputs with `changes` (trial mode)."""
    return evaluate(CHECK_ID, {**COMMON, **changes}, subject=subject, registry=REGISTRY).payload


@pytest.mark.parametrize(
    ("changes", "precondition", "gap"),
    [
        ({"fc_MPa": 16.0}, "FC_MIN", None),
        ({"concrete_class": "sand_lightweight"}, "NORMALWEIGHT", "G-1"),
        ({"concrete_class": "lightweight"}, "NORMALWEIGHT", "G-1"),
        ({"FZ_kN": 0.0}, "COMPRESSION", None),
        ({"FZ_kN": 100.0, "MY_kNm": 200.0}, "FULL_CONTACT", "G-2"),
    ],
)
def test_preconditions(changes: dict[str, Any], precondition: str, gap: str | None) -> None:
    """BD-2 to BD-4: one NEEDS_ENGINEER verdict naming the precondition (and gap); the body runs for neither direction.

    At fc = 17 MPa the two normal verdicts are produced (OS-AC2).
    """
    payload = run(**changes)
    assert len(payload.verdicts) == 1
    assert payload.verdicts[0].status is VerdictStatus.NEEDS_ENGINEER
    trace = payload.traces[0]
    note = next(m for m in trace.messages if m.startswith(f"{precondition} ("))
    if gap is not None:
        assert gap in note
    steps = {s.name for s in trace.steps}
    assert not steps & {"Vu_x_kN", "Vu_y_kN", "phiVc_x_kN", "phiVc_y_kN"}
    at_limit = run(fc_MPa=17.0)
    assert [v.status for v in at_limit.verdicts] == [VerdictStatus.PASS, VerdictStatus.PASS]


def test_member_scope() -> None:
    """A subject that is not a footing is NOT_APPLICABLE (clause spec §2, member scope)."""
    payload = run(subject=Subject(kind=SubjectKind.FRAME, id="C1"))
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NOT_APPLICABLE]


def test_two_directions_and_governing() -> None:
    """HC-2: two verdicts X then Y; X (ratio 0.541148) is governing over Y (0.443478) (OS-AC3)."""
    payload = run(MY_kNm=200.0)
    x, y = payload.verdicts
    assert x.demand is not None
    assert y.demand is not None
    assert x.capacity is not None
    assert x.demand.value == pytest.approx(456.368, abs=_V_KN)
    assert x.demand.unit == "kN"
    assert x.capacity.value == pytest.approx(843.333, abs=_V_KN)
    assert y.demand.value == pytest.approx(374.0, abs=_V_KN)
    assert x.ratio == pytest.approx(0.541148, abs=_RATIO)
    assert y.ratio == pytest.approx(0.443478, abs=_RATIO)
    assert x.governing
    assert not y.governing
    assert x.clause == y.clause == "22.5.5.1"
    assert [x.status, y.status] == [VerdictStatus.PASS, VerdictStatus.PASS]


def test_constants_and_trace() -> None:
    """The §5 constants are recorded with their citations, and the §6 trace names appear in order X, Y."""
    trace = run().traces[0]
    cited = {c.name: c.cited for c in trace.constants}
    assert cited["c_vc"].value == pytest.approx(0.17)
    assert cited["c_vc"].source.startswith("ACI 318-14 eq. 22.5.5.1")
    assert cited["phi_v"].value == pytest.approx(0.75)
    assert cited["lambda_nw"].value == pytest.approx(1.0)
    assert cited["sf_max"].value == pytest.approx(8.3)
    assert cited["k_kilo"].value == pytest.approx(0.001)
    assert cited["k_kilo"].source.startswith("SI prefix kilo")
    names = [s.name for s in trace.steps]
    order = ["q_avg_kPa", "Lc_x_mm", "xbar_x_mm", "Vu_x_kN", "Vu_y_kN", "sf", "Vc_x_kN", "phiVc_x_kN", "Vc_y_kN"]
    assert [n for n in names if n in order] == order
    assert "phiVc_y_kN" in names
    steps = {s.name: s for s in trace.steps}
    assert steps["sf"].value == pytest.approx(28.0**0.5, abs=1e-9)
    assert steps["sf"].unit is None
    assert steps["Vc_x_kN"].value == pytest.approx(843.333 / 0.75, abs=_V_KN)
