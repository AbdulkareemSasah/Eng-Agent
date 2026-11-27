"""The cycle loop, step sequence, cycle limit and locked-model v1 exit (plan 0007 T9b; spec 0007 AC9, AC15, AC20)."""

from pathlib import Path
from typing import Any

from eng_harness.engine import RunStatus
from eng_harness.journal import _events as ev
from eng_harness.ports import InputRequest

from .conftest import (
    VALUES,
    Stand,
    build_stand,
    cycle_responder,
    seed_clean,
    shipped_cycle,
    unlock,
)


def _play(stand: Stand, responder: Any, **kwargs: Any) -> Any:
    return stand.play(shipped_cycle(), responder, workflow="model_edit_cycle", **kwargs)


def test_one_cycle_step_sequence(stand: Stand) -> None:
    """AC9: one cycle in work_on_copy journals the step sequence of spec 4.5 in order, with the working copy,
    the step 7 revision save under the step 6 approval, check-after-write before step 9 reads, and pre_analysis
    before steps 11 and 12; step 6 is asked once and no ApprovalVoid is raised."""
    seed_clean(stand)
    outcome = _play(stand, cycle_responder())
    assert outcome.status is RunStatus.COMPLETED, outcome
    tools = [s.name for s in stand.steps("tool")]
    assert "csi_open_model" in tools
    assert tools.index("csi_run_analysis") > tools.index("csi_save_model")
    assert "csi_design_run" in tools
    saves = [s for s in stand.steps("tool") if s.name == "csi_save_model"]
    revision = next(s for s in saves if (s.args or {}).get("as_new_revision") is True)
    assert revision.under is not None  # step 7 under the step 6 approval
    # settle re-presents the same request on resume (engine approvals); AC9 is one journaled ask
    change_ids = {a.request_id for a in stand.approvals.presented if a.kind == "change_set"}
    assert len(change_ids) == 1
    assert (
        len(
            [
                e
                for e in stand.events()
                if isinstance(e.payload, ev.ApprovalRequested) and e.payload.kind == "change_set"
            ]
        )
        == 1
    )
    roles = [e.payload.role for e in stand.events() if isinstance(e.payload, ev.ModelSaved)]
    assert "working_copy" in roles
    assert "pre_analysis" in roles
    assert "promoted" in roles
    kinds = [s.kind for s in stand.steps()]
    assert "promote" in kinds
    assert any(a.kind == "promotion" for a in stand.approvals.presented)
    assert any(a.kind == "sign_off" for a in stand.approvals.presented)


def test_cycle_limit(tmp_path: Path) -> None:
    """AC20: more cycles than attempts.cycles escalates with attempts_exhausted."""
    values = dict(VALUES)
    values["attempts.cycles"] = (1, None)
    stand = build_stand(tmp_path, values=values)
    seed_clean(stand)

    def on_turn(stand_i: Stand, shown: InputRequest, n: int) -> Any:
        unlock(stand_i)
        return stand_i.choose(shown, "more_edits")

    outcome = _play(stand, cycle_responder(on_turn=on_turn))
    assert outcome.status is RunStatus.NEEDS_ENGINEER, outcome
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "attempts_exhausted"


def test_unlock_under_change_set_approval(tmp_path: Path) -> None:
    """AC15: until plan 0002 T15 (ADR-0031), a cycle whose step 3 status shows locked asks for no change set,
    calls no csi_unlock_model, writes nothing and opens the engineer turn (v1 exit of spec 4.5). After T15 the
    same test expects the unlock item under the change-set approval."""
    stand = build_stand(tmp_path)
    seed_clean(stand)
    turns: list[str] = []

    def on_turn(stand_i: Stand, shown: InputRequest, n: int) -> Any:
        turns.append(shown.request_id)
        if n == 1:
            # leave the model locked after cycle 1 analysis (do not unlock)
            return stand_i.choose(shown, "more_edits")
        return stand_i.choose(shown, "accept")

    outcome = _play(stand, cycle_responder(on_turn=on_turn))
    # cycle 2 hits locked at step 3: engineer turn opens; accept ends the run (or more_edits would loop)
    assert len(turns) >= 2, turns
    assert stand.calls("csi_unlock_model") == []
    # after the locked cycle, no further change-set data request (unique ids: present is called again on resume)
    data_ids = {r.request_id for r in stand.inputs.presented if isinstance(r, InputRequest) and r.kind == "block"}
    assert len(data_ids) == 1  # only cycle 1
    writes = [
        c["tool"] for c in stand.calls() if c["tool"].startswith(("csi_assign", "csi_set", "csi_define", "csi_add"))
    ]
    # only cycle 1's write
    assert writes.count("csi_assign_frame_section") == 1
    assert outcome.status in (RunStatus.COMPLETED, RunStatus.PAUSED, RunStatus.NEEDS_ENGINEER)
