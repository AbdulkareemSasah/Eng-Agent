"""MCP session over the harness process transport (plan 0002 T5; spec 0002 AC8, AC11, AC12, sections 4.3.2 to 4.3.5).

The synthetic Sasaah CSI fake runs as a real process started by the harness launcher. A second, tiny test-double
server (below) serves a paginated tool list, records its arguments and can ignore the end of its standard input.
"""

import json
import os
import signal
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ErrorCode

from eng_harness.errors import ToolFailed
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._launcher import JobPolicy, LaunchedProcess, LaunchSpec, PosixLauncher
from eng_harness.servers._procinfo import PosixProcessInspector

ConfigFactory = Callable[..., ServersConfig]


class RecordingLauncher:
    """The POSIX launcher that remembers every process it started, in order."""

    def __init__(self) -> None:
        self.started: list[LaunchedProcess] = []
        self.specs: list[LaunchSpec] = []
        self._inner = PosixLauncher()

    def start(self, spec: LaunchSpec) -> LaunchedProcess:
        """Start `spec` through the POSIX launcher and record the result."""
        process = self._inner.start(spec)
        self.started.append(process)
        self.specs.append(spec)
        return process


PAGED = """
import json, os, sys, time
import anyio
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

json.dump(sys.argv[1:], open("argv.json", "w"))
NAMES = ["tool_%d" % n for n in range(5)]


async def on_list(ctx, params):
    start = int(params.cursor) if params and params.cursor else 0
    tools = [types.Tool(name=n, input_schema={"type": "object"}) for n in NAMES[start : start + 2]]
    more = str(start + 2) if start + 2 < len(NAMES) else None
    return types.ListToolsResult(tools=tools, next_cursor=more)


async def on_call(ctx, params):
    return types.CallToolResult(content=[types.TextContent(type="text", text="{}")])


async def main():
    server = Server("paged", on_list_tools=on_list, on_call_tool=on_call)
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())
    if os.environ.get("IGNORE_EOF"):
        time.sleep(120)


anyio.run(main)
"""


def _paged(tmp_path: Path) -> Path:
    path = tmp_path / "paged_server.py"
    path.write_text(PAGED)
    return path


def _run(
    tmp_path: Path, config: ServersConfig, launcher: RecordingLauncher, body: Callable[[ServerManager], Any]
) -> None:
    async def scenario() -> None:
        async with ServerManager(config, tmp_path / "run", launcher=launcher) as manager:
            await body(manager)

    anyio.run(scenario)


def _text(result: Any) -> dict[str, Any]:
    assert len(result.content) == 1
    body: dict[str, Any] = json.loads(result.content[0].text)
    return body


def _arm(control: Path, *faults: dict[str, Any]) -> None:
    control.write_text(json.dumps({"faults": list(faults), "seed": {}}))


@pytest.fixture
def launcher() -> RecordingLauncher:
    """A recording POSIX launcher."""
    return RecordingLauncher()


@pytest.fixture
def host(tmp_path: Path) -> Iterator[LaunchedProcess]:
    """A host-program stand-in in a session of its own, as a host started by the Sasaah server is."""
    spec = LaunchSpec(
        argv=[sys.executable, "-c", "import time; time.sleep(120)"],
        env=dict(os.environ),
        cwd=tmp_path,
        stderr_path=tmp_path / "host.stderr.log",
        job=JobPolicy.SERVER,
    )
    process = PosixLauncher().start(spec)
    yield process
    process.terminate_job()
    process.wait(10)
    process.close()


def test_start_list_call(tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher) -> None:
    schemas = json.loads((Path(__file__).resolve().parents[2] / "fakes" / "sasaah_csi" / "schemas.json").read_text())
    expected = {tool["name"] for tool in schemas["tools"]}

    async def body(manager: ServerManager) -> None:
        tools = await manager.list_tools("csi", "main")
        assert {tool.name for tool in tools} == expected
        info = manager.server_info("csi", "main")
        assert info is not None
        assert info.name == "sasaah-csi-fake"
        result = await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)
        assert result.is_error is False
        assert _text(result)["read_only"] is False

    _run(tmp_path, make_config(), launcher, body)
    assert len(launcher.started) == 1


def test_list_reads_every_page(tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher) -> None:
    async def body(manager: ServerManager) -> None:
        assert [t.name for t in await manager.list_tools("csi", "main")] == [f"tool_{n}" for n in range(5)]

    _run(tmp_path, make_config(_paged(tmp_path)), launcher, body)


def test_launch_arguments(tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher) -> None:
    async def body(manager: ServerManager) -> None:
        await manager.list_tools("csi", "long")

    config = make_config(_paged(tmp_path), call_timeout_s=42)
    _run(tmp_path, config, launcher, body)
    run_dir = tmp_path / "run"
    argv = json.loads((run_dir / "argv.json").read_text())
    audit = run_dir / "servers" / "csi-long-audit.jsonl"
    assert argv == ["--call-timeout-sec", "42", "--audit-log", str(audit)]
    assert launcher.specs[0].stderr_path == run_dir / "servers" / "csi-long.stderr.log"
    assert launcher.specs[0].cwd == run_dir
    assert "SASAAH_CSI_FAKE_CONTROL" in launcher.specs[0].env


def test_crash_restart(
    tmp_path: Path,
    make_config: ConfigFactory,
    launcher: RecordingLauncher,
    control: Path,
    host: LaunchedProcess,
) -> None:
    async def body(manager: ServerManager) -> None:
        await manager.call("csi", "main", "csi_attach", {"pid": host.pid, "product": "ETABS"}, CallEffect.WRITE)
        manager.bind_instance("csi", pid=host.pid, product="ETABS")
        before = manager.session_epoch("csi")

        _arm(control, {"fault": "crash_during_call", "tool": "csi_list_points"})
        with pytest.raises(ToolFailed) as read_failure:
            await manager.call("csi", "main", "csi_list_points", {}, CallEffect.READ)
        assert read_failure.value.detail.code is ErrorCode.HOST_NOT_CONNECTED
        assert manager.session_epoch("csi") == before + 1

        # The next call restarts the role and re-attaches to the bound instance by process id.
        status = _text(await manager.call("csi", "main", "csi_status", {}, CallEffect.READ))
        assert status["current_target"] == {"product": "ETABS", "pid": host.pid, "launched": False}
        assert manager.session_epoch("csi") == before + 2
        assert len(launcher.started) == 2

    _run(tmp_path, make_config(max_restarts=2), launcher, body)


def test_crash_during_write_is_unknown_outcome(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher, control: Path
) -> None:
    async def body(manager: ServerManager) -> None:
        await manager.call("csi", "main", "csi_attach", {"pid": 4242, "product": "ETABS"}, CallEffect.WRITE)
        _arm(control, {"fault": "crash_during_call", "tool": "csi_add_point"})
        with pytest.raises(ToolFailed) as failure:
            await manager.call("csi", "main", "csi_add_point", {"x": 1, "y": 2, "z": 3}, CallEffect.WRITE)
        assert failure.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME

    _run(tmp_path, make_config(), launcher, body)


def test_restart_limit(tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher, control: Path) -> None:
    async def crash(manager: ServerManager) -> None:
        _arm(control, {"fault": "crash_during_call", "tool": "csi_list_points"})
        with pytest.raises(ToolFailed):
            await manager.call("csi", "main", "csi_list_points", {}, CallEffect.READ)

    async def body(manager: ServerManager) -> None:
        await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)
        await crash(manager)
        await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)  # the one restart
        await crash(manager)
        with pytest.raises(ToolFailed) as failure:  # beyond max_restarts_per_run: nothing is started, nothing sent
            await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)
        assert failure.value.detail.code is ErrorCode.HOST_NOT_CONNECTED
        assert len(launcher.started) == 2

    _run(tmp_path, make_config(max_restarts=1), launcher, body)


def test_crash_between_calls_restarts_before_next_call(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher
) -> None:
    async def body(manager: ServerManager) -> None:
        await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)
        before = manager.session_epoch("csi")
        os.kill(launcher.started[0].pid, signal.SIGKILL)
        assert launcher.started[0].wait(10) is not None
        result = await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)
        assert result.is_error is False
        assert manager.session_epoch("csi") == before + 2

    _run(tmp_path, make_config(), launcher, body)


def test_backstop_timeout_restarts_role(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher, control: Path
) -> None:
    async def body(manager: ServerManager) -> None:
        await manager.call("csi", "main", "csi_attach", {"pid": 4242, "product": "ETABS"}, CallEffect.WRITE)
        before = manager.session_epoch("csi")
        _arm(control, {"fault": "slow_analysis", "tool": "csi_run_analysis", "seconds": 30})
        with pytest.raises(ToolFailed) as failure:  # backstop = 1 s call timeout + 1 s grace
            await manager.call("csi", "main", "csi_run_analysis", {"confirm": True}, CallEffect.WRITE)
        assert failure.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
        assert manager.session_epoch("csi") == before + 1
        await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)  # a new process serves it
        assert len(launcher.started) == 2

    _run(tmp_path, make_config(call_timeout_s=1, client_grace_s=1), launcher, body)


def test_unknown_server_and_role(tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher) -> None:
    async def body(manager: ServerManager) -> None:
        for server, role in (("nope", "main"), ("csi", "nope")):
            with pytest.raises(KeyError):
                await manager.call(server, role, "csi_status", {}, CallEffect.READ)

    _run(tmp_path, make_config(), launcher, body)


def test_shutdown_leaves_hosts(
    tmp_path: Path,
    make_config: ConfigFactory,
    launcher: RecordingLauncher,
    host: LaunchedProcess,
) -> None:
    inspector = PosixProcessInspector()
    host_identity = inspector.identity(host.pid)
    assert host_identity is not None

    async def body(manager: ServerManager) -> None:
        await manager.call("csi", "main", "csi_attach", {"pid": host.pid, "product": "ETABS"}, CallEffect.WRITE)
        await manager.call("csi", "long", "csi_status", {}, CallEffect.READ)

    _run(tmp_path, make_config(), launcher, body)
    assert len(launcher.started) == 2
    for process in launcher.started:
        assert process.wait(10) == 0  # each server ended on its own when its session closed
        assert process.job_members() == []
    assert inspector.alive(host_identity)  # no host instance is ended by the shutdown


def test_shutdown_terminates_job_after_grace(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher
) -> None:
    async def body(manager: ServerManager) -> None:
        await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)

    config = make_config(_paged(tmp_path), shutdown_grace_s=1, env={"IGNORE_EOF": "1"})
    started = time.monotonic()
    _run(tmp_path, config, launcher, body)
    assert time.monotonic() - started >= 1.0  # the grace time was waited for
    process = launcher.started[0]
    assert process.wait(10) == -signal.SIGKILL
    assert process.job_members() == []
