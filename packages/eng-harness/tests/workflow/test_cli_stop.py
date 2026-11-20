"""`stop` command: live run pauses at safe point, idle/missing/workspace cases (spec 0006 AC9, AC71; plan T16)."""

import threading
from pathlib import Path

from eng_contract.ids import FixedClock
from helpers.cli_deps import START_MS, WORKFLOW, Rig, Session, completes

from eng_harness._runlock import RunLock
from eng_harness.cli import ExitCode
from eng_harness.cli._control import STOP_FILE
from eng_harness.engine import RunOutcome
from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev


def test_stop_wait_blocks_until_lock_released(tmp_path: Path) -> None:
    import time

    rig = Rig(tmp_path / "wait", script=completes)
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    [run_id] = rig.run_ids()
    run_dir = rig.runs / run_id
    lock = RunLock(run_dir)
    lock.acquire()
    result: list[int] = []
    finished = threading.Event()
    stop_rig = Rig(tmp_path / "wait")

    def stop() -> None:
        try:
            result.append(stop_rig.main("stop", run_id, "--wait", "5", clock=FixedClock(START_MS, 1)))
        finally:
            finished.set()

    thread = threading.Thread(target=stop, daemon=True)
    try:
        thread.start()
        deadline = time.monotonic() + 3
        while not (run_dir / STOP_FILE).exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (run_dir / STOP_FILE).exists()
        assert not finished.wait(timeout=0.2)
    finally:
        lock.release()
        thread.join(timeout=5)
    assert finished.is_set()
    assert result == [ExitCode.OK]
    assert "stopped" in stop_rig.out.getvalue().lower()


def test_stop_pauses_at_safe_point(tmp_path: Path) -> None:
    # 1. Live run holding its run lock pauses at the next safe point when `stop <run_id>` is called.
    rig = Rig(tmp_path / "live")
    started = threading.Event()
    observed_run_id: list[str] = []

    async def long_step(session: Session) -> RunOutcome:
        run_dir = session.engine.workspace.root / "runs" / session.run_id
        lock = RunLock(run_dir)
        lock.acquire()
        observed_run_id.append(session.run_id)
        started.set()
        try:
            control = session.ports.run_control
            assert control is not None
            import asyncio

            for _ in range(200):
                if control.stop_requested(session.run_id):
                    return session.paused("stop_requested")
                await asyncio.sleep(0.01)
            return session.completed()
        finally:
            lock.release()

    rig.script = long_step
    exit_codes: list[int] = []
    thread = threading.Thread(
        target=lambda: exit_codes.append(rig.main("run", WORKFLOW, "--no-report", "--progress", "off")),
        daemon=True,
    )
    thread.start()
    assert started.wait(timeout=5)
    run_id = observed_run_id[0]

    stop_rig = Rig(tmp_path / "live")
    assert stop_rig.main("stop", run_id, "--wait", "5", clock=FixedClock(START_MS, 1)) == ExitCode.OK
    thread.join(timeout=5)
    assert exit_codes == [ExitCode.STOPPED]
    run_dir = rig.runs / run_id
    assert not (run_dir / STOP_FILE).exists()  # run process removes stop.json on return (spec 4.4.8)
    reader = JournalReader(run_dir)
    try:
        assert reader.events()[-1].payload == ev.RunPaused(reason="stop_requested", request_ids=[])
    finally:
        reader.close()

    # 2. Run with no live engine: exits 0, says it is not running, writes no stop file.
    idle_rig = Rig(tmp_path / "idle", script=completes)
    assert idle_rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    [idle_id] = idle_rig.run_ids()
    stop_idle = Rig(tmp_path / "idle")
    assert stop_idle.main("stop", idle_id) == ExitCode.OK
    assert "not running" in stop_idle.out.getvalue().lower()
    assert not (idle_rig.runs / idle_id / STOP_FILE).exists()

    # 3. Unknown run id exits 6 and writes nothing.
    missing_id = "run_" + "0" * 26
    for bad_id in (missing_id, "../escape"):
        stop_miss = Rig(tmp_path / "idle")
        assert stop_miss.main("stop", bad_id) == ExitCode.NOT_FOUND
        assert bad_id in stop_miss.err.getvalue()

    # 4. Invalid workspace exits 2 with message and remedy, nothing created (AC71).
    stop_nows = Rig(tmp_path / "no_ws")
    assert stop_nows.main("stop", missing_id, environ={}) == ExitCode.USAGE
    assert "no workspace is configured (set ENG_WORKSPACE)" in stop_nows.err.getvalue()
    assert not stop_nows.workspace.exists()


def test_stop_wait_timeout_and_negative_wait(tmp_path: Path) -> None:
    rig = Rig(tmp_path / "held", script=completes)
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    [run_id] = rig.run_ids()
    run_dir = rig.runs / run_id

    # Negative --wait is a usage error.
    neg = Rig(tmp_path / "held")
    assert neg.main("stop", run_id, "--wait", "-1") == ExitCode.USAGE
    assert "--wait" in neg.err.getvalue()

    # --wait 0 while lock remains held writes stop.json and reports still stopping.
    lock = RunLock(run_dir)
    lock.acquire()
    try:
        wait_zero = Rig(tmp_path / "held")
        assert wait_zero.main("stop", run_id, "--wait", "0", clock=FixedClock(START_MS, 1)) == ExitCode.OK
        assert (run_dir / STOP_FILE).is_file()
        assert "still stopping" in wait_zero.out.getvalue().lower()
    finally:
        lock.release()


def test_stop_real_engine_pauses_at_safe_point(tmp_path: Path) -> None:
    """AC9 re-check: `stop` pauses a live real engine at the next safe point (plan T17; FileRunControl wired)."""
    import time
    from typing import Any, cast

    from eng_contract.ids import SeededIdSource
    from helpers.cli_deps import FakeInput, FakeOutput, FakePorts
    from workflows.rig import Host

    from eng_harness.block import Registry, workflow

    entered = threading.Event()
    release = threading.Event()

    class BlockingHost(Host):
        async def call(self, tool: str, args: Any, *, op_id: str, model: str | None = None) -> Any:
            if not entered.is_set():
                entered.set()
                assert release.wait(30)
            return await super().call(tool, args, op_id=op_id, model=model)

    @workflow(name="stop_flow", version=1, description="Two reads so stop can land between them.")
    async def stop_flow(ctx: Any, inp: FakeInput) -> FakeOutput:
        await ctx.tool("read_a", {"n": 0})
        await ctx.tool("read_a", {"n": 1})
        return FakeOutput()

    rig = Rig(tmp_path / "live", real_engine=True)
    hosts: list[BlockingHost] = []

    def port_builder(
        config: Any,
        workspace: Any,
        store: Any,
        run_folder: Any,
        clock: Any,
        ids: Any,
        *,
        files: Any = None,
        visible: bool = False,
    ) -> FakePorts:
        host = BlockingHost(cast(SeededIdSource, ids), clock, workspace.root / "runs")
        hosts.append(host)
        rig.built.append((config, workspace, store, run_folder))
        return FakePorts(rig.log, host)

    exit_codes: list[int] = []
    thread = threading.Thread(
        target=lambda: exit_codes.append(
            rig.main(
                "run",
                "stop_flow",
                "--no-report",
                "--progress",
                "off",
                workflow_registry=Registry([stop_flow]),
                port_builder=port_builder,
            )
        ),
        daemon=True,
    )
    thread.start()
    assert entered.wait(timeout=10)
    deadline = time.monotonic() + 10
    while not (rig.workspace / "runs").exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    run_ids = sorted(p.name for p in (rig.workspace / "runs").iterdir())
    assert run_ids
    run_id = run_ids[0]

    stop_rig = Rig(tmp_path / "live")
    assert stop_rig.main("stop", run_id, "--wait", "5", clock=FixedClock(START_MS, 1)) == ExitCode.OK
    release.set()
    thread.join(timeout=15)
    assert exit_codes == [ExitCode.STOPPED]
    run_dir = rig.runs / run_id
    assert not (run_dir / STOP_FILE).exists()
    reader = JournalReader(run_dir)
    try:
        assert reader.events()[-1].payload == ev.RunPaused(reason="stop_requested", request_ids=[])
    finally:
        reader.close()
