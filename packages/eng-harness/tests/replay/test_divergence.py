"""Replay divergence, the version rule and the replay index (plan 0001 T9; spec 0001 4.2, 4.5.2, AC28, AC29).

The engine-level tests interrupt a run of the `ORIGINAL` workflow at its third step (a retryable failure), resume it
with a changed workflow, and check that the resume stops before any live tool call with `run_escalated` and that the
original workflow still finishes the run. The index-level tests drive `ReplayIndex` with hand-built events, for the
rules the ctx calls of plan task T10 will exercise (a parallel size, an approval preview, a child block).
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.errors import ErrorCode, ErrorDetail
from fakes.ports import failure
from workflows import chain_edited
from workflows.chain import ORIGINAL, ChainOutput, chain, chain_retyped
from workflows.rig import Rig, make_rig, request

from eng_harness.block import WorkflowDef
from eng_harness.engine import RunStatus
from eng_harness.engine._replay import Recorded, ReplayIndex
from eng_harness.engine._steps import op_id
from eng_harness.errors import HarnessCode, JournalIntegrityError, NeedsReconciliation, ReplayDivergence
from eng_harness.journal import Event, EventType
from eng_harness.journal import _events as ev

T = EventType
REF = "res_" + "1" * 26
AT = "2026-01-01T00:00:00.000Z"


def _interrupted(tmp_path: Path) -> tuple[Rig, str, list[str]]:
    """A run of `ORIGINAL` that stopped at its third step, its id, and the result references of steps 0 and 1."""
    rig = make_rig(tmp_path)
    rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))
    first = asyncio.run(rig.engine(chain(ORIGINAL)).start(request(values={"count": 3})))
    assert first.status is RunStatus.NEEDS_ENGINEER
    events = rig.events(first.run_id)
    refs = [e.payload.result.ref for e in events if isinstance(e.payload, ev.StepCompleted) and e.payload.result]
    return rig, first.run_id, refs


# variant name -> (the changed workflow, whether the change is found in the run header, before the block is called)
VARIANTS: dict[str, tuple[Callable[[], WorkflowDef[Any, Any]], bool]] = {
    "changed_argument": (lambda: chain([("read_a", {"n": 99}), *ORIGINAL[1:]]), False),
    "changed_tool": (lambda: chain([("read_c", {"n": 0}), *ORIGINAL[1:]]), False),
    "inserted_step": (lambda: chain([ORIGINAL[0], ("read_c", {"n": 7}), *ORIGINAL[1:]]), False),
    "removed_step": (lambda: chain([ORIGINAL[0], ORIGINAL[2]]), False),
    "changed_argument_of_the_failed_step": (lambda: chain([*ORIGINAL[:2], ("read_c", {"n": 99})]), False),
    "block_ends_before_the_journal_does": (lambda: chain(ORIGINAL[:2]), False),
    "block_name": (lambda: chain(ORIGINAL, name="renamed"), True),
    "block_version": (lambda: chain(ORIGINAL, version=2), True),
    "run_input": (lambda: chain_retyped, True),
}


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_divergence_variants(tmp_path: Path, variant: str) -> None:
    rig, run_id, recorded = _interrupted(tmp_path)
    changed, in_header = VARIANTS[variant]
    before, mark, ledger = rig.events(run_id), len(rig.log), len(rig.host.ledger)
    stopped = asyncio.run(rig.engine(changed()).resume(run_id))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.output is None
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "replay_divergence"
    assert len(rig.host.ledger) == ledger  # no live tool call
    assert set(rig.log[mark:]) <= {"tool.unreleased_tools"}  # and no other tool or host call either
    gained = rig.events(run_id)[len(before) :]
    # a header change is found before the resume is recorded; a changed step after it (spec 4.5.1 step 3)
    assert [e.type for e in gained] == ([T.RUN_ESCALATED] if in_header else [T.RUN_RESUMED, T.RUN_ESCALATED])
    escalated = gained[-1].payload
    assert isinstance(escalated, ev.RunEscalated)
    assert (escalated.reason, escalated.detail) == ("replay_divergence", stopped.escalation.detail)
    # the original workflow still resumes the run, from the recorded steps
    finished = asyncio.run(rig.engine(chain(ORIGINAL)).resume(run_id))
    assert finished.status is RunStatus.COMPLETED
    assert isinstance(finished.output, ChainOutput)
    assert finished.output.refs[:2] == recorded
    numbers = [e.payload.resume_no for e in rig.events(run_id) if isinstance(e.payload, ev.RunResumed)]
    assert numbers == list(range(1, len(numbers) + 1))


def test_hash_change_warns(tmp_path: Path) -> None:
    original = chain(chain_edited.STEPS)
    edited = chain_edited.chain_edited
    assert (edited.name, edited.version) == (original.name, original.version)
    assert edited.code_sha256 != original.code_sha256  # the same name and version, another source
    rig = make_rig(tmp_path)
    rig.host.script("write_b", failure(ErrorCode.HOST_BUSY), failure(ErrorCode.HOST_BUSY))
    first = asyncio.run(rig.engine(original).start(request()))
    run_id = first.run_id
    head = rig.events(run_id)[0].payload
    assert isinstance(head, ev.RunHeader)
    assert head.block.code_sha256 == original.code_sha256
    asyncio.run(rig.engine(original).resume(run_id))  # the same code: no warning
    outcome = asyncio.run(rig.engine(edited).resume(run_id))  # the edited code: a warning, and the run continues
    assert outcome.status is RunStatus.COMPLETED
    resumed = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.RunResumed)]
    assert [r.code_hash_changed for r in resumed] == [False, True]
    assert rig.host.ledger[-1].op_id == op_id(run_id, "1", 3)  # the write ran live as the third attempt of its step
    assert [c.tool for c in rig.host.ledger] == ["read_a", "write_b", "write_b", "write_b"]


def test_input_hash_mismatch_diverges(tmp_path: Path) -> None:
    """A journal whose header names a run input of another hash than the stored one (a run input that changed)."""
    rig = make_rig(tmp_path)
    run_id = rig.forge(chain(ORIGINAL), input_sha256="f" * 64)
    stopped = asyncio.run(rig.engine(chain(ORIGINAL)).resume(run_id))
    assert stopped.escalation is not None
    assert (stopped.status, stopped.escalation.reason) == (RunStatus.NEEDS_ENGINEER, "replay_divergence")
    assert "input" in stopped.escalation.detail
    assert rig.types(run_id) == [T.RUN_STARTED, T.RUN_ESCALATED]
    assert rig.host.ledger == []


def test_harness_code_recorded_by_a_tool_step_diverges(tmp_path: Path) -> None:
    """A tool step never records a harness code, so a journal that says it did does not fit the block's call."""
    rig = make_rig(tmp_path)
    started = {
        "kind": "tool", "name": "read_a", "args": {"n": 0}, "args_sha256": payload_sha256({"n": 0}), "effect": "read",
    }  # fmt: skip
    failed = {"error": {"harness_code": "NOT_IMPLEMENTED", "message": "a gap"}, "retryable": False, "duration_ms": 1}
    run_id = rig.forge(chain(ORIGINAL), (T.STEP_STARTED, "0", started), (T.STEP_FAILED, "0", failed))
    stopped = asyncio.run(rig.engine(chain(ORIGINAL)).resume(run_id))
    assert stopped.escalation is not None
    assert (stopped.status, stopped.escalation.reason) == (RunStatus.NEEDS_ENGINEER, "replay_divergence")
    assert "NOT_IMPLEMENTED" in stopped.escalation.detail
    assert rig.host.ledger == []


# ---- the replay index, with hand-built events ------------------------------------------------------------------


D1 = payload_sha256({"n": 1})


def _event(seq: int, kind: EventType, path: str, attempt: int, payload: Any) -> Event:
    return Event(seq, kind, path, attempt, AT, payload)


def _begin(
    seq: int, path: str, attempt: int = 1, *, kind: str = "tool", name: str = "t", digest: str = D1, child: Any = None
) -> Event:
    started = ev.StepStarted(
        kind=kind, name=name, args={"n": 1}, args_sha256=digest, effect="read", child=child
    )  # the arguments are not checked against the digest: the index compares the digest only
    return _event(seq, T.STEP_STARTED, path, attempt, started)


def _done(seq: int, path: str, attempt: int = 1) -> Event:
    result = ev.StepResult(ref=REF, summary={"v": 1}, warnings=[], complete=True)
    return _event(seq, T.STEP_COMPLETED, path, attempt, ev.StepCompleted(result=result, duration_ms=1))


def _failed(seq: int, path: str, attempt: int = 1, *, retryable: bool) -> Event:
    code = ErrorCode.HOST_BUSY if retryable else ErrorCode.INVALID_ARGUMENT
    error = ErrorDetail(code=code, message="m", retryable=retryable)
    return _event(seq, T.STEP_FAILED, path, attempt, ev.StepFailed(error=error, retryable=retryable, duration_ms=1))


def _reconciled(seq: int, path: str, attempt: int, outcome: str, *, with_result: bool = True) -> Event:
    result = ev.StepResult(ref=REF, summary={}, warnings=[], complete=True) if with_result else None
    payload = ev.StepReconciled.model_validate(
        {"op_id": "op_x", "outcome": outcome, "result": result, "decided_by": "adapter", "evidence": []}
    )
    return _event(seq, T.STEP_RECONCILED, path, attempt, payload)


def test_lookup_compares_kind_name_arguments_and_child() -> None:
    child = ev.BlockRef(name="c", version="1", code_sha256="a" * 64)
    events = [_begin(1, "0"), _done(2, "0"), _begin(3, "1", kind="block", name="c", child=child), _done(4, "1")]
    same = ("0", "tool", "t", D1)
    assert ReplayIndex(events).lookup(*same) == Recorded(
        1, ev.StepResult(ref=REF, summary={"v": 1}, warnings=[], complete=True)
    )
    for other in (("0", "read", "t", D1), ("0", "tool", "u", D1), ("0", "tool", "t", "f" * 64)):
        with pytest.raises(ReplayDivergence) as raised:
            ReplayIndex(events).lookup(*other)
        assert raised.value.code is HarnessCode.REPLAY_DIVERGENCE
        assert "step 0" in raised.value.message
    # a block step is identified by the child's name and version, not by its code hash
    assert ReplayIndex(events).lookup("1", "block", "c", D1, ("c", "1")) is not None
    for wrong in (("c", "2"), ("d", "1"), None):
        with pytest.raises(ReplayDivergence):
            ReplayIndex(events).lookup("1", "block", "c", D1, wrong)
    with pytest.raises(ReplayDivergence):  # a child where the journal has none
        ReplayIndex(events).lookup("0", "tool", "t", D1, ("c", "1"))


def test_parallel_size_and_approval_preview_diverge() -> None:
    three, shown = payload_sha256({"children": 3}), payload_sha256({"preview": "a"})
    events = [
        _begin(1, "0", kind="parallel", name="parallel", digest=three), _done(2, "0"),
        _begin(3, "1", kind="approve", name="Review the change set", digest=shown), _done(4, "1"),
    ]  # fmt: skip
    assert ReplayIndex(events).lookup("0", "parallel", "parallel", three) is not None
    assert ReplayIndex(events).lookup("1", "approve", "Review the change set", shown) is not None
    with pytest.raises(ReplayDivergence):
        ReplayIndex(events).lookup("0", "parallel", "parallel", payload_sha256({"children": 2}))
    with pytest.raises(ReplayDivergence):
        ReplayIndex(events).lookup("1", "approve", "Review the change set", payload_sha256({"preview": "b"}))


def test_recorded_outcomes() -> None:
    result = ev.StepResult(ref=REF, summary={"v": 1}, warnings=[], complete=True)
    empty = ev.StepResult(ref=REF, summary={}, warnings=[], complete=True)
    call = ("0", "tool", "t", D1)
    cases: list[tuple[list[Event], Recorded | type[BaseException]]] = [
        ([_begin(1, "0"), _done(2, "0")], Recorded(1, result)),
        ([_begin(1, "0", 2), _done(2, "0", 2)], Recorded(2, result)),
        ([_begin(1, "0"), _failed(2, "0", retryable=True), _begin(3, "0", 2), _done(4, "0", 2)], Recorded(2, result)),
        ([_begin(1, "0"), _failed(2, "0", retryable=True)], Recorded(1, None)),  # runs again, as attempt 2
        ([_begin(1, "0"), _reconciled(2, "0", 1, "not_applied")], Recorded(1, None)),
        ([_begin(1, "0"), _reconciled(2, "0", 1, "applied")], Recorded(1, empty)),
        ([_begin(1, "0"), _reconciled(2, "0", 1, "applied", with_result=False)], NeedsReconciliation),
        ([_begin(1, "0")], NeedsReconciliation),  # in flight: never run again without knowing its outcome
    ]
    for events, expected in cases:
        if isinstance(expected, Recorded):
            assert ReplayIndex(events).lookup(*call) == expected
        else:
            with pytest.raises(expected):
                ReplayIndex(events).lookup(*call)
    error = ErrorDetail(code=ErrorCode.INVALID_ARGUMENT, message="m", retryable=False)
    assert ReplayIndex([_begin(1, "0"), _failed(2, "0", retryable=False)]).lookup(*call) == Recorded(1, error)


def test_unrecorded_and_unreplayed_paths() -> None:
    events = [
        _begin(1, "0"), _done(2, "0"),
        _begin(3, "0~host.units.m1"), _done(4, "0~host.units.m1"),
        _begin(5, "@resume1.units.m1"), _done(6, "@resume1.units.m1"),
    ]  # fmt: skip
    saved = ev.ModelSaved.model_validate(
        {"model_key": "m", "model_id": "mdl_" + "0" * 26, "revision": 1, "fingerprint": "f", "file_sha256": "a" * 64,
         "file_name": "a.edb", "role": "revision"}
    )  # fmt: skip
    index = ReplayIndex([*events, _event(7, T.MODEL_SAVED, "0", 1, saved)])  # an event of another kind at a path
    assert index.lookup("1", "tool", "t", D1) is None  # not recorded: the run goes live
    assert index.lookup("0~host.units.m1", "tool", "t", D1) is None  # an audit record of a host event
    assert index.lookup("@resume1.units.m1", "tool", "t", D1) is None  # housekeeping of a resume
    with pytest.raises(ReplayDivergence, match="0"):  # `0` is recorded and was not called
        index.finish()
    assert index.lookup("0", "tool", "t", D1) is not None
    index.finish()  # every replayable recorded path was visited; the host and housekeeping paths are not required


def test_finish_names_the_unvisited_paths() -> None:
    index = ReplayIndex([_begin(1, "2"), _done(2, "2"), _begin(3, "10"), _done(4, "10"), _begin(5, "1"), _done(6, "1")])
    with pytest.raises(ReplayDivergence) as raised:
        index.finish()
    assert raised.value.code is HarnessCode.REPLAY_DIVERGENCE
    assert all(f" {path}" in raised.value.message for path in ("1", "2", "10"))
    ReplayIndex([]).finish()  # an empty index has nothing to miss


def test_step_event_without_a_start_is_a_damaged_journal() -> None:
    with pytest.raises(JournalIntegrityError):
        ReplayIndex([_done(1, "0")])
