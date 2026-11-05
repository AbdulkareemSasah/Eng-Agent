"""Timeout mapping and the wedged host through the ToolPort (plan 0002 T9; spec 0002 4.5.6, AC21).

The host is the recording fake of `test_toolport`: nothing is started and no clock is read. A server `timeout` arrives
as an error reply; a client backstop arrives as the session's `ToolFailed`.
"""

from pathlib import Path
from typing import Any

from eng_contract.envelope import FailureEnvelope
from eng_contract.errors import ErrorCode, ErrorDetail
from eng_contract.ids import SeededIdSource
from eng_contract.store import ResultStore

from eng_harness.adapters._errors import HostHealth
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.errors import ToolFailed

from .test_toolport import Rig

TIMEOUT_REPLY = {"code": "timeout", "message": "csi_x timed out after 30 s", "data": None}
WALL = "csi_define_wall_section"


def _rig(run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any) -> tuple[Rig, HostHealth]:
    health = HostHealth()
    rig = Rig(run_dir, store, ids, clock, health=health, errors=CsiErrorMapper(ids))
    rig.caller.is_error = True
    rig.caller.body = TIMEOUT_REPLY
    return rig, health


def _failure(envelope: Any) -> ErrorDetail:
    assert isinstance(envelope, FailureEnvelope)
    return envelope.error


def test_timeout_mapping(run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any) -> None:
    # AC21: a read is TIMEOUT_NO_EFFECT; a write is TIMEOUT_UNKNOWN_OUTCOME with the op_id; the host is wedged
    rig, health = _rig(run_dir, store, ids, clock)
    assert health.wedged("csi") is None

    read = _failure(rig.call("csi_list_stories", {"model": "main"}, op_id="op-r"))
    assert (read.code, read.retryable, read.op_id) == (ErrorCode.TIMEOUT_NO_EFFECT, True, None)
    assert health.wedged("csi") == "op-r"
    assert health.epoch_bumps("csi") == 1

    health.reconciled("op-r")
    assert health.wedged("csi") is None
    write = _failure(rig.call(WALL, rig.wall(), op_id="op-w"))
    assert (write.code, write.retryable, write.op_id) == (ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, False, "op-w")
    assert health.wedged("csi") == "op-w"
    assert health.epoch_bumps("csi") == 2


def test_backstop_gets_the_op_id_and_wedges_without_a_second_epoch_bump(
    run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any
) -> None:
    # the session restarted the role and increased the epoch itself (spec 4.5.6); the adapter does not count it again
    rig, health = _rig(run_dir, store, ids, clock)
    lost = ErrorDetail(code=ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, message="csi/main lost its session", retryable=False)
    rig.caller.failure = ToolFailed(lost)
    failure = _failure(rig.call(WALL, rig.wall(), op_id="op-b"))
    assert (failure.code, failure.op_id) == (ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, "op-b")
    assert health.wedged("csi") == "op-b"
    assert health.epoch_bumps("csi") == 0


def test_backstop_on_a_read_is_no_effect(run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any) -> None:
    rig, health = _rig(run_dir, store, ids, clock)
    rig.caller.failure = ToolFailed(ErrorDetail(code=ErrorCode.TIMEOUT_NO_EFFECT, message="lost", retryable=True))
    assert _failure(rig.call("csi_list_stories", {"model": "main"})).code is ErrorCode.TIMEOUT_NO_EFFECT
    assert health.wedged("csi") is not None


def test_wedged_host_refuses_without_sending(run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any) -> None:
    rig, health = _rig(run_dir, store, ids, clock)
    rig.call(WALL, rig.wall(), op_id="op-w")
    sent = len(rig.caller.calls)
    ledgered = rig.ledger.path.read_text(encoding="utf-8")

    refused = _failure(rig.call("csi_list_stories", {"model": "main"}, op_id="op-next"))
    assert refused.code is ErrorCode.HOST_WEDGED
    assert refused.retryable is True
    assert "op-w" in refused.message
    assert len(rig.caller.calls) == sent  # nothing was sent
    assert rig.ledger.path.read_text(encoding="utf-8") == ledgered  # and nothing ledgered

    health.reconciled("op-w")
    rig.caller.is_error = False
    rig.caller.body = {"stories": ["S1"], "truncated": False}
    assert not isinstance(rig.call("csi_list_stories", {"model": "main"}), FailureEnvelope)


def test_error_reply_is_mapped_and_does_not_wedge(
    run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any
) -> None:
    rig, health = _rig(run_dir, store, ids, clock)
    rig.caller.body = {"code": "model_locked", "message": "locked", "data": None}
    assert _failure(rig.call(WALL, rig.wall())).code is ErrorCode.HOST_LOCKED
    assert health.wedged("csi") is None
    rig.caller.body = "plain text, not a JSON object"
    unexpected = _failure(rig.call(WALL, rig.wall()))
    assert unexpected.code is ErrorCode.INTERNAL
    assert unexpected.incident_id
