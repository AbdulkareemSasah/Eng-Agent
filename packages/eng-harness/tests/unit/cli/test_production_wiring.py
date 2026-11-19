"""Production wiring of progress, run-control and the heartbeat (plan 0006 T16b; AC9, AC18, AC19, AC37, AC62)."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from helpers.cli_deps import WORKFLOW, FakeCalc, FakeInput, FakeOutput, Placeholder, Rig, completes
from workflows.rig import Host

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.basis import StoreBasisPort
from eng_harness.block import Registry, workflow
from eng_harness.cli import ExitCode
from eng_harness.cli._control import FileRunControl
from eng_harness.cli._wiring import IsolatingFanOut, RunIdCell, RunPortSet, default_engine_factory, heartbeat_run_dir
from eng_harness.engine import EngineSettings
from eng_harness.journal import Event, EventType
from eng_harness.journal import _events as ev
from eng_harness.pages import PageApprovalPort
from eng_harness.ports import ApprovalPort, ApprovalRequest, CalcPort, InputPort, RunClass
from eng_harness.progress import ExpectedTimes, Heartbeat, ProgressRenderer, TerminalProgress

SHA = "a" * 64
START_MS = 1_767_225_600_000
RUN_ID = "run_" + "0" * 26


class _FakeDecisionPort:
    def __init__(self, summary: dict[str, object] | None = None) -> None:
        self._summary = summary or {"providers": ["ok"]}

    async def decide(self, call: object) -> object:
        raise AssertionError("not called")

    async def decide_many(self, calls: Sequence[object]) -> list[object]:
        raise AssertionError("not called")

    def runtime_summary(self) -> dict[str, object]:
        return dict(self._summary)


class _Recording:
    """A ProgressSink that keeps every event it was given."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


class _Raising:
    """A ProgressSink that fails once, then would succeed if not detached."""

    def __init__(self, message: str = "member defect") -> None:
        self.message = message
        self.calls = 0

    def emit(self, event: Event) -> None:
        self.calls += 1
        raise RuntimeError(self.message)


def _header(run_id: str = RUN_ID) -> Event:
    payload = ev.RunHeader.model_validate(
        {
            "run_id": run_id,
            "workflow": "noop",
            "block": {"name": "noop", "version": "1", "code_sha256": SHA},
            "input_ref": "res_" + "0" * 26,
            "input_sha256": SHA,
            "basis_ref": "res_" + "0" * 26,
            "mode": "work_on_copy",
            "run_class": "trial",
            "engine_version": "0",
            "contract_version": "eng-contract/1",
            "settings_sha256": SHA,
            "servers": [],
            "always_ask": [],
        }
    )
    return Event(1, EventType.RUN_STARTED, None, None, "2026-01-01T00:00:00.000Z", payload)


def _resolved(request_id: str = "apr_one") -> Event:
    payload = ev.ApprovalResolved.model_validate(
        {
            "request_id": request_id,
            "shown_sha256": SHA,
            "decision": "approve",
            "rejected_items": [],
            "reason": None,
            "by": "engineer:ada",
        }
    )
    return Event(5, EventType.APPROVAL_RESOLVED, None, None, "2026-01-01T00:00:00.000Z", payload)


def test_engine_ports_carry_stop_progress_and_cascade(tmp_path: Path) -> None:
    """The default factory maps progress, run-control and decision; run_started fills the run-id cell (AC9, AC62)."""
    clock = FixedClock(START_MS, 1)
    ids = SeededIdSource(b"pw", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    runs = workspace.root / "runs"
    runs.mkdir(parents=True)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    host = Host(ids, clock, runs)
    cell = RunIdCell(runs)
    terminal = _Recording()
    page = PageApprovalPort(engineer="ada", stop_requested=lambda: False)
    progress = IsolatingFanOut([terminal, page.hub], cell=cell)
    control = FileRunControl(runs)
    decision = _FakeDecisionPort({"providers": ["cascade"]})

    @workflow(name="noop_pw", version=1, description="Empty typed flow.")
    async def noop_pw(ctx: Any, inp: FakeInput) -> FakeOutput:
        return FakeOutput()

    ports = RunPortSet(
        tool=cast(Any, host),
        host=cast(Any, host),
        calc=cast(CalcPort, FakeCalc((), RunClass.TRIAL)),
        basis=StoreBasisPort(store),
        approvals=cast(ApprovalPort, Placeholder()),
        inputs=cast(InputPort, Placeholder()),
        decision=cast(Any, decision),
        progress=progress,
        run_control=control,
    )
    engine = default_engine_factory(workspace, Registry([noop_pw]), ports, store, EngineSettings(), clock, ids)
    held = engine._ports
    assert held.progress is progress
    assert held.run_control is control
    assert held.decision is decision
    assert isinstance(held.run_control, FileRunControl)

    assert cell.run_id is None
    progress.emit(_header("run_" + "a" * 26))
    assert cell.run_id == "run_" + "a" * 26
    assert terminal.events[0].type is EventType.RUN_STARTED


def test_failing_sink_detached_alone() -> None:
    """A raising member is detached alone; the others keep receiving (AC19 fan-out path, AC37)."""
    good = _Recording()
    bad = _Raising()
    page = PageApprovalPort(engineer="ada", stop_requested=lambda: False)
    request = ApprovalRequest(
        request_id="apr_one",
        run_id=RUN_ID,
        kind="info",
        title="t",
        preview_ref="res_" + "0" * 26,
        shown_sha256=SHA,
        binding=(),
        items=(),
    )
    asyncio.run(page.present(request))
    fan = IsolatingFanOut([bad, good, page.hub])

    started = _header()
    fan.emit(started)
    assert bad.calls == 1
    assert [e.type for e in good.events] == [EventType.RUN_STARTED]

    resolved = _resolved()
    fan.emit(resolved)
    assert bad.calls == 1  # detached: not called again
    assert [e.type for e in good.events] == [EventType.RUN_STARTED, EventType.APPROVAL_RESOLVED]
    entry = page.hub._open["apr_one"]
    assert entry.recorded is True

    alone = IsolatingFanOut([_Raising("only")])
    with pytest.raises(RuntimeError, match="only"):
        alone.emit(started)


def test_heartbeat_follows_run_id_cell(tmp_path: Path) -> None:
    """No heartbeat.json before the cell fills; after, the file is written in the run folder (AC18)."""
    runs = tmp_path / "runs"
    runs.mkdir()
    cell = RunIdCell(runs)
    get = heartbeat_run_dir(cell)
    out = io.StringIO()
    sink = TerminalProgress(ProgressRenderer("plain", ExpectedTimes({})), out, mode="plain", queue_lines=100)
    clock = FixedClock(START_MS + 10_000, 10_000)
    beat = Heartbeat(sink, clock, interval_s=10, run_dir=get)

    beat.beat()
    assert list(runs.rglob("heartbeat.json")) == []
    assert get() is None

    cell.fill(RUN_ID)
    assert get() is None  # folder does not exist yet
    beat.beat()
    assert list(runs.rglob("heartbeat.json")) == []

    (runs / RUN_ID).mkdir()
    assert get() == runs / RUN_ID
    beat.beat()
    sink.close()
    path = runs / RUN_ID / "heartbeat.json"
    assert path.is_file()
    assert "heartbeat:" in out.getvalue()


def test_drive_starts_heartbeat_beside_the_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`run` starts the heartbeat task with the cell's folder callable and cancels it when the engine returns."""
    seen: list[Any] = []

    class _Spy(Heartbeat):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            seen.append(kwargs)
            super().__init__(*args, **kwargs)

        async def run(self) -> None:
            self.beat()
            await asyncio.Event().wait()

    monkeypatch.setattr("eng_harness.cli._run.Heartbeat", _Spy)
    rig = Rig(tmp_path / "hb", script=completes)
    rig.workspace.mkdir(parents=True)
    (rig.workspace / "harness.toml").write_text("[progress]\nheartbeat_s = 1\n", encoding="utf-8")
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "plain") == ExitCode.OK
    assert len(seen) == 1
    assert seen[0]["interval_s"] == 1
    assert callable(seen[0]["run_dir"])
    [run_id] = rig.run_ids()
    assert (rig.runs / run_id).is_dir()


def test_run_installs_fan_out_and_file_run_control(tmp_path: Path) -> None:
    """`run` hands the isolating fan-out and FileRunControl to the engine factory (AC9, AC37)."""
    held: list[Any] = []

    async def capture(session: Any) -> Any:
        held.append(session.ports)
        assert session.ports.run_control is not None
        assert session.ports.run_control.stop_requested(session.run_id) is False
        assert isinstance(session.ports.progress, IsolatingFanOut)
        assert session.ports.decision is not None
        return session.completed()

    rig = Rig(tmp_path / "ports", script=capture)
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "plain") == ExitCode.OK
    assert len(held) == 1
    assert isinstance(held[0].run_control, FileRunControl)
    assert held[0].progress is not None
    [run_id] = rig.run_ids()
    assert held[0].progress._cell is not None
    assert held[0].progress._cell.run_id == run_id
