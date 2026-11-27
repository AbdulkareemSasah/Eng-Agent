"""Approvals journaled per permission mode (plan 0007 T9b; spec 0007 AC23, section 4.7)."""

from pathlib import Path

import pytest

from eng_harness.engine import PermissionMode, RunStatus

from .conftest import build_stand, cycle_responder, seed_clean, shipped_cycle


@pytest.mark.parametrize(
    "mode",
    [PermissionMode.WORK_ON_COPY, PermissionMode.APPROVE_EACH_WRITE, PermissionMode.AUTONOMOUS_LOGGED],
)
def test_approvals_per_mode(tmp_path: Path, mode: PermissionMode) -> None:
    """AC23: the same scripted cycle in each permission mode journals approvals that match the table of §4.7:
    CHANGE_SET is a page in work_on_copy and approve_each_write and is resolved by the mode in autonomous_logged;
    PROMOTION and SIGN_OFF are always a page."""
    stand = build_stand(tmp_path / mode.value)
    seed_clean(stand)
    outcome = stand.play(shipped_cycle(), cycle_responder(), workflow="model_edit_cycle", mode=mode)
    assert outcome.status is RunStatus.COMPLETED, outcome
    kinds = [a.kind for a in stand.approvals.presented]
    assert "promotion" in kinds
    assert "sign_off" in kinds
    if mode is PermissionMode.AUTONOMOUS_LOGGED:
        # CHANGE_SET is resolved by the mode: the engineer is not shown a change_set page
        assert "change_set" not in kinds
    else:
        assert "change_set" in kinds
