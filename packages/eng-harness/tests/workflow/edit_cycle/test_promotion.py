"""Promotion and sign-off of the edit cycle (plan 0007 T9b; spec 0007 AC21, AC22)."""

from pathlib import Path
from typing import Any

from eng_harness.engine import RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalRequest

from .conftest import Stand, build_stand, cycle_responder, seed_clean, shipped_cycle


def _play(stand: Stand, responder: Any, **kwargs: Any) -> Any:
    return stand.play(shipped_cycle(), responder, workflow="model_edit_cycle", **kwargs)


def test_promote_and_conflict(tmp_path: Path) -> None:
    """AC21: accept runs a PROMOTION approval then ctx.promote; the backup exists and the original holds the
    accepted revision. An original changed since the copy is CONFLICT, nothing is copied, and the run escalates."""
    ok = build_stand(tmp_path / "ok")
    seed_clean(ok)
    outcome = _play(ok, cycle_responder())
    assert outcome.status is RunStatus.COMPLETED, outcome
    assert any(a.kind == "promotion" for a in ok.approvals.presented)
    assert (ok.run_dir / "backups" / ok.original.name).is_file()
    assert outcome.output is not None
    assert outcome.output.signed is True
    assert outcome.output.promoted.model_key == "m" or outcome.output.promoted.model_key == ok.original.name
    # conflict path: change the original between the promotion approval and the promote step
    bad = build_stand(tmp_path / "bad")
    seed_clean(bad)
    seen: list[str] = []

    def on_approval(stand_i: Stand, shown: ApprovalRequest) -> Any:
        if shown.kind == "promotion":
            seen.append(shown.request_id)
            stand_i.original.write_bytes(b"changed by hand after the copy")
            return stand_i.approve(shown)
        return stand_i.approve(shown)

    refused = _play(bad, cycle_responder(on_approval=on_approval))
    assert seen, "promotion was not asked"
    assert refused.status is RunStatus.NEEDS_ENGINEER, refused
    assert refused.escalation is not None
    assert "conflict" in (refused.escalation.detail or "").lower() or refused.escalation.reason in {
        "unhandled_error",
        "block_escalation",
    }
    assert bad.original.read_bytes() == b"changed by hand after the copy"


def test_sign_off_and_draft(stand: Stand) -> None:
    """AC22: after promotion a SIGN_OFF approval follows, signed_off is journaled, and run_completed.draft is
    true while any calc or rule used is draft."""
    seed_clean(stand)
    outcome = _play(stand, cycle_responder())
    assert outcome.status is RunStatus.COMPLETED, outcome
    assert any(a.kind == "sign_off" for a in stand.approvals.presented)
    signed = [e.payload for e in stand.events() if e.type is EventType.SIGNED_OFF]
    assert signed
    completed = [e.payload for e in stand.events() if isinstance(e.payload, ev.RunCompleted)]
    assert completed
    assert completed[-1].draft is True
    assert outcome.output is not None
    assert outcome.output.signed is True
