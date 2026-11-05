"""MCP session over the harness process transport (plan 0002 T5; spec 0002 AC8, AC11, AC12, sections 4.3.2 to 4.3.5).

The synthetic Sasaah CSI fake runs as a real process started by the harness launcher. A second, tiny test-double
server (below) serves a paginated tool list, records its arguments and, by environment variables, can ignore the end
of its standard input, exit before the handshake, never answer the handshake, or fail or stall `csi_attach`.
"""

import json
import os
import signal
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ErrorCode

from eng_harness.adapters.csi import csi_allowlist
from eng_harness.errors import ToolFailed
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._buildcheck import BuildExpectation
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
if os.environ.get("EXIT_FIRST") and not os.path.exists("started.marker"):
    open("started.marker", "w").close()
    sys.exit(3)  # the first start ends before the handshake
if os.environ.get("NO_HANDSHAKE"):
    time.sleep(120)
NAMES = ["tool_%d" % n for n in range(5)]


async def on_list(ctx, params):
    start = int(params.cursor) if params and params.cursor else 0
    tools = [types.Tool(name=n, input_schema={"type": "object"}) for n in NAMES[start : start + 2]]
    more = str(start + 2) if start + 2 < len(NAMES) else None
    return types.ListToolsResult(tools=tools, next_cursor=more)


async def on_call(ctx, params):
    if params.name == "csi_attach":
        mode = os.environ.get("ATTACH")
        if mode == "stall":
            await anyio.sleep(120)
        if mode == "raise":
            raise RuntimeError("attach refused")
        if mode == "error":
            return types.CallToolResult(content=[types.TextContent(type="text", text="{}")], is_error=True)
    return types.CallToolResult(content=[types.TextContent(type="text", text="{}")])


async def main():
    server = Server("paged", on_list_tools=on_list, on_call_tool=on_call)
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())
    if os.environ.get("IGNORE_EOF"):
        open("eof.marker", "w").close()  # the end of the standard input reached the server
        time.sleep(120)


anyio.run(main)
"""


def _paged(tmp_path: Path) -> Path:
    path = tmp_path / "paged_server.py"
    path.write_text(PAGED)
    return path


def _run(
    tmp_path: Path,
    config: ServersConfig,
    launcher: RecordingLauncher,
    body: Callable[[ServerManager], Any],
    check: Mapping[str, BuildExpectation] | None = None,
) -> None:
    async def scenario() -> None:
        async with ServerManager(config, tmp_path / "run", launcher=launcher, check=check) as manager:
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
        # The backstop (2 s call timeout + 1 s grace) is the behavior under test and the fake sleeps 30 s, so a loaded
        # container can only make this test slower, not wrong; the assertions do not read a clock.
        with pytest.raises(ToolFailed) as failure:
            await manager.call("csi", "main", "csi_run_analysis", {"confirm": True}, CallEffect.WRITE)
        assert failure.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
        assert manager.session_epoch("csi") == before + 1
        await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)  # a new process serves it
        assert len(launcher.started) == 2

    _run(tmp_path, make_config(call_timeout_s=2, client_grace_s=1), launcher, body)


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
    _run(tmp_path, config, launcher, body)
    # Order of events, not elapsed time: the server saw the end of its input (the session closed first), ignored it, and
    # only then did the manager end the job.
    assert (tmp_path / "run" / "eof.marker").exists()
    process = launcher.started[0]
    assert process.wait(10) == -signal.SIGKILL
    assert process.job_members() == []


def _fails_as_not_connected(manager: ServerManager) -> Callable[[], Any]:
    async def attempt() -> None:
        with pytest.raises(ToolFailed) as failure:
            await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)
        assert failure.value.detail.code is ErrorCode.HOST_NOT_CONNECTED

    return attempt


def test_server_exiting_before_handshake_is_not_connected(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher
) -> None:
    async def body(manager: ServerManager) -> None:
        await _fails_as_not_connected(manager)()  # a typed error, not an ExceptionGroup of the task group
        assert manager.server_info("csi", "main") is None
        result = await manager.call("csi", "main", "tool_0", {}, CallEffect.READ)  # the manager stays usable
        assert result.is_error is False
        assert len(launcher.started) == 2

    _run(tmp_path, make_config(_paged(tmp_path), env={"EXIT_FIRST": "1"}), launcher, body)


def test_failing_start_uses_up_a_restart(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher
) -> None:
    async def body(manager: ServerManager) -> None:
        attempt = _fails_as_not_connected(manager)
        await attempt()  # the start
        await attempt()  # beyond max_restarts_per_run: refused, nothing started

    config = make_config(_paged(tmp_path), max_restarts=0, env={"EXIT_FIRST": "1"})
    _run(tmp_path, config, launcher, body)
    assert len(launcher.started) == 1  # the second call hit the restart limit and started nothing


def test_missing_program_is_not_connected(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher
) -> None:
    async def body(manager: ServerManager) -> None:
        await _fails_as_not_connected(manager)()
        assert launcher.started == []

    _run(tmp_path, make_config(command=str(tmp_path / "no-such-program")), launcher, body)


def test_handshake_timeout_is_not_connected(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher
) -> None:
    async def body(manager: ServerManager) -> None:
        await _fails_as_not_connected(manager)()  # the server never answers; the backstop (4 s) bounds the handshake
        stuck = launcher.started[0]
        assert stuck.wait(10) is not None  # the stuck process was ended, whatever the load delays the end by
        assert stuck.job_members() == []

    # The backstop is the behavior under test and the server never answers, so a larger bound only costs time (P-54).
    config = make_config(_paged(tmp_path), call_timeout_s=3, client_grace_s=1, env={"NO_HANDSHAKE": "1"})
    _run(tmp_path, config, launcher, body)


@pytest.mark.parametrize(
    ("mode", "call_timeout_s", "client_grace_s"),
    # The backstop bounds the handshake as well as the attach. An attach that fails at once leaves the backstop
    # unused, so it is generous and a slow start of the server cannot let the handshake time out first. Only the
    # stalled attach waits for the backstop: 10 s, about five times what a loaded start of the server took (P-54).
    [("error", 30, 30), ("raise", 30, 30), ("stall", 8, 2)],
)
def test_attach_failure_marks_role_down(
    tmp_path: Path,
    make_config: ConfigFactory,
    launcher: RecordingLauncher,
    mode: str,
    call_timeout_s: int,
    client_grace_s: int,
) -> None:
    async def body(manager: ServerManager) -> None:
        manager.bind_instance("csi", pid=4242, product="ETABS")
        before = manager.session_epoch("csi")
        await _fails_as_not_connected(manager)()
        assert manager.server_info("csi", "main") is None  # the role is down, not half-attached
        assert manager.session_epoch("csi") == before + 1
        assert launcher.started[0].job_members() == []

    config = make_config(
        _paged(tmp_path), call_timeout_s=call_timeout_s, client_grace_s=client_grace_s, env={"ATTACH": mode}
    )
    _run(tmp_path, config, launcher, body)


def test_launch_arguments_without_audit_log(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher
) -> None:
    async def body(manager: ServerManager) -> None:
        await manager.list_tools("csi", "main")

    _run(tmp_path, make_config(_paged(tmp_path), call_timeout_s=42, audit_log=False), launcher, body)
    assert json.loads((tmp_path / "run" / "argv.json").read_text()) == ["--call-timeout-sec", "42"]


def _checks(*, wrong_fingerprint: bool = False) -> dict[str, BuildExpectation]:
    """The build check of the CSI allowlist for server `csi`; the fingerprint can be made wrong on purpose."""
    expected = csi_allowlist().build_expectation()
    return {"csi": replace(expected, tool_fingerprint="0" * 64) if wrong_fingerprint else expected}


def test_restart_repeats_build_check(
    tmp_path: Path,
    make_config: ConfigFactory,
    launcher: RecordingLauncher,
    control: Path,
    host: LaunchedProcess,
) -> None:
    """AC11: a role's first start runs no check; its restart runs it before the re-attach (a wrong pin shows it)."""

    async def body(manager: ServerManager) -> None:
        # The first start is not checked, although the pinned fingerprint is wrong.
        await manager.call("csi", "main", "csi_attach", {"pid": host.pid, "product": "ETABS"}, CallEffect.WRITE)
        manager.bind_instance("csi", pid=host.pid, product="ETABS")
        _arm(control, {"fault": "crash_during_call", "tool": "csi_list_points"})
        with pytest.raises(ToolFailed):
            await manager.call("csi", "main", "csi_list_points", {}, CallEffect.READ)
        with pytest.raises(ToolFailed) as failure:  # the restart finds the build wrong and does not re-attach
            await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)
        assert failure.value.detail.code is ErrorCode.HOST_NOT_CONNECTED
        assert "build check" in failure.value.detail.message
        assert "fingerprint" in failure.value.detail.message
        assert manager.server_info("csi", "main") is None  # the role is down
        assert len(launcher.started) == 2
        assert launcher.started[1].job_members() == []

    _run(tmp_path, make_config(max_restarts=2), launcher, body, _checks(wrong_fingerprint=True))


def test_restart_with_matching_build_reattaches(
    tmp_path: Path,
    make_config: ConfigFactory,
    launcher: RecordingLauncher,
    control: Path,
    host: LaunchedProcess,
) -> None:
    async def body(manager: ServerManager) -> None:
        await manager.call("csi", "main", "csi_attach", {"pid": host.pid, "product": "ETABS"}, CallEffect.WRITE)
        manager.bind_instance("csi", pid=host.pid, product="ETABS")
        _arm(control, {"fault": "crash_during_call", "tool": "csi_list_points"})
        with pytest.raises(ToolFailed):
            await manager.call("csi", "main", "csi_list_points", {}, CallEffect.READ)
        status = _text(await manager.call("csi", "main", "csi_status", {}, CallEffect.READ))
        assert status["current_target"] == {"product": "ETABS", "pid": host.pid, "launched": False}
        assert len(launcher.started) == 2

    _run(tmp_path, make_config(max_restarts=2), launcher, body, _checks())


def test_preflight_over_the_csi_fake(tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher) -> None:
    config = make_config()
    commit = config.servers["csi"].build.sasaah_commit
    exe = config.servers["csi"].build.exe_sha256

    async def body(manager: ServerManager) -> None:
        [check] = await manager.preflight({"csi": commit})
        assert check.reason is None
        assert check.ok is True
        assert (check.server, check.build, check.min_build) == ("csi", f"{commit[:12]}+{exe[:12]}", commit)
        assert check.fingerprint == check.expected_fingerprint == csi_allowlist().tool_fingerprint

    _run(tmp_path, config, launcher, body, _checks())


def test_preflight_reports_each_failure(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher
) -> None:
    async def body(manager: ServerManager) -> None:
        [check] = await manager.preflight({"csi": "e" * 40})  # a minimum that is not a tested build
        assert check.ok is False
        assert check.reason is not None
        assert "minimum" in check.reason

    _run(tmp_path, make_config(), launcher, body, _checks())


def test_preflight_without_a_check_is_not_ok(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher
) -> None:
    async def body(manager: ServerManager) -> None:
        [check] = await manager.preflight({})
        assert check.ok is False
        assert check.reason is not None
        assert "no build check" in check.reason
        assert launcher.started == []  # nothing is started to say so

    _run(tmp_path, make_config(), launcher, body)


def test_preflight_wrong_fingerprint(tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher) -> None:
    async def body(manager: ServerManager) -> None:
        [check] = await manager.preflight({})
        assert check.ok is False
        assert check.reason is not None
        assert "fingerprint" in check.reason
        assert check.fingerprint != check.expected_fingerprint

    _run(tmp_path, make_config(), launcher, body, _checks(wrong_fingerprint=True))


def test_preflight_of_a_server_that_cannot_start(
    tmp_path: Path, make_config: ConfigFactory, launcher: RecordingLauncher
) -> None:
    async def body(manager: ServerManager) -> None:
        [check] = await manager.preflight({})
        assert check.ok is False
        assert check.reason is not None
        assert "cannot start" in check.reason

    _run(tmp_path, make_config(command=str(tmp_path / "no-such-program")), launcher, body, _checks())
