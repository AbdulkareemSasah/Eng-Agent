"""Engineer turn and D-3 drift (plan 0007 T9a; spec 0007 AC19, AC42).

Synthetic model and basis values only. Drift ratios are synthetic host rows compared with the confirmed
basis field `limits.drift_ratio` (0.01 in the stand), never chosen here.
"""

from math import nextafter
from pathlib import Path
from typing import Any

from pydantic import JsonValue

from eng_harness.engine import PermissionMode, RunStatus
from eng_harness.ports import ApprovalRequest, InputRequest

from .conftest import ITEM_SECTION, Stand, build_stand, seed_results

THREE: dict[str, JsonValue] = {"change_set": {"items": [ITEM_SECTION]}}
LIMIT = 0.01  # the stand's confirmed limits.drift_ratio (synthetic)
STEEL = [{"frame": "F1", "ratio": 0.5, "ratio_type": "PMM", "location": 0.0, "combo": "C1"}]


def _drift(story: str, ratio: float, case: str = "C1") -> dict[str, Any]:
    """One synthetic story-drift row in the fake's host shape (`drift` is the ratio the adapter stores)."""
    return {
        "story": story,
        "case": case,
        "direction": "X",
        "drift": ratio,
        "label": "J1",
        "x": 0.0,
        "y": 0.0,
        "z": 3.0,
    }


def _seed_clean(stand: Stand, *, above: bool = False) -> None:
    """No analysis messages; drifts at the limit, or one row just above it (AC42)."""
    high = nextafter(LIMIT, float("inf")) if above else LIMIT
    seed_results(stand, drifts=[_drift("S1", 0.004), _drift("S2", high)], design={"steel": STEEL}, messages=[])


def _options(shown: InputRequest) -> set[str]:
    found: set[str] = set()
    for prop in shown.fields_schema.get("properties", {}).values():
        found.update(prop.get("enum") or ())
    return found


def _is_turn(shown: InputRequest) -> bool:
    return {"accept", "more_edits", "hand_edit"} <= _options(shown)


def _is_d3(shown: InputRequest) -> bool:
    options = _options(shown)
    return "stop_cycle" in options and "accept" not in options


def _responder(*, turn: str = "accept", d3: str = "continue") -> Any:
    """Approve the change set; answer D-3 and the engineer turn with the given options."""

    def respond(stand: Stand, shown: Any) -> Any:
        if isinstance(shown, ApprovalRequest):
            return stand.approve(shown)
        assert isinstance(shown, InputRequest)
        if shown.kind == "block":
            return stand.give(shown, THREE)
        if _is_turn(shown):
            return stand.choose(shown, turn)
        if _is_d3(shown):
            return stand.choose(shown, d3)
        return stand.choose(shown, "continue")

    return respond


def test_engineer_turn_branches(tmp_path: Path) -> None:
    """AC19: the engineer turn is a choice with accept / more_edits / hand_edit even in autonomous_logged;
    accept ends; more_edits asks for a change set next; hand_edit starts the next cycle with an empty set,
    no step 6 approval and a saved revision."""
    # accept in autonomous_logged
    accept = build_stand(tmp_path / "accept")
    _seed_clean(accept)
    outcome = accept.play(
        accept.flow(summarize=True),
        _responder(turn="accept"),
        mode=PermissionMode.AUTONOMOUS_LOGGED,
    )
    assert outcome.status is RunStatus.COMPLETED, outcome
    turns = [r for r in accept.inputs.presented if isinstance(r, InputRequest) and _is_turn(r)]
    assert turns, [r.kind for r in accept.inputs.presented]
    assert _options(turns[0]) == {"accept", "more_edits", "hand_edit"}
    assert outcome.output is not None
    assert [s.turn for s in outcome.output.summaries] == ["accept"]  # type: ignore[attr-defined]

    # more_edits: a second cycle opens a new change-set data request
    more = build_stand(tmp_path / "more")
    _seed_clean(more)
    asked: list[str] = []

    def more_respond(stand_i: Stand, shown: Any) -> Any:
        if isinstance(shown, ApprovalRequest):
            return stand_i.approve(shown)
        assert isinstance(shown, InputRequest)
        if shown.kind == "block":
            asked.append(shown.request_id)
            return stand_i.give(shown, THREE)
        if _is_turn(shown):
            return stand_i.choose(shown, "more_edits" if len(asked) == 1 else "accept")
        if _is_d3(shown):
            return stand_i.choose(shown, "continue")
        return stand_i.choose(shown, "accept")

    out_more = more.play(more.flow(cycles=2, summarize=True), more_respond)
    assert out_more.status is RunStatus.COMPLETED, out_more
    assert len(asked) == 2

    # hand_edit: next cycle has no change-set ask, no step 6 approval, a revision save
    hand = build_stand(tmp_path / "hand")
    _seed_clean(hand)
    data_asks: list[str] = []
    turn_n = {"n": 0}

    def hand_respond(stand_i: Stand, shown: Any) -> Any:
        if isinstance(shown, ApprovalRequest):
            return stand_i.approve(shown)
        assert isinstance(shown, InputRequest)
        if shown.kind == "block":
            data_asks.append(shown.request_id)
            return stand_i.give(shown, THREE)
        if _is_turn(shown):
            turn_n["n"] += 1
            return stand_i.choose(shown, "hand_edit" if turn_n["n"] == 1 else "accept")
        if _is_d3(shown):
            return stand_i.choose(shown, "continue")
        return stand_i.choose(shown, "accept")

    out_hand = hand.play(hand.flow(cycles=2, summarize=True), hand_respond)
    assert out_hand.status is RunStatus.COMPLETED, out_hand
    assert len(data_asks) == 1
    assert len([a for a in hand.approvals.presented if a.kind == "change_set"]) == 1
    saves = [s for s in hand.steps("tool") if s.name == "csi_save_model"]
    assert any((s.args or {}).get("as_new_revision") for s in saves)


def test_drift_at_d3(tmp_path: Path) -> None:
    """AC42: drifts whose highest ratio equals the limit give D-3 drift_status PASS (rule continues);
    a ratio just above the limit gives NEEDS_ENGINEER and D-3 reaches the engineer."""
    at = build_stand(tmp_path / "at")
    _seed_clean(at, above=False)
    at_out = at.play(at.flow(summarize=True), _responder(turn="accept"))
    assert at_out.status is RunStatus.COMPLETED, at_out
    (summary,) = at.results("harness.analysis_summary")
    assert summary["exceeding"] == []
    assert summary["status"] == "PASS"
    assert [r for r in at.inputs.presented if isinstance(r, InputRequest) and _is_d3(r)] == []

    above = build_stand(tmp_path / "above")
    _seed_clean(above, above=True)
    above_out = above.play(above.flow(summarize=True), _responder(turn="accept", d3="continue"))
    assert above_out.status is RunStatus.COMPLETED, above_out
    (summary2,) = above.results("harness.analysis_summary")
    assert summary2["exceeding"]
    assert summary2["status"] == "NEEDS_ENGINEER"
    assert [r for r in above.inputs.presented if isinstance(r, InputRequest) and _is_d3(r)], (
        "D-3 must reach the engineer when drift exceeds the limit"
    )
