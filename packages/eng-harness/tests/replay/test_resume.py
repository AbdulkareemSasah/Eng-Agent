"""Resume: a completed or failed run, the recorded prefix, recorded failures and the run lock (plan 0001 T9b).

Covers spec 0001 AC35 (a completed run), the resume half of AC23 (one engine per run) and the resume order of 4.5.1
steps 1 to 3 and 9. A resume opens the run with a new engine over the same workspace, as a new process would. The
rig's call log shows which port calls it made; the fake host's ledger shows which tool calls reached the host.
"""

import asyncio
from pathlib import Path

import pytest
from eng_contract.errors import ContractError, ErrorCode, ErrorDetail
from fakes.ports import failure
from workflows.chain import ChainOutput, chain
from workflows.rig import Rig, hold_lock, make_rig, request, steps

from eng_harness.engine import RunStatus
from eng_harness.engine._steps import op_id
from eng_harness.errors import HarnessCode, JournalIntegrityError, RunLocked
from eng_harness.journal import EventType, JournalReader, JournalWriter, StepView, is_locked
from eng_harness.journal import _events as ev
from eng_harness.ports import HostInstance

T = EventType
AT = "2026-01-01T00:10:00.000Z"
CSI_ONE = HostInstance(instance_id="csi-1", pid=4242, process_started_at=AT, program="etabs")
CSI_TWO = HostInstance(instance_id="csi-2", pid=4243, process_started_at=AT, program="etabs")
OTHER = HostInstance(instance_id="other-1", pid=77, process_started_at=AT, program="safe")


def _append(rig: Rig, run_id: str, *events: tuple[EventType, dict[str, object]]) -> None:
    """Append events by hand with a writer of its own (no engine holds the run)."""
    writer = JournalWriter(rig.run_dir(run_id), rig.store, rig.clock, rig.ids)
    for kind, payload in events:
        writer.append(kind, payload)
    writer.close()


def _steps(rig: Rig, run_id: str) -> list[StepView]:
    reader = JournalReader(rig.run_dir(run_id))
    try:
        return reader.steps()
    finally:
        reader.close()


def _started(host_key: str, instance: HostInstance) -> tuple[EventType, dict[str, object]]:
    """The `host_started` event that journals `instance`, as the host invariants of plan task T13 will write it."""
    payload = {"host_key": host_key, **instance.model_dump(mode="json")}
    return T.HOST_STARTED, payload


def test_completed_run(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))  # the first run stops here
    workflow = chain(steps("read_a", "write_b", "read_c"))
    first = asyncio.run(rig.engine(workflow).start(request()))
    assert first.status is RunStatus.NEEDS_ENGINEER
    run_id = first.run_id
    _append(rig, run_id, _started("csi", CSI_ONE), _started("csi", CSI_TWO), _started("other", OTHER))
    completed = asyncio.run(rig.engine(workflow).resume(run_id))
    assert completed.status is RunStatus.COMPLETED
    _append(rig, run_id, (T.SIGNED_OFF, {"outputs": [], "approval_request_id": "apr_x", "by": "engineer:x"}))
    before, mark, ledger = rig.events(run_id), len(rig.log), len(rig.host.ledger)
    for _ in range(2):  # a resume of a terminal run repeats close_started
        again = asyncio.run(rig.engine(workflow).resume(run_id))
        assert again == completed  # the recorded output, equal to the live one
        assert isinstance(again.output, ChainOutput)
    assert rig.log[mark:] == ["host.close_started"] * 4  # the only calls: one per host key and resume, no tool, calc...
    assert rig.host.closed == [CSI_ONE, CSI_TWO, OTHER] * 2  # exactly the journaled instances
    assert len(rig.host.ledger) == ledger
    assert rig.events(run_id) == before  # nothing is journaled: no run_resumed either


def test_completed_run_without_instances_calls_nothing(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    workflow = chain(steps("read_a"))
    done = asyncio.run(rig.engine(workflow).start(request()))
    mark = len(rig.log)
    assert asyncio.run(rig.engine(workflow).resume(done.run_id)) == done
    assert rig.log[mark:] == []
    with pytest.raises(ContractError) as unknown:  # the output cannot be read back without its workflow
        asyncio.run(rig.engine().resume(done.run_id))
    assert unknown.value.detail.code is ErrorCode.INVALID_ARGUMENT


def test_failed_run(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.script("read_a", failure(ErrorCode.HOST_BUSY))
    workflow = chain(steps("read_a"))
    first = asyncio.run(rig.engine(workflow).start(request()))
    _append(rig, first.run_id, _started("csi", CSI_ONE), (T.RUN_FAILED, {"reason": "abandoned", "by": "engineer:x"}))
    mark = len(rig.log)
    failed = asyncio.run(rig.engine(workflow).resume(first.run_id))
    assert (failed.status, failed.output, failed.escalation) == (RunStatus.FAILED, None, None)
    assert rig.log[mark:] == ["host.close_started"]
    assert rig.host.closed == [CSI_ONE]


def test_recorded_prefix_is_replayed_without_port_calls(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))
    workflow = chain([("read_a", {"n": 0}), ("write_b", {"n": 1, "model": "m1"}), ("read_c", {"n": 2})])
    first = asyncio.run(rig.engine(workflow).start(request()))
    run_id = first.run_id
    recorded = [s.result_ref for s in _steps(rig, run_id) if s.status == "completed"]
    mark, ledger = len(rig.log), len(rig.host.ledger)
    outcome = asyncio.run(rig.engine(workflow).resume(run_id))
    assert outcome.status is RunStatus.COMPLETED
    assert isinstance(outcome.output, ChainOutput)
    assert outcome.output.refs[:2] == recorded  # the first two steps returned what the journal holds
    # the resume read the unreleased tools; only the third step went further, to describe and call its tool
    assert rig.log[mark:] == ["tool.unreleased_tools", "tool.describe", "tool.call"]
    assert len(rig.host.ledger) == ledger + 1
    assert (rig.host.ledger[-1].tool, rig.host.ledger[-1].op_id) == ("read_c", op_id(run_id, "2", 2))
    events = rig.events(run_id)
    assert [e.type for e in events[-5:]] == [
        T.RUN_ESCALATED, T.RUN_RESUMED, T.STEP_STARTED, T.STEP_COMPLETED, T.RUN_COMPLETED,
    ]  # fmt: skip
    resumed, started = events[-4].payload, events[-3]
    assert isinstance(resumed, ev.RunResumed)
    assert (resumed.resume_no, resumed.code_hash_changed, resumed.servers) == (1, False, [])
    assert resumed.restored_to_seq is None
    assert (started.path, started.attempt) == ("2", 2)  # the recorded retryable failure ran again as attempt 2
    views = [(s.path, s.attempt, s.status) for s in _steps(rig, run_id)]
    assert views == [
        ("0", 1, "completed"), ("1", 1, "completed"), ("2", 1, "failed"), ("2", 2, "completed"),
    ]  # fmt: skip


def test_recorded_failures(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.script("read_c", failure(ErrorCode.INVALID_ARGUMENT, "the argument is wrong"))
    workflow = chain(steps("read_a", "read_c"))
    first = asyncio.run(rig.engine(workflow).start(request()))
    run_id = first.run_id
    assert first.status is RunStatus.NEEDS_ENGINEER
    assert first.escalation is not None
    assert (first.escalation.reason, first.escalation.detail) == ("unhandled_error", "the argument is wrong")
    failed = rig.events(run_id)[-2].payload
    assert isinstance(failed, ev.StepFailed)
    assert failed.retryable is False
    assert isinstance(failed.error, ErrorDetail)
    assert failed.error.code is ErrorCode.INVALID_ARGUMENT
    mark, ledger = len(rig.log), len(rig.host.ledger)
    second = asyncio.run(
        rig.engine(workflow).resume(run_id)
    )  # a non-retryable failure is raised again from the journal
    assert (second.status, second.escalation) == (first.status, first.escalation)
    assert rig.log[mark:] == ["tool.unreleased_tools"]  # and nothing else: the failed step was not called again
    assert len(rig.host.ledger) == ledger
    assert [e.type for e in rig.events(run_id)[-3:]] == [T.RUN_ESCALATED, T.RUN_RESUMED, T.RUN_ESCALATED]


def test_journal_without_a_header(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    workflow = chain(steps("read_a"))
    empty = rig.forge(None)  # a crash between the creation of the journal and `run_started`
    headless = rig.forge(None, (T.RUN_RESUMED, None, {"resume_no": 1, "code_hash_changed": False, "servers": []}))
    for run_id in (empty, headless):
        with pytest.raises(JournalIntegrityError, match="run_started"):
            asyncio.run(rig.engine(workflow).resume(run_id))
    assert rig.log == []


def test_resume_holds_the_run_lock(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))  # the first run stops after its first step, resumable
    engine = rig.engine(chain(steps("read_a", "read_c")))
    first = asyncio.run(engine.start(request()))
    run_dir = rig.run_dir(first.run_id)
    assert not is_locked(run_dir)  # released when the run returned
    before, calls, logged = rig.events(first.run_id), list(rig.host.locked), list(rig.log)
    with hold_lock(run_dir) as holder:
        assert is_locked(run_dir)
        with pytest.raises(RunLocked) as refused:
            asyncio.run(engine.resume(first.run_id))
        assert refused.value.code is HarnessCode.RUN_LOCKED
        assert rig.events(first.run_id) == before  # the journal is unchanged
        assert (rig.host.locked, rig.log) == (calls, logged)  # and no port was called
        holder.kill()  # the holder dies without releasing anything
        holder.join()
    assert not is_locked(run_dir)
    second = asyncio.run(engine.resume(first.run_id))  # the next engine opens the run
    assert second.status is RunStatus.COMPLETED
    assert rig.host.locked[len(calls) :] == [True]  # and holds the lock for the one live call it makes
    assert not is_locked(run_dir)  # until the run returns
