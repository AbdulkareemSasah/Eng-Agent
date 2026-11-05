"""The run lock on Windows (plan 0001 T9; spec 0001 4.4.4, AC23): the engine holds it, the killed holder frees it.

Defined only on Windows (as `tests/windows/test_jobs.py` does), so no skip enters the ratchet; it runs in the Windows CI
job, which runs only `tests/windows` and `tests/perf`, and has not run on Windows yet (owner local test,
`docs/local-testing.md`). Its twin on every platform is `tests/unit/test_run_lock.py`; the rig is repeated here because
the Windows job does not import from the other test folders and the task's file scope holds no shared helper.
"""

import sys
from pathlib import Path

if sys.platform == "win32":
    import asyncio
    from collections.abc import Mapping
    from typing import Any

    import pytest
    from eng_contract.ids import FixedClock, SeededIdSource
    from eng_contract.store import LocationClass, ResultStore, Workspace
    from fakes.ports import ENVELOPE, FakeApprovalPort, FakeBasisPort, FakeCalcPort, FakeHost, FakeInputPort
    from pydantic import BaseModel, JsonValue

    from eng_harness._kinds import HARNESS_KINDS
    from eng_harness._runlock import RunLock
    from eng_harness.block import Registry, workflow
    from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunRequest, RunStatus
    from eng_harness.errors import HarnessCode, RunLocked
    from eng_harness.journal import is_locked
    from eng_harness.ports import RunClass, ToolInfo

    HOLDER = (
        "import sys\nfrom pathlib import Path\nfrom eng_harness._runlock import RunLock\n"
        "RunLock(Path(sys.argv[1])).acquire()\nprint('held', flush=True)\nsys.stdin.read()\n"
    )
    PROBE = (
        "import sys\nfrom pathlib import Path\nfrom eng_harness._runlock import RunLock\n"
        "from eng_harness.errors import RunLocked\n"
        "try:\n    RunLock(Path(sys.argv[1])).acquire()\nexcept RunLocked as exc:\n    print(exc.code.value)\n"
        "else:\n    print('acquired')\n"
    )

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
        """The fake host; before each call it asks a second process for the run lock of the only run under way."""

        def __init__(self, ids: SeededIdSource, clock: FixedClock, runs_dir: Path) -> None:
            """Serve the tool `write_b`; `runs_dir` holds the one run being watched."""
            tool = ToolInfo(name="write_b", effect="write", action="plain", host_key="csi", model_param="model")
            super().__init__([tool], ids, clock)
            self.sightings: list[tuple[bool, str]] = []
            self._runs_dir = runs_dir

        async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> ENVELOPE:
            """Record whether the run is locked and what a second process got from the lock, then call."""
            (run_dir,) = self._runs_dir.iterdir()
            probe = await spawn(PROBE, run_dir)
            async with asyncio.timeout(60):
                answer, _ = await probe.communicate()
            self.sightings.append((is_locked(run_dir), answer.decode().strip()))
            return await super().call(tool, args, op_id=op_id, model=model)

    @pytest.mark.windows
    def test_engine_holds_the_run_lock_against_another_process(tmp_path: Path) -> None:
        clock = FixedClock(1_767_225_600_000, 1)
        ids = SeededIdSource(b"harness", clock)
        workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
        host = WatchingHost(ids, clock, workspace.root / "runs")
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
        asked = RunRequest(workflow="one_write", input={}, basis_ref="res_" + "0" * 26)
        assert asyncio.run(engine.start(asked)).status is RunStatus.COMPLETED
        assert host.sightings == [(True, "RUN_LOCKED")]
        (run_dir,) = (workspace.root / "runs").iterdir()
        assert not is_locked(run_dir)  # released when the run returned

    @pytest.mark.windows
    def test_killed_holder_releases_the_run_lock(tmp_path: Path) -> None:
        async def scenario() -> None:
            holder = await spawn(HOLDER, tmp_path)
            try:
                assert holder.stdout is not None
                async with asyncio.timeout(60):
                    assert (await holder.stdout.readline()).strip() == b"held"
                assert is_locked(tmp_path)
                with pytest.raises(RunLocked) as refused:
                    RunLock(tmp_path).acquire()
                assert refused.value.code is HarnessCode.RUN_LOCKED
                holder.kill()  # the holder dies without releasing anything
                await holder.wait()
            finally:
                if holder.returncode is None:
                    holder.kill()
                    await holder.wait()
            assert not is_locked(tmp_path)
            again = RunLock(tmp_path)  # the next engine opens the run
            again.acquire()
            again.release()

        asyncio.run(scenario())
