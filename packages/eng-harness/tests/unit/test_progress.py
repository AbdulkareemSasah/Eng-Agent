"""The ProgressSink and the journal's commit hook (plan 0001 T18, amendment B-509; spec 0001 4.10, AC58).

The sink gets every event after its commit, in `seq` order, before the next step starts; a sink that raises is detached
and the failure is logged. The seam is the `on_commit` keyword of `JournalWriter`.
"""

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import ClassVar

import pytest
from eng_contract.errors import ContractError, ErrorCode
from fakes.ports import FakeBasisPort, FakeCalcPort, RecordingProgressSink, failure
from workflows.chain import chain
from workflows.rig import Rig, make_rig, request, steps

from eng_harness.block import Registry
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunStatus
from eng_harness.journal import INLINE_EVENT_BYTES, Event, EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import ProgressSink

T = EventType
THREE = steps("read_a", "write_b", "read_c")


class Watching(RecordingProgressSink):
    """Records, for each event, the last `seq` found on disk and the number of host calls at the moment of delivery."""

    def __init__(self, rig: Rig) -> None:
        super().__init__()
        self._rig = rig
        self.on_disk: list[int] = []
        self.calls: list[int] = []

    def emit(self, event: Event) -> None:
        super().emit(event)
        self.on_disk.append(self._rig.events(self._rig.run_ids()[0])[-1].seq)
        self.calls.append(len(self._rig.host.ledger))


class Failing(RecordingProgressSink):
    """Keeps `keep` events, then raises on every call; `attempts` counts the calls."""

    def __init__(self, keep: int) -> None:
        super().__init__()
        self._keep, self.attempts = keep, 0

    def emit(self, event: Event) -> None:
        self.attempts += 1
        if len(self.events) >= self._keep:
            raise RuntimeError("the sink broke")
        super().emit(event)


def _engine(rig: Rig, sink: ProgressSink) -> Engine:
    ports = EnginePorts(
        tool=rig.host, host=rig.host, calc=FakeCalcPort(rig.run_class, rig.calc_infos),
        basis=FakeBasisPort(rig.bases), approvals=rig.approvals, inputs=rig.inputs, progress=sink,
    )  # fmt: skip
    return Engine(rig.workspace, Registry([chain(THREE)]), ports, rig.store, EngineSettings(), rig.clock, rig.ids)


def test_sink_order_and_failure(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    rig = make_rig(tmp_path / "ok")
    sink = Watching(rig)
    outcome = asyncio.run(_engine(rig, sink).start(request()))
    journal = rig.events(outcome.run_id)
    assert outcome.status is RunStatus.COMPLETED
    assert sink.events == journal  # every event once, in `seq` order, with the payload as stored (`run_started` too)
    assert sink.on_disk == [e.seq for e in journal]  # each one was committed when it was delivered
    started = {e.path: calls for e, calls in zip(sink.events, sink.calls, strict=True) if e.type is T.STEP_STARTED}
    assert started == {"0": 0, "1": 1, "2": 2}  # and delivered before the next step's call
    # a sink that raises is detached and the failure logged; the run goes on and the journal stays complete
    rig = make_rig(tmp_path / "broken")
    broken = Failing(2)
    with caplog.at_level(logging.WARNING):
        outcome = asyncio.run(_engine(rig, broken).start(request()))
    assert outcome.status is RunStatus.COMPLETED
    assert (len(broken.events), broken.attempts) == (2, 3)  # never called again after the failure
    assert [e.type for e in rig.events(outcome.run_id)][-1] is T.RUN_COMPLETED
    assert "the sink broke" in caplog.text
    # a resume delivers its events too, from `run_resumed` on, in the same order as the journal
    rig = make_rig(tmp_path / "resumed")
    first, second = RecordingProgressSink(), RecordingProgressSink()
    rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))
    stopped = asyncio.run(_engine(rig, first).start(request()))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    done = asyncio.run(_engine(rig, second).resume(stopped.run_id))
    assert done.status is RunStatus.COMPLETED
    journal = rig.events(stopped.run_id)
    assert first.events[0].type is T.RUN_STARTED
    assert first.events + second.events == journal
    assert second.events[0].type is T.RUN_RESUMED


class _Failing(sqlite3.Connection):
    fail: ClassVar[bool] = False

    def commit(self) -> None:
        if _Failing.fail:
            raise sqlite3.OperationalError("disk full")
        super().commit()


def test_commit_hook_runs_once_per_append_after_the_commit(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run_dir = rig.workspace.root / "runs" / "run_x"
    run_dir.mkdir(parents=True)
    seen: list[tuple[Event, int, int]] = []

    def hook(event: Event) -> None:
        with sqlite3.connect(run_dir / "journal.sqlite") as other:  # a second connection sees the committed row
            rows = other.execute("SELECT count(*) FROM events").fetchone()[0]
        seen.append((event, rows, writer.last_seq))

    def connect(path: str) -> sqlite3.Connection:
        return _Failing(path, isolation_level=None)

    writer = JournalWriter(run_dir, rig.store, rig.clock, rig.ids, connect=connect, on_commit=hook)
    assert seen == []  # the journal's own creation is no event
    pause = {"reason": "stop_requested", "request_ids": []}
    seq = writer.append(T.RUN_PAUSED, pause)
    event, rows, last = seen[0]
    assert (len(seen), event.seq, event.type, event.path, event.attempt) == (1, seq, T.RUN_PAUSED, None, None)
    assert event.payload == ev.RunPaused.model_validate(pause)
    assert (rows, last) == (seq, seq)  # committed, and `seq` already advanced
    step = {"kind": "tool", "name": "t", "args": {"a": "y" * (INLINE_EVENT_BYTES + 1)}, "args_sha256": "a" * 64}
    writer.append(T.STEP_STARTED, {**step, "effect": "read"}, path="0", attempt=1)
    started = seen[1][0].payload
    assert isinstance(started, ev.StepStarted)
    assert (len(seen), seen[1][0].path, seen[1][0].attempt) == (2, "0", 1)
    assert started.args is None  # the event is built from the stored body: `args_ref` is visible
    assert started.args_ref is not None
    with pytest.raises(ContractError):
        writer.append(T.RUN_PAUSED, {"reason": "bogus", "request_ids": []})  # an invalid payload is no event
    _Failing.fail = True
    try:
        with pytest.raises(ContractError):
            writer.append(T.RUN_PAUSED, pause)  # a failed write is no event
    finally:
        _Failing.fail = False
    assert (len(seen), writer.last_seq) == (2, seq + 1)
    writer.close()
