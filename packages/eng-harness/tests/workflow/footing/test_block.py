"""Block `design_isolated_footing` scenarios (plan 0010 T8; spec 0010 AC17 to AC20).

Synthetic reaction and basis values; each scenario names its derivation from spec 0010 / golden plan-gross /
bearing full-contact bounds. No project value is used.
"""

from __future__ import annotations

import json
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

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "footing" / "scenarios"
_ENLARGE = json.loads((_SCENARIOS / "enlarge-until-pass.json").read_text(encoding="utf-8"))
_FAMILIES = ("bearing", "one_way_shear", "punching", "flexure", "min_steel", "development")


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


def _refuse_decide(stand: Stand, shown: InputRequest) -> Any:
    """Rules must answer; a decide screen means the single-family setup failed."""
    props = _props(shown)
    if any(isinstance(p, dict) and "enum" in p for p in props.values()):
        raise AssertionError("rule should have answered; engineer was asked")
    return _auto(stand, shown)


def _status_rows(stand: Stand) -> list[dict[str, Any]]:
    """Stored `harness.footing_status` payloads in journal order (one per completed check round)."""
    rows: list[dict[str, Any]] = []
    for event in stand.events():
        payload = event.payload
        if (
            isinstance(payload, ev.StepCompleted)
            and payload.calc is not None
            and payload.calc.id == "harness.footing_status"
            and payload.result is not None
        ):
            rows.append(cast(dict[str, Any], stand.store.payload(payload.result.ref)))
    return rows


def _footing_state(status_payload: dict[str, Any], footing_id: str = "F1") -> dict[str, Any]:
    row = next(r for r in cast(list[dict[str, Any]], status_payload["footings"]) if r["id"] == footing_id)
    return cast(dict[str, Any], row["state"])


def _reaction_from_scenario(row: dict[str, Any]) -> dict[str, Any]:
    return reaction_row(
        str(row["joint"]),
        str(row["case"]),
        fz=float(row["FZ_kN"]),
        my=float(row.get("MY_kNm", 0.0)),
        mx=float(row.get("MX_kNm", 0.0)),
    )


def test_enlarge_until_pass(tmp_stand_root: Path) -> None:
    """AC17: bearing fails at the initial plan (moments, full contact); rounds enlarge until every check passes.

    Derivation (spec 0010 4.4.2 / 4.6; BP S5): see `tests/data/footing/scenarios/enlarge-until-pass.json`.
    Service FZ=576 kN → plan 2000 mm; MY=50 kN.m → q_max≈221.5 > 200 (FAIL), q_min≥0 (full contact).
    Factored MY=0 and max_spacing_mm=100 so only bearing fails; enlarge_plan to 2200 mm passes every check.
    """
    basis = {
        path: (float(value), unit)
        for path, (value, unit) in cast(dict[str, list[Any]], _ENLARGE["basis_overrides"]).items()
    }
    stand = build_stand(
        tmp_stand_root / "enlarge",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(*(_reaction_from_scenario(r) for r in _ENLARGE["reactions"])),
        basis=basis,
    )
    outcome = stand.play(_refuse_decide)
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.output is not None
    out = cast(Any, outcome.output)
    expected = cast(dict[str, Any], _ENLARGE["expected"])
    row = _footing_row(stand, outcome)
    assert row["Lx_mm"] == row["Ly_mm"] == expected["Lx_mm"]
    assert any(c["id"] == "F1" and c["status"] == expected["closure_status"] for c in _closures(outcome))
    # Two completed rounds (fail at 2000 mm, pass at 2200 mm); one verdict-set ref per family per round.
    assert out.rounds == expected["rounds"]
    per_round = int(expected["verdict_sets_per_round"])
    assert len(out.verdict_sets) == per_round * out.rounds
    assert list(out.decisions) == ["F1:enlarge_plan:rule:footing_fix_strategy.bearing_only"]
    state0 = _footing_state(_status_rows(stand)[0])
    assert state0["bearing"] == "FAIL"
    for family in _FAMILIES:
        if family != "bearing":
            assert state0[family] == "PASS", family


def test_shear_deepens(tmp_stand_root: Path) -> None:
    """AC18: punching (and one-way) fail alone → rule `shear_only` picks `increase_depth`; depth grows.

    Concentric high factored FZ on a large plan (bearing passes); thin depth so punching governs.
    Dense bars (max_spacing_mm=100) so flexure and min_steel PASS — otherwise the rule does not match.
    Initial h = foundation.min_depth_mm = 400 mm from plan size.
    """
    stand = build_stand(
        tmp_stand_root / "shear",
        subjects=subjects_payload(subject(cx_mm=500.0, cy_mm=500.0)),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz=400.0),
            reaction_row("J1", "U1", fz=2500.0),
        ),
        basis={
            "foundation.min_depth_mm": (400.0, "mm"),
            "foundation.max_depth_mm": (1500.0, "mm"),
            "reinforcement.max_spacing_mm": (100.0, "mm"),
        },
    )
    outcome = stand.play(_refuse_decide)
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.output is not None
    state0 = _footing_state(_status_rows(stand)[0])
    assert state0["punching"] == "FAIL"
    assert state0["bearing"] == "PASS"
    assert state0["flexure"] == "PASS"
    assert state0["min_steel"] == "PASS"
    assert state0["development"] == "PASS"
    decisions = list(cast(Any, outcome.output).decisions)
    assert decisions
    assert all(d.startswith("F1:increase_depth:rule:footing_fix_strategy.shear_only") for d in decisions)
    assert _footing_row(stand, outcome)["h_mm"] > 400.0


def test_flexure_reduces_spacing(tmp_stand_root: Path) -> None:
    """AC18: min_steel fails alone (steel_only) → `reduce_bar_spacing`; spacing shrinks from max_spacing_mm.

    Deep footing (min_depth_mm=900) so shear PASS; sparse bars (350 mm) so min_steel FAIL; concentric loads so
    flexure from moments does not mix families (spec 0010 4.5 steel_only / Q5).
    """
    stand = build_stand(
        tmp_stand_root / "flexure",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz=500.0),
            reaction_row("J1", "U1", fz=800.0),
        ),
        basis={
            "foundation.min_depth_mm": (900.0, "mm"),
            "reinforcement.max_spacing_mm": (350.0, "mm"),
            "reinforcement.min_spacing_mm": (100.0, "mm"),
        },
    )
    outcome = stand.play(_refuse_decide)
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.output is not None
    state0 = _footing_state(_status_rows(stand)[0])
    assert state0["min_steel"] == "FAIL"
    assert state0["flexure"] == "PASS"
    assert state0["bearing"] == "PASS"
    assert state0["one_way_shear"] == "PASS"
    assert state0["punching"] == "PASS"
    assert state0["development"] == "PASS"
    decisions = list(cast(Any, outcome.output).decisions)
    assert decisions
    assert all(d.startswith("F1:reduce_bar_spacing:rule:footing_fix_strategy.steel_only") for d in decisions)
    row = _footing_row(stand, outcome)
    assert row["s_mm"] < 350.0 or row["s_x_mm"] < 350.0


def test_attempts_exhausted_closes_open_footings(tmp_stand_root: Path) -> None:
    """AC19: last attempt with footings still failing → NEEDS_ENGINEER (ATTEMPTS_EXHAUSTED)."""
    stand = build_stand(
        tmp_stand_root / "exhausted",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz=576.0, my=50.0),
            reaction_row("J1", "U1", fz=800.0, my=50.0),
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
    assert cast(Any, outcome.output).rounds == 1


def test_eccentric_reaction_needs_engineer(tmp_stand_root: Path) -> None:
    """AC19 / Q18: q_min < 0 at the plan of §4.4.2 → bearing NEEDS_ENGINEER with the gap; no decide, no enlarge.

    Derivation: at L=2000 mm, N≈736 kN, q_avg=184 kPa; MY=300 kN.m → M/S≈225 > 184 → q_min < 0 (BP G-1 /
    FULL_CONTACT). Factored MY=0 and denser max spacing so other families do not FAIL (status would then be
    failing, not needs_engineer — spec 0010 4.4.5). Closure.reason carries the pack gap/precondition id.
    """
    stand = build_stand(
        tmp_stand_root / "eccentric",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz=576.0, my=300.0),
            reaction_row("J1", "U1", fz=800.0, my=0.0),
        ),
        basis={"reinforcement.max_spacing_mm": (100.0, "mm")},
    )
    outcome = stand.play(_auto)
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.output is not None
    out = cast(Any, outcome.output)
    closed = _closures(outcome)
    gap_closed = [
        c
        for c in closed
        if c["id"] == "F1" and c["status"] == "NEEDS_ENGINEER" and c["reason"] in {"FULL_CONTACT", "G-1"}
    ]
    assert gap_closed, closed
    assert not any(s.kind == "decide_many" for s in stand.steps())
    assert _footing_row(stand, outcome)["Lx_mm"] == _footing_row(stand, outcome)["Ly_mm"] == 2000.0
    assert out.rounds == 1
    state0 = _footing_state(_status_rows(stand)[0])
    assert state0["bearing"] == "NEEDS_ENGINEER"
    for family in _FAMILIES:
        if family != "bearing":
            assert state0[family] == "PASS", family
    bearing = cast(dict[str, Any], stand.store.payload(out.verdict_sets[0].ref))
    messages = [m for t in cast(list[dict[str, Any]], bearing.get("traces", [])) for m in t.get("messages", [])]
    assert any("FULL_CONTACT" in m and "G-1" in m for m in messages)


def test_engineer_dimensions(tmp_stand_root: Path) -> None:
    """AC20 / Q17: ask_engineer asks one L, h, s; next size equals the engineer answer (2600 / 550 / 200)."""
    stand = build_stand(
        tmp_stand_root / "engineer",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz=576.0, my=50.0),
            reaction_row("J1", "U1", fz=800.0, my=50.0),
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
    row = _footing_row(stand, outcome)
    assert row["Lx_mm"] == row["Ly_mm"] == 2600.0
    assert row["h_mm"] == 550.0
    assert row["s_mm"] == 200.0
    assert row["source"] == "engineer"


def test_combine_closes(tmp_stand_root: Path) -> None:
    """AC20: combine_with_neighbor closes NEEDS_ENGINEER (COMBINE_REQUESTED)."""
    stand = build_stand(
        tmp_stand_root / "combine",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz=576.0, my=50.0),
            reaction_row("J1", "U1", fz=800.0, my=50.0),
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
            reaction_row("J1", "S1", fz=576.0, my=50.0),
            reaction_row("J1", "U1", fz=800.0, my=50.0),
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


def test_plan_size_needs_engineer_closes(tmp_stand_root: Path) -> None:
    """Plan-size P6: service FZ <= 0 → UPLIFT → block closes NEEDS_ENGINEER before any sizing round."""
    stand = build_stand(
        tmp_stand_root / "uplift",
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz=-10.0),
            reaction_row("J1", "U1", fz=100.0),
        ),
    )
    outcome = stand.play(_auto)
    closed = _closures(outcome)
    assert any(c["id"] == "F1" and c["status"] == "NEEDS_ENGINEER" and c["reason"] == "UPLIFT" for c in closed)
    assert cast(Any, outcome.output).rounds == 0
    assert not list(cast(Any, outcome.output).decisions)


def test_width_too_small_closes(tmp_stand_root: Path) -> None:
    """Layout L1: span <= 0 → WIDTH_TOO_SMALL (spec 0010 §4.4.3 / B-568); closed before checks.

    Derivation: q_net≈160 kPa; FZ=5 kN → A_req≈0.031 m² → plan stays at min 200 mm (increment 100 mm).
    cover=100 mm, db=16 mm → 2*cover+db=216 mm > 200 mm → span < 0 → WIDTH_TOO_SMALL.
    """
    stand = build_stand(
        tmp_stand_root / "width",
        subjects=subjects_payload(subject(cx_mm=100.0, cy_mm=100.0)),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz=5.0),
            reaction_row("J1", "U1", fz=8.0),
        ),
        basis={
            "durability.cover_footing_mm": (100.0, "mm"),
            "foundation.min_plan_dimension_mm": (200.0, "mm"),
            "foundation.plan_increment_mm": (100.0, "mm"),
        },
    )
    outcome = stand.play(_auto)
    closed = _closures(outcome)
    assert any(c["id"] == "F1" and c["status"] == "NEEDS_ENGINEER" and c["reason"] == "WIDTH_TOO_SMALL" for c in closed)
    assert cast(Any, outcome.output).rounds == 1
    assert not any(s.kind == "decide_many" for s in stand.steps())


def test_plan_closed_sibling_open_reaches_status(tmp_stand_root: Path) -> None:
    """Spec 0010 §4.6 steps 1–2.3 / P6: one footing closed at plan; sibling still reaches status.

    F1: service FZ <= 0 → plan UPLIFT → closed before rounds.
    F2: FZ=576 kN, MY=50 → plan 2000 mm, bearing FAIL under full contact (enlarge-until-pass loads);
    factored MY=0 and dense bars so only bearing fails and status runs for F2.
    """
    stand = build_stand(
        tmp_stand_root / "mix_plan_status",
        subjects=subjects_payload(
            subject("F1", "J1", "C1"),
            subject("F2", "J2", "C2"),
        ),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz=-10.0),
            reaction_row("J1", "U1", fz=100.0),
            reaction_row("J2", "S1", fz=576.0, my=50.0),
            reaction_row("J2", "U1", fz=800.0, my=0.0),
        ),
        basis={"reinforcement.max_spacing_mm": (100.0, "mm")},
    )
    outcome = stand.play(_refuse_decide)
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.output is not None
    closed = _closures(outcome)
    assert any(c["id"] == "F1" and c["status"] == "NEEDS_ENGINEER" and c["reason"] == "UPLIFT" for c in closed)
    assert any(s.kind == "calc" and s.name == "harness.footing_status" for s in stand.steps())
    assert any(c["id"] == "F2" for c in closed) or any(
        r["id"] == "F2" for r in _status_rows(stand)[0]["footings"]
    )


def test_width_closed_sibling_open_reaches_status(tmp_stand_root: Path) -> None:
    """Spec 0010 §4.6.2.1–2.3 / B-568: WIDTH_TOO_SMALL sibling closed; open footing still reaches status.

    F1: same WIDTH_TOO_SMALL derivation as test_width_too_small_closes (cover 100, min plan 200).
    F2: enlarge-until-pass bearing-fail loads with dense bars so status runs for F2 only.
    """
    stand = build_stand(
        tmp_stand_root / "mix_width_status",
        subjects=subjects_payload(
            subject("F1", "J1", "C1", cx_mm=100.0, cy_mm=100.0),
            subject("F2", "J2", "C2"),
        ),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz=5.0),
            reaction_row("J1", "U1", fz=8.0),
            reaction_row("J2", "S1", fz=576.0, my=50.0),
            reaction_row("J2", "U1", fz=800.0, my=0.0),
        ),
        basis={
            "durability.cover_footing_mm": (100.0, "mm"),
            "foundation.min_plan_dimension_mm": (200.0, "mm"),
            "foundation.plan_increment_mm": (100.0, "mm"),
            "reinforcement.max_spacing_mm": (100.0, "mm"),
        },
    )
    outcome = stand.play(_refuse_decide)
    assert outcome.status is RunStatus.COMPLETED
    closed = _closures(outcome)
    assert any(c["id"] == "F1" and c["reason"] == "WIDTH_TOO_SMALL" for c in closed)
    assert any(s.kind == "calc" and s.name == "harness.footing_status" for s in stand.steps())
    assert any(c["id"] == "F2" for c in closed) or any(
        r["id"] == "F2" for r in _status_rows(stand)[0]["footings"]
    )


def test_status_closed_sibling_still_resizes(tmp_stand_root: Path) -> None:
    """Spec 0010 §4.6.2.3–2.7: one footing closed at status NEEDS_ENGINEER; sibling still resizes.

    F1: eccentric service MY so bearing NEEDS_ENGINEER (FULL_CONTACT / G-1); closed at status, no decide.
    F2: bearing FAIL under full contact → rule enlarge_plan. Resize must still list an action for F1 (closed in dims).
    Factored MY=0 and dense bars so F1 stays needs_engineer and F2 is bearing-only.
    """
    stand = build_stand(
        tmp_stand_root / "mix_status_resize",
        subjects=subjects_payload(
            subject("F1", "J1", "C1"),
            subject("F2", "J2", "C2"),
        ),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz=576.0, my=300.0),
            reaction_row("J1", "U1", fz=800.0, my=0.0),
            reaction_row("J2", "S1", fz=576.0, my=50.0),
            reaction_row("J2", "U1", fz=800.0, my=0.0),
        ),
        basis={"reinforcement.max_spacing_mm": (100.0, "mm")},
    )
    outcome = stand.play(_refuse_decide)
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.output is not None
    closed = _closures(outcome)
    assert any(
        c["id"] == "F1" and c["status"] == "NEEDS_ENGINEER" and c["reason"] in {"FULL_CONTACT", "G-1", None}
        for c in closed
    )
    assert any("F2:enlarge_plan:" in d for d in cast(Any, outcome.output).decisions)


def test_combine_one_resize_sibling(tmp_stand_root: Path) -> None:
    """Spec 0010 §4.6.2.6–2.7: combine closes one footing; sibling still resizes (actions for every dims id).

    Mixed family failures so no draft rule matches (engineer decides). One decide_many screen: F1 combine, F2 enlarge.
    """
    from eng_harness.ports import InputAnswer

    stand = build_stand(
        tmp_stand_root / "mix_combine_resize",
        subjects=subjects_payload(
            subject("F1", "J1", "C1"),
            subject("F2", "J2", "C2"),
        ),
        reactions=reactions_payload(
            # Bearing + punching both FAIL → no single-family rule (engineer path).
            reaction_row("J1", "S1", fz=576.0, my=50.0),
            reaction_row("J1", "U1", fz=2500.0),
            reaction_row("J2", "S1", fz=576.0, my=50.0),
            reaction_row("J2", "U1", fz=2500.0),
        ),
        basis={
            "foundation.min_depth_mm": (400.0, "mm"),
            "attempts.footing_rounds": (2, None),
        },
    )

    def responder(stand: Stand, shown: InputRequest) -> Any:
        props = _props(shown)
        enums = {
            name: cast(list[str], prop.get("enum") or ())
            for name, prop in props.items()
            if isinstance(prop, dict) and "enum" in prop
        }
        if enums:
            names = sorted(enums)
            choices = {names[0]: "combine_with_neighbor", names[1]: "enlarge_plan"}
            for name in names[2:]:
                choices[name] = "enlarge_plan"
            return InputAnswer(
                request_id=shown.request_id,
                shown_sha256=shown.fields_schema_sha256,
                choices=choices,
                by="engineer:test",
            )
        return _auto(stand, shown)

    outcome = stand.play(responder)
    assert outcome.status is RunStatus.COMPLETED
    closed = _closures(outcome)
    assert any(c["id"] == "F1" and c["reason"] == "COMBINE_REQUESTED" for c in closed)
    assert any("F2:enlarge_plan:" in d for d in cast(Any, outcome.output).decisions)
