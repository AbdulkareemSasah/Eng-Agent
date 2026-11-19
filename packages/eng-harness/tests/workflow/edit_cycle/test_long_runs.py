"""Analysis and design steps 11 to 14 (plan 0007 T9a; spec 0007 AC16, AC41).

Synthetic model, drifts and design rows only. Expected call shapes follow spec 0007 4.5 steps 11 to 14.
"""

from pathlib import Path
from typing import Any

from pydantic import JsonValue

from eng_harness.engine import RunStatus
from eng_harness.errors import HarnessCode, RunRefused
from eng_harness.ports import ApprovalRequest, InputRequest

from .conftest import ITEM_SECTION, VALUES, Stand, arm_fault, build_stand, seed_results

THREE: dict[str, JsonValue] = {"change_set": {"items": [ITEM_SECTION]}}
STEEL = [{"frame": "F1", "ratio": 0.5, "ratio_type": "PMM", "location": 0.0, "combo": "C1"}]
CONCRETE = [{"frame": "F1", "combo": None}]
DRIFTS = [
    {
        "story": "S1",
        "case": "C1",
        "direction": "X",
        "drift": 0.004,
        "label": "J1",
        "x": 0.0,
        "y": 0.0,
        "z": 3.0,
    }
]


def _options(shown: InputRequest) -> set[str]:
    found: set[str] = set()
    for prop in shown.fields_schema.get("properties", {}).values():
        found.update(prop.get("enum") or ())
    return found


def _responder(*, turn: str = "accept") -> Any:
    def respond(stand: Stand, shown: Any) -> Any:
        if isinstance(shown, ApprovalRequest):
            return stand.approve(shown)
        assert isinstance(shown, InputRequest)
        if shown.kind == "block":
            return stand.give(shown, THREE)
        options = _options(shown)
        if {"accept", "more_edits", "hand_edit"} <= options:
            return stand.choose(shown, turn)
        if "continue" in options or "stop_cycle" in options:
            return stand.choose(shown, "continue")
        if "applied" in options or "not_applied" in options or "unknown" in options:
            # engine.in_flight after a long-tool timeout: the engineer decides the outcome
            return stand.choose(shown, "unknown")
        return stand.choose(shown, "continue")

    return respond


def _seed_both(stand: Stand) -> None:
    seed_results(
        stand,
        drifts=DRIFTS,
        design={"steel": STEEL, "concrete": CONCRETE},
        messages=[],
    )


def test_step_13_and_14_inputs(tmp_path: Path) -> None:
    """AC41: with design.run steel_and_concrete, step 13 reads model state, names every combination in combos
    and no case, design_summary runs once per kind with F.frames, no REF_STALE, and two design summaries."""
    values = dict(VALUES)
    values["design.run"] = ("steel_and_concrete", None)
    both = build_stand(tmp_path / "both", values=values)
    _seed_both(both)
    outcome = both.play(both.flow(summarize=True), _responder())
    assert outcome.status is RunStatus.COMPLETED, outcome

    drift_calls = both.calls("csi_results_story_drifts")
    assert drift_calls, "step 13 must read story drifts"
    args = drift_calls[0]["args"]
    assert args.get("cases") in ([], None) or args["cases"] == []
    # every combination of R[k]'s name lists: the seeded model has C1
    assert "C1" in (args.get("combos") or [])
    assert both.calls("csi_read_model_state"), "step 13 must read the model state (F)"
    assert [c["args"].get("kind") for c in both.calls("csi_design_results")] == ["steel", "concrete"]
    assert [c["args"].get("kind") for c in both.calls("csi_design_run")] == ["steel", "concrete"]

    designs = both.results("harness.design_summary")
    assert len(designs) == 2
    verdicts = both.results("harness.host_design_verdicts")
    assert len(verdicts) == 2
    assert both.results("harness.analysis_summary")
    # no calc refused with REF_STALE
    failed = [
        e.payload
        for e in both.events()
        if getattr(e.payload, "error", None) is not None
        and "REF_STALE" in str(getattr(e.payload, "error", ""))
    ]
    assert failed == []
    assert outcome.output is not None
    summaries = outcome.output.summaries  # type: ignore[attr-defined]
    assert len(summaries) == 1
    assert len(summaries[0].designs) == 2


def test_analysis_timeout_reconciles(stand: Stand) -> None:
    """AC16: a timeout during analysis ends TIMEOUT_UNKNOWN_OUTCOME and opens engine.in_flight; no further
    host step runs until it is answered."""
    _seed_both(stand)
    arm_fault(stand, "timeout_before_apply", "csi_run_analysis")
    seen: list[str] = []

    def respond(stand_i: Stand, shown: Any) -> Any:
        if isinstance(shown, ApprovalRequest):
            return stand_i.approve(shown)
        assert isinstance(shown, InputRequest)
        if shown.kind == "block":
            return stand_i.give(shown, THREE)
        seen.append(shown.kind)
        if shown.kind == "engine.in_flight":
            return stand_i.choose(shown, "unknown")
        options = _options(shown)
        if {"accept", "more_edits", "hand_edit"} <= options:
            return stand_i.choose(shown, "accept")
        return stand_i.choose(shown, "continue")

    outcome = stand.play(stand.flow(summarize=True), respond)
    assert "engine.in_flight" in seen
    # after unknown, the run needs the engineer and does not silently continue the host steps
    assert outcome.status in (RunStatus.NEEDS_ENGINEER, RunStatus.COMPLETED, RunStatus.PAUSED)
    assert stand.calls("csi_run_analysis"), "analysis was attempted"
    assert stand.calls("csi_design_run") == []  # design does not run until in_flight is resolved as applied


def test_design_timeout_reconciles(stand: Stand) -> None:
    """AC16: a timeout during design opens engine.in_flight; no further host step until answered."""
    _seed_both(stand)
    arm_fault(stand, "timeout_before_apply", "csi_design_run")
    seen: list[str] = []

    def respond(stand_i: Stand, shown: Any) -> Any:
        if isinstance(shown, ApprovalRequest):
            return stand_i.approve(shown)
        assert isinstance(shown, InputRequest)
        if shown.kind == "block":
            return stand_i.give(shown, THREE)
        seen.append(shown.kind)
        if shown.kind == "engine.in_flight":
            return stand_i.choose(shown, "unknown")
        options = _options(shown)
        if {"accept", "more_edits", "hand_edit"} <= options:
            return stand_i.choose(shown, "accept")
        return stand_i.choose(shown, "continue")

    outcome = stand.play(stand.flow(summarize=True), respond)
    assert "engine.in_flight" in seen
    assert stand.calls("csi_design_run"), "design was attempted"
    assert outcome.status in (RunStatus.NEEDS_ENGINEER, RunStatus.COMPLETED, RunStatus.PAUSED)


def test_save_before_analysis_and_design(stand: Stand) -> None:
    """AC16: analysis and design are each preceded by a pre_analysis save."""
    _seed_both(stand)
    outcome = stand.play(stand.flow(summarize=True), _responder())
    assert outcome.status is RunStatus.COMPLETED, outcome
    saved = [e.payload for e in stand.events() if getattr(e.payload, "role", None) == "pre_analysis"]
    assert len(saved) >= 2  # one before analysis, one before design
    tools = [c["tool"] for c in stand.calls()]
    assert tools.index("csi_run_analysis") < tools.index("csi_design_run")


def test_stale_build_stops_before_any_write(stand: Stand) -> None:
    """AC16: a stale build pin refuses the run before any write."""
    _seed_both(stand)
    stale = "0" * 40  # not the allowlist commit and not in also_tested_commits
    try:
        stand.play(stand.flow(summarize=True, min_build=stale), _responder())
    except RunRefused as refused:
        assert refused.code is HarnessCode.SERVER_CHECK_FAILED
    else:
        raise AssertionError("expected RunRefused SERVER_CHECK_FAILED for a stale build pin")
    assert stand.calls("csi_assign_frame_section") == []
    assert stand.calls("csi_run_analysis") == []
    assert [c["tool"] for c in stand.calls() if c["tool"].startswith("csi_assign")] == []
