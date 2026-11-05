"""One engine per run (plan 0001 T9; spec 0001 4.4.4, AC23).

`Engine.start` holds the run lock from the creation of the run folder until the run returns, however it ends; a second
engine, here a second Python process, gets `RunLocked` and the journal stays as it was; and the operating system frees
the lock when its holder is killed. The holder is a child process, so the lock is the operating system's, not an object
of this process. The resume half of AC23 (a second engine that resumes the run, and the next one after the kill) is
task T9b. The Windows variant is `tests/windows/test_run_lock_windows.py`. The rig is local to this file: the task's
file scope holds no shared test helper.
"""

import asyncio
import sys
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from fakes.ports import ENVELOPE, FakeApprovalPort, FakeBasisPort, FakeCalcPort, FakeHost, FakeInputPort, Raise
from pydantic import BaseModel, JsonValue

from eng_harness._kinds import HARNESS_KINDS
from eng_harness._runlock import RunLock
from eng_harness.block import Registry, workflow
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunOutcome, RunRequest, RunStatus
from eng_harness.errors import HarnessCode, RunLocked
from eng_harness.journal import EventType, JournalReader, is_locked
from eng_harness.ports import RunClass, ToolInfo

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
BASIS_REF = "res_" + "0" * 26
WRITE = ToolInfo(name="write_b", effect="write", action="plain", host_key="csi", model_param="model")
HOLDER = """
import sys
from pathlib import Path
from eng_harness._runlock import RunLock
RunLock(Path(sys.argv[1])).acquire()
print("held", flush=True)
sys.stdin.read()
"""
"""A second process that takes the run lock of the folder it is given, says so, and holds it until it is killed."""
PROBE = """
import sys
from pathlib import Path
from eng_harness._runlock import RunLock
from eng_harness.errors import RunLocked
try:
    RunLock(Path(sys.argv[1])).acquire()
except RunLocked as exc:
    print(exc.code.value)
else:
    print("acquired")
"""
"""A second engine as far as the lock goes: it tries the run lock of the folder it is given and prints the outcome."""


class Empty(BaseModel):
    """Input of the test workflow."""


class Written(BaseModel):
    """Output of the test workflow: the result reference of its one step."""

    ref: str


@workflow(name="one_write", version=1, description="Calls one write tool.")
async def one_write(ctx: Any, inp: Empty) -> Written:
    """Calls `write_b` once."""
    result = await ctx.tool("write_b", {"n": 0, "model": "m1"})
    return Written(ref=result.ref.ref)


class Crash(BaseException):  # not an engine stop: it leaves the engine as a process crash would
    """An exit that no engine code catches."""


@dataclass(frozen=True)
class Sighting:
    """What a second engine sees of a run that is under way: the lock, the answer of a probe process, the journal."""

    locked: bool
    second_engine: str
    journal_unchanged: bool
    status: str


async def spawn(code: str, run_dir: Path) -> asyncio.subprocess.Process:
    """Start a Python process (isolated from the environment) that runs `code` with `run_dir` as its argument."""
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-c",
        code,
        str(run_dir),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )


class WatchingHost(FakeHost):
    """The fake host; before each call it looks at the only run under `runs_dir` the way a second engine would."""

    def __init__(self, ids: SeededIdSource, clock: FixedClock, runs_dir: Path) -> None:
        """Serve the tool `write_b`; `runs_dir` holds the one run being watched."""
        super().__init__([WRITE], ids, clock)
        self.sightings: list[Sighting] = []
        self._runs_dir = runs_dir

    async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> ENVELOPE:
        """Record a `Sighting`, then behave as the fake host."""
        (run_dir,) = self._runs_dir.iterdir()
        reader = JournalReader(run_dir)
        before = reader.events()
        probe = await spawn(PROBE, run_dir)
        async with asyncio.timeout(60):
            answer, _ = await probe.communicate()
        sighting = Sighting(
            locked=is_locked(run_dir),
            second_engine=answer.decode().strip(),
            journal_unchanged=reader.events() == before,
            status=reader.run().status,
        )
        reader.close()
        self.sightings.append(sighting)
        return await super().call(tool, args, op_id=op_id, model=model)


def make_engine(root: Path) -> tuple[Engine, WatchingHost, Path]:
    """An engine over a watching fake host in a workspace under `root`; also the folder that will hold its run."""
    clock = FixedClock(START_MS, 1)
    ids = SeededIdSource(b"harness", clock)
    workspace = Workspace(root=root / "ws", classification=LocationClass.LOCAL)
    runs_dir = workspace.root / "runs"
    host = WatchingHost(ids, clock, runs_dir)
    ports = EnginePorts(
        tool=host,
        host=host,
        calc=FakeCalcPort(RunClass.PRODUCTION, []),
        basis=FakeBasisPort({}),
        approvals=FakeApprovalPort(),
        inputs=FakeInputPort(),
    )
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    engine = Engine(workspace, Registry([one_write]), ports, store, EngineSettings(), clock, ids)
    return engine, host, runs_dir


def start(engine: Engine) -> Coroutine[Any, Any, RunOutcome]:
    """Start the run of the test workflow; the awaitable is run by `asyncio.run`."""
    return engine.start(RunRequest(workflow="one_write", input={}, basis_ref=BASIS_REF, run_class=RunClass.PRODUCTION))


def test_one_engine_per_run(tmp_path: Path) -> None:
    engine, host, runs_dir = make_engine(tmp_path)
    outcome = asyncio.run(start(engine))
    assert outcome.status is RunStatus.COMPLETED
    # While the run was under way (at its one tool call): the lock was held, a second engine in another process was
    # refused with RUN_LOCKED, its attempt left the journal as it was, and the reader saw an engine at work.
    assert host.sightings == [
        Sighting(locked=True, second_engine="RUN_LOCKED", journal_unchanged=True, status="RUNNING")
    ]
    (run_dir,) = runs_dir.iterdir()
    assert not is_locked(run_dir)  # released when the run returned
    reader = JournalReader(run_dir)
    assert reader.run().status == "COMPLETED"
    reader.close()


def test_lock_is_released_when_the_run_ends_abnormally(tmp_path: Path) -> None:
    engine, host, runs_dir = make_engine(tmp_path)
    host.script("write_b", Raise(Crash()))
    with pytest.raises(Crash):
        asyncio.run(start(engine))
    (run_dir,) = runs_dir.iterdir()
    assert not is_locked(run_dir)
    reader = JournalReader(run_dir)  # the journal that the crash left verifies, and shows a run no engine holds
    assert [e.type for e in reader.events()] == [EventType.RUN_STARTED, EventType.STEP_STARTED]
    assert reader.run().status == "INTERRUPTED"
    reader.close()


def test_killed_holder_releases_the_lock(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_holder"
    run_dir.mkdir()

    async def scenario() -> None:
        holder = await spawn(HOLDER, run_dir)
        try:
            assert holder.stdout is not None
            async with asyncio.timeout(60):
                assert (await holder.stdout.readline()).strip() == b"held"
            assert is_locked(run_dir)
            with pytest.raises(RunLocked) as refused:
                RunLock(run_dir).acquire()
            assert refused.value.code is HarnessCode.RUN_LOCKED
            holder.kill()  # the holder dies without releasing anything
            await holder.wait()
        finally:
            if holder.returncode is None:
                holder.kill()
                await holder.wait()
        assert not is_locked(run_dir)
        again = RunLock(run_dir)  # the next engine opens the run
        again.acquire()
        assert is_locked(run_dir)
        again.release()

    asyncio.run(scenario())
