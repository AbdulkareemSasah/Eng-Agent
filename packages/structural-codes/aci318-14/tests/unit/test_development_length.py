"""Preconditions, gaps, directions, constants and the psi_s assumption of the development length check.

Plan 0002 T8; DL-AC2, DL-AC3. Inputs are the clause spec §8 common inputs with the HC-1 bars; expected values are the
spec's §8 hand values with its tolerances (0.001 mm on lengths, 1e-6 on ratios).
"""

from typing import Any

import pytest
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14.checks.development_length import development_length_bottom_bars

CHECK_ID = "aci318_14.25_4_2_3.development_length_bottom_bars"
REGISTRY = Registry.of(
    [
        Pack(
            "aci318_14",
            "ACI 318-14",
            "2014",
            "0.1.0.dev0",
            checks=(development_length_bottom_bars,),
            approvals="approvals.yaml",
        )
    ]
)
FOOTING = Subject(kind=SubjectKind.FOOTING, id="F1")
COMMON: dict[str, Any] = {
    "Lx_mm": 2500.0,
    "Ly_mm": 2500.0,
    "cx_mm": 400.0,
    "cy_mm": 400.0,
    "db_x_mm": 16.0,
    "db_y_mm": 16.0,
    "s_x_mm": 200.0,
    "s_y_mm": 200.0,
    "cover_x_mm": 75.0,
    "cover_y_mm": 75.0,
    "end_cover_mm": 75.0,
    "fc_MPa": 28.0,
    "fy_MPa": 420.0,
    "concrete_class": "normalweight",
    "coating": "uncoated",
}
_MM = 0.001
_RATIO = 1e-6
_BODY = {"cb_x_mm", "cb_y_mm", "ld_x_mm", "ld_y_mm", "ld_eq_x_mm", "psi_s_ratio"}


def run(subject: Subject = FOOTING, **changes: Any) -> VerdictSet:
    """Evaluate the check on the common inputs with `changes` (trial mode)."""
    return evaluate(CHECK_ID, {**COMMON, **changes}, subject=subject, registry=REGISTRY).payload


@pytest.mark.parametrize(
    ("changes", "precondition", "gap"),
    [
        ({"end_cover_mm": 1050.0}, "ANCHORAGE_POSITIVE", None),
        ({"cy_mm": 2350.0}, "ANCHORAGE_POSITIVE", None),
        ({"coating": "epoxy"}, "UNCOATED", "G-2"),
        ({"coating": "zinc_epoxy_dual"}, "UNCOATED", "G-2"),
        ({"concrete_class": "lightweight"}, "NORMALWEIGHT", "G-1"),
        ({"concrete_class": "sand_lightweight"}, "NORMALWEIGHT", "G-1"),
        ({"fc_MPa": 16.0}, "FC_MIN", None),
        ({"fy_MPa": 600.0}, "FY_MAX", None),
    ],
)
def test_preconditions(changes: dict[str, Any], precondition: str, gap: str | None) -> None:
    """BD-1 to BD-3: one NEEDS_ENGINEER verdict naming the precondition (and its gap); the body does not run (DL-AC2).

    `cy = 2350 mm` leaves `la_y = 1250 - 1175 - 75 = 0` with `la_x > 0`: one direction alone fails the precondition.
    """
    payload = run(**changes)
    assert len(payload.verdicts) == 1
    assert payload.verdicts[0].status is VerdictStatus.NEEDS_ENGINEER
    trace = payload.traces[0]
    note = next(m for m in trace.messages if m.startswith(f"{precondition} ("))
    if gap is not None:
        assert gap in note
    assert not {s.name for s in trace.steps} & _BODY


def test_limits_pass() -> None:
    """At the limits (fc = 17 MPa, fy = 550 MPa, la just above zero) both normal verdicts are produced (DL-AC2)."""
    limits: tuple[dict[str, Any], ...] = ({"fc_MPa": 17.0}, {"fy_MPa": 550.0})
    for changes in limits:
        payload = run(**changes)
        assert [v.status for v in payload.verdicts] == [VerdictStatus.PASS, VerdictStatus.PASS], changes
    tight = run(end_cover_mm=1049.0)
    assert [v.status for v in tight.verdicts] == [VerdictStatus.FAIL, VerdictStatus.FAIL]
    steps = {s.name: s.value for s in tight.traces[0].steps}
    assert steps["la_x_mm"] == pytest.approx(1.0, abs=_MM)


def test_member_scope() -> None:
    """A subject that is not a footing is NOT_APPLICABLE (clause spec §2, member scope)."""
    payload = run(subject=Subject(kind=SubjectKind.FRAME, id="C1"))
    assert [v.status for v in payload.verdicts] == [VerdictStatus.NOT_APPLICABLE]


def test_psi_s_assumption() -> None:
    """The trace records psi_s from the constant psi_s_used and every verdict names plan §6 Q10 (DL-AC3).

    The step is named `psi_s_ratio`: the bare `psi_s` ends in the time suffix `_s`, which fixes the unit `s`
    (core AC10).
    """
    payload = run()
    trace = payload.traces[0]
    cited = {c.name: c.cited for c in trace.constants}
    assert cited["psi_s_used"].value == pytest.approx(1.0)
    assert cited["psi_s_used"].source.startswith("ACI 318-14 Table 25.4.2.4")
    steps = {s.name: s for s in trace.steps}
    assert steps["psi_s_ratio"].uses == ["psi_s_used"]
    assert steps["psi_s_ratio"].value == pytest.approx(1.0)
    assert len(payload.verdicts) == 2
    for verdict in payload.verdicts:
        assert any("Q10" in a for a in verdict.assumptions)


def test_constants_and_trace() -> None:
    """The §5 constants carry their citations and the §6 trace names appear X then Y (HC-1 values)."""
    trace = run().traces[0]
    cited = {c.name: c.cited for c in trace.constants}
    expected = {
        "c_ld": (1.1, "ACI 318-14 eq. 25.4.2.3a"),
        "conf_max": (2.5, "ACI 318-14 25.4.2.3"),
        "Ktr": (0.0, "ACI 318-14 25.4.2.3"),
        "ld_min": (300.0, "ACI 318-14 25.4.2.1"),
        "psi_t_bottom": (1.0, "ACI 318-14 Table 25.4.2.4"),
        "psi_e_uncoated": (1.0, "ACI 318-14 Table 25.4.2.4"),
        "psi_te_max": (1.7, "ACI 318-14 25.4.2.4"),
        "lambda_nw": (1.0, "ACI 318-14 19.2.4.2"),
        "sf_max": (8.3, "ACI 318-14"),
        "c_half": (2.0, "Geometry"),
    }
    for name, (value, source) in expected.items():
        assert cited[name].value == pytest.approx(value), name
        assert cited[name].source.startswith(source), name
    names = [s.name for s in trace.steps]
    order = [
        "la_x_mm",
        "la_y_mm",
        "sf",
        "psi_t",
        "psi_e",
        "psi_s_ratio",
        "cb_x_mm",
        "conf_x_ratio",
        "ld_eq_x_mm",
        "ld_x_mm",
    ]
    assert [n for n in names if n in order] == order
    assert {"cb_y_mm", "conf_y_ratio", "ld_eq_y_mm", "ld_y_mm"} <= set(names)
    steps = {s.name: s for s in trace.steps}
    assert steps["sf"].unit is None
    assert steps["conf_x_ratio"].unit == "1"
    assert steps["la_x_mm"].value == pytest.approx(975.0, abs=_MM)
    assert steps["cb_x_mm"].value == pytest.approx(83.0, abs=_MM)
    assert steps["conf_x_ratio"].value == pytest.approx(2.5, abs=_RATIO)
    assert steps["ld_x_mm"].value == pytest.approx(461.803865, abs=_MM)


def test_rectangular_plan_uses_each_direction_own_bars() -> None:
    """Asymmetric hand check: X uses Lx, cx and the _x bars; Y uses Ly, cy and the _y bars (clause spec §4).

    X: Lx = 3000, cx = 500, db = 25, cover = 40, s = 150: la = 1500 - 250 - 75 = 1175 mm, cb = min(52.5, 75) = 52.5 mm,
    conf = 2.1, ld = 420 / (1.1 * sqrt(28)) * 25 / 2.1 = 859.010166 mm, ratio 0.731072.
    Y: Ly = 2000, cy = 300, db = 16, cover = 80, s = 250: la = 1000 - 150 - 75 = 775 mm, cb = min(88, 125) = 88 mm,
    conf = 2.5 (limit), ld = 461.803865 mm, ratio 0.595876. A swapped direction input fails here.
    """
    changes: dict[str, Any] = {
        "Lx_mm": 3000.0,
        "Ly_mm": 2000.0,
        "cx_mm": 500.0,
        "cy_mm": 300.0,
        "db_x_mm": 25.0,
        "db_y_mm": 16.0,
        "s_x_mm": 150.0,
        "s_y_mm": 250.0,
        "cover_x_mm": 40.0,
        "cover_y_mm": 80.0,
    }
    payload = run(**changes)
    x, y = payload.verdicts
    assert x.demand is not None
    assert x.capacity is not None
    assert y.demand is not None
    assert y.capacity is not None
    assert x.demand.unit == x.capacity.unit == "mm"
    assert x.demand.value == pytest.approx(859.010166, abs=_MM)
    assert x.capacity.value == pytest.approx(1175.0, abs=_MM)
    assert y.demand.value == pytest.approx(461.803865, abs=_MM)
    assert y.capacity.value == pytest.approx(775.0, abs=_MM)
    assert x.ratio == pytest.approx(0.731072, abs=_RATIO)
    assert y.ratio == pytest.approx(0.595876, abs=_RATIO)
    assert x.governing
    assert not y.governing
    assert x.clause == y.clause == "25.4.2.3"
    assert [x.status, y.status] == [VerdictStatus.PASS, VerdictStatus.PASS]
