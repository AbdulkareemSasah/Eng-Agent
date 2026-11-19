"""The engineer edits the model during the cycle (plan 0007 T8; spec 0007 AC13, first clause).

The fake's model is changed through the control file between two calls, as the engineer would in the host program.
"""

from typing import Any

from eng_harness.engine import RunStatus
from eng_harness.ports import ApprovalRequest, InputRequest

from .conftest import ITEM_SECTION, LOADS, STOP, Stand


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
    first, second = stand.results("harness.model_diff")
    assert first["changes"] == []  # cycle 1 compares the read with itself
    edited = [c for c in second["changes"] if c["section"] == "model.load_set/1"]
    assert edited, second["changes"]  # the hand edit is in the new difference report
    assert [c["key"][:2] for c in edited] == [["frame_loads", "F1"]]
    checks = stand.results("harness.change_set_check")
    assert [c["status"] for c in checks] == ["PASS", "PASS"]  # the answer was kept and checked again on the new read
