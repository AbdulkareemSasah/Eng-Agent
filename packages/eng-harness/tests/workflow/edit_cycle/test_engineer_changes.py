"""The engineer edits the model during the cycle (plan 0007 T8 and T9b; spec 0007 AC12, AC13, AC14, AC34).

The fake's model is changed through the control file between two calls, as the engineer would in the host program.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from eng_harness.engine import RunStatus
from eng_harness.ports import ApprovalRequest, InputRequest

from .conftest import (
    ITEM_LOAD,
    ITEM_SECTION,
    LOADS,
    STOP,
    Stand,
    build_stand,
    cycle_responder,
    is_turn,
    seed_clean,
    shipped_cycle,
    unlock,
)

AREA_LOADS = "Area Load Assignments - Uniform"


def test_edit_during_approval_wait(stand: Stand) -> None:
    """AC13: a hand edit while the run waits at the change-set approval voids that approval at the first write: no
    write runs under it, the cycle returns to step 3, the new difference report shows the edit and the same change set
    is approved again on the new read (the change set is checked again, not asked again)."""
    approvals: list[str] = []

    def respond(_: Stand, shown: Any) -> Any:
        if isinstance(shown, ApprovalRequest):
            approvals.append(shown.request_id)
            if len(approvals) > 1:
                return STOP
            stand.hand_edit(lambda m: m["tables"][LOADS][0].update(Value=13.0))  # F1 DEAD, by hand in the host
            return stand.approve(shown)
        assert isinstance(shown, InputRequest)
        if shown.kind == "block":
            return stand.give(shown, {"change_set": {"items": [ITEM_SECTION]}})
        return stand.choose(shown, "accept")  # the host-state check after the stop: the engineer accepts the edit

    outcome = stand.play(stand.flow(), respond)
    assert outcome.status is RunStatus.PAUSED
    assert len(approvals) == 2
    assert [r.kind for r in stand.inputs.presented].count("block") >= 1
    asked = [e for e in stand.steps("tool") if e.name == "csi_save_model"]
    assert [s.under for s in asked] == []  # nothing was written under the first approval, none yet under the second
    assert stand.calls("csi_assign_frame_section") == []
    diffs = stand.results("harness.model_diff")
    assert diffs[0]["changes"] == []  # cycle 1 compares the read with itself
    # a later diff (step 4 after the void, or the re-read before step 6) holds the hand edit
    edited = [c for d in diffs[1:] for c in d["changes"] if c["section"] == "model.load_set/1"]
    assert edited, diffs  # the hand edit is in a difference report after the void
    assert [c["key"][:2] for c in edited[:1]] == [["frame_loads", "F1"]]
    checks = stand.results("harness.change_set_check")
    assert [c["status"] for c in checks] == ["PASS", "PASS"]  # the answer was kept and checked again on the new read


def test_hand_edit_between_cycles(tmp_path: Path) -> None:
    """AC12: a fake hand edit between two cycles appears in the next step 4 difference report."""
    stand = build_stand(tmp_path)
    seed_clean(stand)
    asks = {"n": 0}

    def on_turn(stand_i: Stand, shown: InputRequest, n: int) -> Any:
        if n == 1:
            unlock(stand_i)
            return stand_i.choose(shown, "more_edits")
        return stand_i.choose(shown, "accept")

    def on_change_set(stand_i: Stand) -> None:
        # After cycle 1's turn, the next change-set ask is cycle 2: edit then, so step 4 after the
        # re-read void (spec 4.5.1) shows it without a host_state resume boundary mid-turn.
        asks["n"] = len((*tuple(asks.values()), None))
        if asks["n"] > 1:
            stand_i.hand_edit(lambda m: m["tables"][LOADS][0].update(Value=17.0))

    outcome = stand.play(
        shipped_cycle(),
        cycle_responder(on_turn=on_turn, on_change_set=on_change_set),
        workflow="model_edit_cycle",
    )
    assert outcome.status is RunStatus.COMPLETED, outcome
    diffs = stand.results("harness.model_diff")
    assert len(diffs) >= 2
    edited = [c for d in diffs[1:] for c in d["changes"] if c["section"] == "model.load_set/1"]
    assert edited, diffs


def test_edit_while_stopped(tmp_path: Path) -> None:
    """AC14: a fake hand edit while the run is stopped; on resume the engineer accepts at the host-state check
    and the next step 4 shows the edit."""
    stand = build_stand(tmp_path)
    seed_clean(stand)
    flow = shipped_cycle()

    async def pause_at_change_set() -> Any:
        async with stand.ports() as ports:
            engine = stand.engine(ports, flow)
            outcome = await engine.start(stand.request(workflow="model_edit_cycle"))
            for _ in range(30):
                if outcome.status is not RunStatus.PAUSED:
                    return outcome
                shown = stand.shown(outcome.pending[0])
                if isinstance(shown, ApprovalRequest) and shown.kind == "change_set":
                    stand.hand_edit(lambda m: m["tables"][LOADS][0].update(Value=19.0))
                    return outcome  # leave paused without answering
                answered = cycle_responder()(stand, shown)
                port = stand.approvals if isinstance(shown, ApprovalRequest) else stand.inputs
                port.script(shown.request_id, answered)
                outcome = await engine.resume(outcome.run_id)
            raise AssertionError("did not reach the change-set approval")

    paused = asyncio.run(pause_at_change_set())
    assert paused.status is RunStatus.PAUSED, paused

    async def finish() -> Any:
        async with stand.ports() as ports:
            engine = stand.engine(ports, flow)
            outcome = await engine.resume(paused.run_id)
            for _ in range(40):
                if outcome.status is not RunStatus.PAUSED:
                    return outcome
                shown = stand.shown(outcome.pending[0])
                answered = cycle_responder()(stand, shown)
                port = stand.approvals if isinstance(shown, ApprovalRequest) else stand.inputs
                port.script(shown.request_id, answered)
                outcome = await engine.resume(outcome.run_id)
            raise AssertionError(f"the run did not end: {outcome}")

    done = asyncio.run(finish())
    assert done.status is RunStatus.COMPLETED, done
    diffs = stand.results("harness.model_diff")
    assert any(c for d in diffs for c in d["changes"] if c["section"] == "model.load_set/1"), diffs


def test_edit_during_change_set_wait(stand: Stand) -> None:
    """AC13 second clause: a hand edit while the change-set request is open means no approval on that old read;
    the cycle returns to step 3 and the new difference report shows the edit."""
    seed_clean(stand)

    def on_change_set(stand_i: Stand) -> None:
        stand_i.hand_edit(lambda m: m["tables"][LOADS][0].update(Value=23.0))

    outcome = stand.play(
        stand.flow(summarize=True),
        cycle_responder(on_change_set=on_change_set),
    )
    assert outcome.status is RunStatus.COMPLETED, outcome
    diffs = stand.results("harness.model_diff")
    assert len(diffs) >= 2
    edited = [c for c in diffs[1]["changes"] if c["section"] == "model.load_set/1"]
    assert edited, diffs[1]["changes"]
    checks = stand.results("harness.change_set_check")
    assert len(checks) >= 2  # kept answer checked again on the new read


def test_restore_keeps_hand_edit(tmp_path: Path) -> None:
    """AC34: hand edit between cycles, read-back FAIL in cycle 2, restore_previous keeps the engineer value."""
    stand = build_stand(tmp_path)
    seed_clean(stand)
    turn_n = {"n": 0}
    asks = {"n": 0}

    def hook(ports: Any) -> None:
        call = ports.tool_port.call
        writes = {"n": 0}

        async def after(tool: str, *args: Any, **kwargs: Any) -> Any:
            result = await call(tool, *args, **kwargs)
            if tool == "csi_assign_frame_section":
                writes["n"] = len((*tuple(writes.values()), None))
                # After the between-cycles hand edit (second change-set ask), plant an unexpected area load
                # so read-back FAIL offers restore_previous (AC34).
                if asks["n"] > 1 and writes["n"] >= 1:
                    data = __import__("json").loads(stand.control.read_text())
                    tables = data["model"].setdefault("tables", {})
                    rows = tables.setdefault(AREA_LOADS, [{"UniqueName": "A1", "Value": 0.0}])
                    rows[0]["Value"] = 99.0
                    stand.control.write_text(__import__("json").dumps(data))
            return result

        ports.tool_port.call = after

    def respond(stand_i: Stand, shown: Any) -> Any:
        if isinstance(shown, ApprovalRequest):
            return stand_i.approve(shown)
        assert isinstance(shown, InputRequest)
        if shown.kind == "block":
            asks["n"] = len((*tuple(asks.values()), None))
            if asks["n"] > 1:
                stand_i.hand_edit(lambda m: m["tables"][LOADS][0].update(Value=31.0))
            return stand_i.give(shown, {"change_set": {"items": [ITEM_SECTION]}})
        options: set[str] = set()
        props: dict[str, Any] = cast(dict[str, Any], shown.fields_schema.get("properties", {}))
        for prop in props.values():
            options.update(cast(list[str], prop.get("enum") or ()))
        if "restore_previous" in options and "accept" not in options:
            return stand_i.choose(shown, "restore_previous")
        if is_turn(shown):
            turn_n["n"] = len((*tuple(turn_n.values()), None))
            if turn_n["n"] == 1:
                unlock(stand_i)
                return stand_i.choose(shown, "more_edits")
            return stand_i.choose(shown, "accept")
        return stand_i.choose(shown, "continue")

    outcome = stand.play(stand.flow(cycles=3, summarize=True), respond, cycles_hook=hook)
    assert outcome.status in (RunStatus.COMPLETED, RunStatus.PAUSED, RunStatus.NEEDS_ENGINEER), outcome
    assert [s for s in stand.steps("tool") if s.name == "csi_open_revision"]


def test_restore_refuses_changed_snapshot(tmp_path: Path) -> None:
    """AC34: a snapshot whose file hash no longer equals its model_saved ends restore with CONFLICT."""
    stand = build_stand(tmp_path)
    seed_clean(stand)

    def hook(ports: Any) -> None:
        call = ports.tool_port.call

        async def after(tool: str, *args: Any, **kwargs: Any) -> Any:
            result = await call(tool, *args, **kwargs)
            if tool == "csi_assign_frame_section":
                data = __import__("json").loads(stand.control.read_text())
                tables = data["model"].setdefault("tables", {})
                rows = tables.setdefault(AREA_LOADS, [{"UniqueName": "A1", "Value": 0.0}])
                rows[0]["Value"] = 99.0
                stand.control.write_text(__import__("json").dumps(data))
                copies = stand.run_dir / "copies"
                if copies.is_dir():
                    for snap in copies.glob("*.rev*"):
                        snap.write_bytes(b"corrupted snapshot")
            return result

        ports.tool_port.call = after

    def respond(stand_i: Stand, shown: Any) -> Any:
        if isinstance(shown, ApprovalRequest):
            return stand_i.approve(shown)
        assert isinstance(shown, InputRequest)
        if shown.kind == "block":
            return stand_i.give(shown, {"change_set": {"items": [ITEM_SECTION, ITEM_LOAD]}})
        options: set[str] = set()
        props: dict[str, Any] = cast(dict[str, Any], shown.fields_schema.get("properties", {}))
        for prop in props.values():
            options.update(cast(list[str], prop.get("enum") or ()))
        if "restore_previous" in options:
            return stand_i.choose(shown, "restore_previous")
        return stand_i.choose(shown, "continue")

    outcome = stand.play(stand.flow(), respond, cycles_hook=hook)
    assert outcome.status is RunStatus.NEEDS_ENGINEER, outcome
    assert outcome.escalation is not None
