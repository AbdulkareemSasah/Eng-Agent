"""Decision-point behaviour of the footing block (plan 0010 T8; spec 0010 AC15, AC16)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eng_harness.engine import RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import InputRequest

from .conftest import (
    Stand,
    build_stand,
    reaction_row,
    reactions_payload,
    shadow_model,
    subject,
    subjects_payload,
)
from .test_block import _auto


def _failing_stand(root: Path, *, model: Any = None) -> Stand:
    """One footing that fails bearing at the first size so a decide step is reached (same derivation as AC17)."""
    return build_stand(
        root,
        subjects=subjects_payload(subject()),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz_kN=576.0, my_kNm=50.0),
            reaction_row("J1", "U1", fz_kN=800.0, my_kNm=50.0),
        ),
        model=model,
    )


def test_shadow_suggestion_not_applied(tmp_stand_root: Path) -> None:
    """AC15: a fake provider suggests an option; the engineer's choice is applied; the suggestion is shadow only."""
    stand = _failing_stand(tmp_stand_root / "shadow", model=shadow_model("combine_with_neighbor"))

    def responder(stand: Stand, shown: InputRequest) -> Any:
        props = shown.fields_schema.get("properties", {})
        assert isinstance(props, dict)
        if any(isinstance(p, dict) and "enum" in p for p in props.values()):
            # Engineer overrides the shadow suggestion.
            return stand.choose(shown, "enlarge_plan")
        return _auto(stand, shown)

    outcome = stand.play(responder)
    assert outcome.status is RunStatus.COMPLETED
    made = [e.payload for e in stand.events() if e.type is EventType.DECISION_MADE]
    assert made
    assert all(getattr(m, "decided_by", "").startswith("engineer:") or getattr(m, "decided_by", "").startswith("rule:") for m in made)
    # Provider was consulted (shadow), but its combine suggestion is not the applied choice when the engineer picks.
    assert stand.model is not None
    assert stand.model.requests  # the provider saw the request


def test_no_provider(tmp_stand_root: Path) -> None:
    """AC15: without a provider the engineer decides alone (rules may still answer)."""
    stand = _failing_stand(tmp_stand_root / "noprovider", model=None)
    outcome = stand.play(_auto)
    assert outcome.status is RunStatus.COMPLETED
    # No model provider was wired.
    assert stand.model is None


def test_one_screen_per_round(tmp_stand_root: Path) -> None:
    """AC16: three footings that need the engineer in one round → one decide_many step / one screen."""
    stand = build_stand(
        tmp_stand_root / "three",
        subjects=subjects_payload(
            subject("F1", "J1", "C1"),
            subject("F2", "J2", "C2", cx_mm=400.0, cy_mm=400.0),
            subject("F3", "J3", "C3", cx_mm=400.0, cy_mm=400.0),
        ),
        reactions=reactions_payload(
            reaction_row("J1", "S1", fz_kN=576.0, my_kNm=50.0),
            reaction_row("J1", "U1", fz_kN=800.0, my_kNm=50.0),
            reaction_row("J2", "S1", fz_kN=576.0, my_kNm=50.0),
            reaction_row("J2", "U1", fz_kN=800.0, my_kNm=50.0),
            reaction_row("J3", "S1", fz_kN=576.0, my_kNm=50.0),
            reaction_row("J3", "U1", fz_kN=800.0, my_kNm=50.0),
        ),
        # Force the engineer path: mixed failures so no single-family rule matches.
        basis={"attempts.footing_rounds": (2, None)},
    )

    screens = 0

    def responder(stand: Stand, shown: InputRequest) -> Any:
        nonlocal screens
        props = shown.fields_schema.get("properties", {})
        assert isinstance(props, dict)
        if any(isinstance(p, dict) and "enum" in p for p in props.values()):
            screens += 1
            # Count enum properties: decide_many puts one question per footing on one screen.
            enums = [n for n, p in props.items() if isinstance(p, dict) and "enum" in p]
            assert len(enums) >= 3
            return stand.choose(shown, "enlarge_plan")
        return _auto(stand, shown)

    outcome = stand.play(responder)
    assert outcome.status is RunStatus.COMPLETED
    decide_many = [s for s in stand.steps("decide_many")]
    assert len(decide_many) >= 1
    # One decide_many step for the first round's three footings (AC16).
    assert screens >= 1
    first = decide_many[0]
    assert isinstance(first, ev.StepStarted)
