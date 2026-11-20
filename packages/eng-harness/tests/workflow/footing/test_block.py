"""Block `design_isolated_footing` scenarios (plan 0010 T8; spec 0010 AC17 to AC20).

Synthetic reaction and basis values; each scenario names its derivation from spec 0010 / golden plan-gross /
bearing full-contact bounds. No project value is used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from eng_harness.engine import RunStatus
from eng_harness.journal import _events as ev
from eng_harness.ports import InputRequest

from .conftest import (
    Stand,
    build_stand,
    reaction_row,
    reactions_payload,
    subject,
    subjects_payload,
)


def _props(shown: InputRequest) -> dict[str, Any]:
    return cast(dict[str, Any], shown.fields_schema.get("properties", {}))


def _footing_row(stand: Stand, outcome: Any, footing_id: str = "F1") -> dict[str, Any]:
    out = cast(Any, outcome.output)
    design = cast(dict[str, Any], stand.store.payload(out.design.ref))
    return next(r for r in cast(list[dict[str, Any]], design["footings"]) if r["id"] == footing_id)


def _auto(stand: Stand, shown: InputRequest) -> Any:
    """Answer decide screens with the first enum option the rules would pick is already applied; else enlarge_plan.

    When the cascade still asks the engineer (no rule match), pick enlarge_plan so enlarge scenarios can proceed;
    dimension asks are answered with a larger square plan.
    """
    props = _props(shown)
    if any(isinstance(p, dict) and "enum" in p for p in props.values()):
        # Decision screen: prefer enlarge_plan when offered.
        enums = {
            name: cast(list[str], prop.get("enum") or ())
            for name, prop in props.items()
            if isinstance(prop, dict) and "enum" in prop
        }
        for _name, options in enums.items():
            if "enlarge_plan" in options:
                return stand.choose(shown, "enlarge_plan")
            if "increase_depth" in options:
                return stand.choose(shown, "increase_depth")
            if "reduce_bar_spacing" in options:
                return stand.choose(shown, "reduce_bar_spacing")
            return stand.choose(shown, options[0])
    # FootingDimensions ask: Quantity fields as {value, unit}.
    return stand.give(
        shown,
        {
            "L": {"value": 2400.0, "unit": "mm"},
            "h": {"value": 600.0, "unit": "mm"},
            "s": {"value": 200.0, "unit": "mm"},
        },
    )


def _closures(outcome: Any) -> list[dict[str, Any]]:
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.output is not None
    return [c.model_dump() for c in cast(Any, outcome.output).closures]


def test_enlarge_until_pass(tmp_stand_root: Path) -> None:
    """AC17: bearing fails at the initial plan (moments, full contact); rounds enlarge until every check passes.

    Derivation (spec 0010 4.4.2 / 4.6; BP S5): basis of golden plan-gross (q_allow=200 kPa, w=40 kPa).
    Service FZ=576 kN → plan size 2000 mm (A=4 m²). With MY=50 kN.m, q_avg=184 kPa, M/S≈37.5 kPa,
    q_max≈221.5 > 200 (FAIL) and q_min≈146.5 ≥ 0 (full contact). After enlarge_plan to 2200 mm, q_max < 200.
    """
    stand = build_stand(
        tmp_stand_root / "enlarge",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz_kN=576.0, my_kNm=50.0),
            reaction_row("J1", "U1", fz_kN=800.0, my_kNm=50.0),
        ),
    )
    outcome = stand.play(_auto)
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.output is not None
    # Final design plan is the smallest multiple that passes (spec AC17).
    row = _footing_row(stand, outcome)
    assert row["Lx_mm"] == row["Ly_mm"]
    assert row["Lx_mm"] >= 2000.0
    assert any(isinstance(e.payload, ev.StepCompleted) and e.payload.calc for e in stand.events())
    assert cast(Any, outcome.output).verdict_sets  # each round's verdict sets are retained


def test_shear_deepens(tmp_stand_root: Path) -> None:
    """AC18: punching fails alone → increase_depth; depth grows.

    Concentric high factored FZ on a large plan (bearing passes); thin depth so punching governs.
    Initial h = foundation.min_depth_mm = 500 mm from plan size.
    """
    stand = build_stand(
        tmp_stand_root / "shear",
        subjects=subjects_payload(subject(cx_mm=500.0, cy_mm=500.0)),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz_kN=400.0),
            reaction_row("J1", "U1", fz_kN=2500.0),
        ),
        basis={"foundation.min_depth_mm": (400.0, "mm"), "foundation.max_depth_mm": (1500.0, "mm")},
    )

    def responder(stand: Stand, shown: InputRequest) -> Any:
        props = _props(shown)
        if any(isinstance(p, dict) and "enum" in p for p in props.values()):
            return stand.choose(shown, "increase_depth")
        return _auto(stand, shown)

    outcome = stand.play(responder)
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.output is not None
    assert _footing_row(stand, outcome)["h_mm"] > 400.0


def test_flexure_reduces_spacing(tmp_stand_root: Path) -> None:
    """AC18: flexure fails alone → reduce_bar_spacing; spacing shrinks from max_spacing_mm."""
    stand = build_stand(
        tmp_stand_root / "flexure",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz_kN=400.0),
            reaction_row("J1", "U1", fz_kN=900.0, my_kNm=200.0),
        ),
        basis={"reinforcement.max_spacing_mm": (400.0, "mm"), "reinforcement.min_spacing_mm": (100.0, "mm")},
    )

    def responder(stand: Stand, shown: InputRequest) -> Any:
        props = _props(shown)
        if any(isinstance(p, dict) and "enum" in p for p in props.values()):
            return stand.choose(shown, "reduce_bar_spacing")
        return _auto(stand, shown)

    outcome = stand.play(responder)
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.output is not None
    row = _footing_row(stand, outcome)
    assert row["s_mm"] < 400.0 or row["s_x_mm"] < 400.0


def test_attempts_exhausted_closes_open_footings(tmp_stand_root: Path) -> None:
    """AC19: last attempt with footings still failing → NEEDS_ENGINEER (ATTEMPTS_EXHAUSTED)."""
    stand = build_stand(
        tmp_stand_root / "exhausted",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz_kN=576.0, my_kNm=50.0),
            reaction_row("J1", "U1", fz_kN=800.0, my_kNm=50.0),
        ),
        basis={
            "attempts.footing_rounds": (1, None),
            "foundation.max_plan_dimension_mm": (2000.0, "mm"),  # cannot enlarge past the failing size
        },
    )
    outcome = stand.play(_auto)
    assert outcome.status is RunStatus.COMPLETED
    closed = _closures(outcome)
    assert any(c["id"] == "F1" and c["reason"] == "ATTEMPTS_EXHAUSTED" for c in closed)


def test_eccentric_reaction_needs_engineer(tmp_stand_root: Path) -> None:
    """AC19 / Q18: q_min < 0 at the plan of §4.4.2 → bearing NEEDS_ENGINEER; no decide, no enlarge round.

    Derivation: at L=2000 mm, N≈736 kN, q_avg=184 kPa; MY=300 kN.m → M/S≈225 > 184 → q_min < 0 (BP G-1).
    Factored MY=0 and denser max spacing so other families do not FAIL (status would then be failing, not
    needs_engineer — spec 0010 4.4.5).
    """
    stand = build_stand(
        tmp_stand_root / "eccentric",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz_kN=576.0, my_kNm=300.0),
            reaction_row("J1", "U1", fz_kN=800.0, my_kNm=0.0),
        ),
        basis={"reinforcement.max_spacing_mm": (100.0, "mm")},
    )
    outcome = stand.play(_auto)
    assert outcome.status is RunStatus.COMPLETED
    closed = _closures(outcome)
    assert any(c["id"] == "F1" and c["status"] == "NEEDS_ENGINEER" for c in closed)
    # No decide_many step for this footing (closed as needs_engineer from status / bearing gap).
    assert not any(s.kind == "decide_many" for s in stand.steps())


def test_engineer_dimensions(tmp_stand_root: Path) -> None:
    """AC20 / Q17: ask_engineer asks one L, h, s; schedule source engineer; next round checks them."""
    stand = build_stand(
        tmp_stand_root / "engineer",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz_kN=576.0, my_kNm=50.0),
            reaction_row("J1", "U1", fz_kN=800.0, my_kNm=50.0),
        ),
    )

    def responder(stand: Stand, shown: InputRequest) -> Any:
        props = _props(shown)
        if any(isinstance(p, dict) and "enum" in p for p in props.values()):
            return stand.choose(shown, "ask_engineer")
        # One square plan size L with h and s (Q17); no Lx/Ly.
        assert "L" in props
        assert "Lx" not in props
        assert "Ly" not in props
        return stand.give(
            shown,
            {
                "L": {"value": 2600.0, "unit": "mm"},
                "h": {"value": 550.0, "unit": "mm"},
                "s": {"value": 200.0, "unit": "mm"},
            },
        )

    outcome = stand.play(responder)
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.output is not None
    assert any(s.kind == "ask" for s in stand.steps())


def test_combine_closes(tmp_stand_root: Path) -> None:
    """AC20: combine_with_neighbor closes NEEDS_ENGINEER (COMBINE_REQUESTED)."""
    stand = build_stand(
        tmp_stand_root / "combine",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz_kN=576.0, my_kNm=50.0),
            reaction_row("J1", "U1", fz_kN=800.0, my_kNm=50.0),
        ),
    )

    def responder(stand: Stand, shown: InputRequest) -> Any:
        props = _props(shown)
        if any(isinstance(p, dict) and "enum" in p for p in props.values()):
            return stand.choose(shown, "combine_with_neighbor")
        return _auto(stand, shown)

    outcome = stand.play(responder)
    closed = _closures(outcome)
    assert any(c["id"] == "F1" and c["reason"] == "COMBINE_REQUESTED" for c in closed)


def test_limit_closes(tmp_stand_root: Path) -> None:
    """AC20: a resize at its bound closes LIMIT_REACHED."""
    stand = build_stand(
        tmp_stand_root / "limit",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz_kN=576.0, my_kNm=50.0),
            reaction_row("J1", "U1", fz_kN=800.0, my_kNm=50.0),
        ),
        basis={
            "foundation.max_plan_dimension_mm": (2000.0, "mm"),
            "foundation.plan_increment_mm": (200.0, "mm"),
        },
    )

    def responder(stand: Stand, shown: InputRequest) -> Any:
        props = _props(shown)
        if any(isinstance(p, dict) and "enum" in p for p in props.values()):
            return stand.choose(shown, "enlarge_plan")
        return _auto(stand, shown)

    outcome = stand.play(responder)
    closed = _closures(outcome)
    assert any(c["id"] == "F1" and c["reason"] == "LIMIT_REACHED" for c in closed)
