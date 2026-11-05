"""Process guard (plan 0002 T7; spec 0002 AC15, section 4.4.2).

The Sasaah CSI fake runs as a real server process and answers `csi_launch`, `csi_status` and `csi_exit` as the S-12
inventory describes (its instance has the fixed pid 4242). The host programs themselves are an in-memory
`ProcessInspector`, so what the guard ends is observable without starting anything.
"""

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode
from mcp import types

from eng_harness.errors import ToolFailed
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._guard import ProcessGuard, StartedInstance
from eng_harness.servers._procinfo import ProcessIdentity

ConfigFactory = Callable[..., ServersConfig]
FAKE_PID = 4242  # the pid the CSI fake gives every instance it launches
ETABS = "ETABS.exe"


class FakeInspector:
    """Running processes by pid; `terminate` removes a matching one and remembers it."""

    def __init__(self) -> None:
        self.running: dict[int, ProcessIdentity] = {}
        self.kids: dict[int, list[ProcessIdentity]] = {}
        self.terminated: list[ProcessIdentity] = []

    def identity(self, pid: int) -> ProcessIdentity | None:
        """The running process with `pid`."""
        return self.running.get(pid)

    def alive(self, identity: ProcessIdentity) -> bool:
        """True when pid and start time match a running process."""
        found = self.running.get(identity.pid)
        return found is not None and found.started_at == identity.started_at

    def children(self, pid: int) -> list[ProcessIdentity]:
        """The configured children of `pid`."""
        return list(self.kids.get(pid, []))

    def snapshot(self, exe_names: list[str]) -> list[ProcessIdentity]:
        """Running processes whose image is in `exe_names`."""
        return [i for i in self.running.values() if i.exe_name in exe_names]

    def terminate(self, identity: ProcessIdentity) -> bool:
        """End a matching process."""
        if not self.alive(identity):
            return False
        del self.running[identity.pid]
        self.terminated.append(identity)
        return True


class Recording:
    """The `ServerManager` with a record of the tools sent through it."""

    def __init__(self, manager: ServerManager) -> None:
        self.manager = manager
        self.tools: list[str] = []

    def role_session(self, server: str, role: str) -> int:
        """Session counter of the role."""
        return self.manager.role_session(server, role)

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        """Record and forward the call."""
        self.tools.append(tool)
        return await self.manager.call(server, role, tool, arguments, effect)


def _body(result: types.CallToolResult) -> dict[str, Any]:
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    body: dict[str, Any] = json.loads(block.text)
    return body


def _arm(control: Path, *faults: dict[str, Any]) -> None:
    control.write_text(json.dumps({"faults": list(faults), "seed": {}}))


def _run(
    tmp_path: Path, config: ServersConfig, body: Callable[[ServerManager, ProcessGuard, FakeInspector], Any]
) -> None:
    inspector = FakeInspector()
    guard = ProcessGuard(inspector, tmp_path / "run", host_exes=[ETABS])

    async def scenario() -> None:
        async with ServerManager(config, tmp_path / "run", helpers=guard) as manager:
            await body(manager, guard, inspector)

    anyio.run(scenario)


async def _launch(
    manager: ServerManager, guard: ProcessGuard, inspector: FakeInspector, *, visible: bool
) -> StartedInstance:
    """`csi_launch` as the adapter does it: snapshot, call, identify, record the launching role's session."""
    before = guard.snapshot()
    inspector.running[FAKE_PID] = ProcessIdentity(FAKE_PID, "t1", ETABS)
    reply = await manager.call("csi", "main", "csi_launch", {"product": "ETABS", "visible": visible}, CallEffect.WRITE)
    assert _body(reply)["pid"] == FAKE_PID
    return guard.record_launch(manager, guard.identify_launch(before, named_pid=FAKE_PID), visible=visible)


def test_close_only_started(tmp_path: Path, make_config: ConfigFactory) -> None:
    async def body(manager: ServerManager, guard: ProcessGuard, inspector: FakeInspector) -> None:
        started = await _launch(manager, guard, inspector, visible=False)
        inspector.running[5000] = ProcessIdentity(5000, "t9", ETABS)  # an instance the run attached to: never passed
        reused = StartedInstance(pid=777, started_at="old", program=ETABS, visible=False)
        inspector.running[777] = ProcessIdentity(777, "new", ETABS)  # same pid, another process
        recording = Recording(manager)

        left = await guard.close_started(recording, [reused, started])

        assert left == []
        assert recording.tools == ["csi_status", "csi_exit"]  # the owned, current target is exited gracefully
        assert inspector.terminated == []
        assert set(inspector.running) == {FAKE_PID, 777, 5000}  # nothing else was touched; 777 did not match
        status = await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)
        assert _body(status)["current_target"] is None

    _run(tmp_path, make_config(), body)


def test_close_after_timeout_falls_back(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    async def body(manager: ServerManager, guard: ProcessGuard, inspector: FakeInspector) -> None:
        started = await _launch(manager, guard, inspector, visible=False)
        before = manager.role_session("csi", "main")
        _arm(control, {"fault": "timeout_before_apply", "tool": "csi_list_points"})
        reply = await manager.call("csi", "main", "csi_list_points", {}, CallEffect.READ)  # a read times out
        assert _body(reply)["code"] == "timeout"
        assert manager.role_session("csi", "main") == before + 1
        recording = Recording(manager)

        left = await guard.close_started(recording, [started])

        assert left == []
        assert recording.tools == []  # launch ownership is lost: not even csi_status is sent
        assert inspector.terminated == [ProcessIdentity(FAKE_PID, "t1", ETABS)]

    _run(tmp_path, make_config(), body)


def test_visible_instance_left_open(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    async def body(manager: ServerManager, guard: ProcessGuard, inspector: FakeInspector) -> None:
        started = await _launch(manager, guard, inspector, visible=True)
        manager.invalidate_session("csi", "main")  # a reconnect ends launch ownership too
        recording = Recording(manager)

        for _ in range(2):  # idempotent
            assert await guard.close_started(recording, [started]) == [started]

        assert recording.tools == []
        assert inspector.terminated == []
        listed = json.loads((tmp_path / "run" / "hosts" / "left_open.json").read_text())
        assert listed == [{"pid": FAKE_PID, "started_at": "t1", "program": ETABS}]

    _run(tmp_path, make_config(), body)


def test_other_current_target_falls_back(tmp_path: Path, make_config: ConfigFactory) -> None:
    async def body(manager: ServerManager, guard: ProcessGuard, inspector: FakeInspector) -> None:
        started = await _launch(manager, guard, inspector, visible=False)
        await manager.call("csi", "main", "csi_attach", {"pid": 9999, "product": "ETABS"}, CallEffect.WRITE)
        recording = Recording(manager)

        await guard.close_started(recording, [started])
        await guard.close_started(recording, [started])  # the instance is gone now: ignored

        assert recording.tools == ["csi_status"]  # the current target is another instance: no csi_exit
        assert inspector.terminated == [ProcessIdentity(FAKE_PID, "t1", ETABS)]

    _run(tmp_path, make_config(), body)


def test_exit_refused_falls_back(tmp_path: Path, make_config: ConfigFactory) -> None:
    async def body(manager: ServerManager, guard: ProcessGuard, inspector: FakeInspector) -> None:
        started = await _launch(manager, guard, inspector, visible=False)
        # A re-attachment the guard was not told about: the server answers not_launched_by_server to csi_exit.
        await manager.call("csi", "main", "csi_attach", {"pid": FAKE_PID, "product": "ETABS"}, CallEffect.WRITE)
        recording = Recording(manager)

        await guard.close_started(recording, [started])

        assert recording.tools == ["csi_status", "csi_exit"]
        assert inspector.terminated == [ProcessIdentity(FAKE_PID, "t1", ETABS)]

    _run(tmp_path, make_config(), body)


def test_crash_ends_launch_ownership(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    async def body(manager: ServerManager, guard: ProcessGuard, inspector: FakeInspector) -> None:
        started = await _launch(manager, guard, inspector, visible=False)
        before = manager.role_session("csi", "main")
        _arm(control, {"fault": "crash_during_call", "tool": "csi_list_points"})
        with pytest.raises(ToolFailed):
            await manager.call("csi", "main", "csi_list_points", {}, CallEffect.READ)
        assert manager.role_session("csi", "main") == before + 1
        recording = Recording(manager)

        await guard.close_started(recording, [started])

        assert recording.tools == []
        assert inspector.terminated == [ProcessIdentity(FAKE_PID, "t1", ETABS)]

    _run(tmp_path, make_config(), body)


def test_session_counter_is_per_role(tmp_path: Path, make_config: ConfigFactory) -> None:
    async def body(manager: ServerManager, guard: ProcessGuard, inspector: FakeInspector) -> None:
        await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)
        await manager.call("csi", "long", "csi_status", {}, CallEffect.READ)
        manager.invalidate_session("csi", "main")
        assert (manager.role_session("csi", "main"), manager.role_session("csi", "long")) == (1, 0)

    _run(tmp_path, make_config(), body)


@pytest.mark.parametrize("others", [[], [("ETABS.exe", 8)], [("ETABS.exe", 8), ("ETABS.exe", 9)]])
def test_identify_launch_needs_exactly_the_named_new_instance(others: list[tuple[str, int]], tmp_path: Path) -> None:
    inspector = FakeInspector()
    guard = ProcessGuard(inspector, tmp_path, host_exes=[ETABS])
    old = ProcessIdentity(7, "t0", ETABS)
    inspector.running[7] = old
    before = guard.snapshot()
    for name, pid in others:
        inspector.running[pid] = ProcessIdentity(pid, "t2", name)
    # Zero, or several, candidates are refused; so is one that is not the pid the reply names.
    for named in (7, 99):
        with pytest.raises(ContractError, match="launched instance not identified") as refused:
            guard.identify_launch(before, named_pid=named)
        assert refused.value.detail.code is ErrorCode.CONFLICT
    if len(others) == 1:
        assert guard.identify_launch(before, named_pid=8) == ProcessIdentity(8, "t2", ETABS)
    else:
        with pytest.raises(ContractError, match="not identified"):
            guard.identify_launch(before, named_pid=8)


class AnyPidInspector(FakeInspector):
    """Every job member has the same two children: a helper process and a host program."""

    def children(self, pid: int) -> list[ProcessIdentity]:
        """The helper and the host."""
        return [ProcessIdentity(300, "h1", "helper.exe"), ProcessIdentity(301, "h2", ETABS)]


def test_helpers_are_terminated_at_server_stop(tmp_path: Path, make_config: ConfigFactory) -> None:
    inspector = AnyPidInspector()
    helper, host = inspector.children(0)
    inspector.running.update({300: helper, 301: host})
    guard = ProcessGuard(inspector, tmp_path / "run", host_exes=[ETABS])

    async def scenario() -> None:
        async with ServerManager(make_config(), tmp_path / "run", helpers=guard) as manager:
            await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)
            assert inspector.terminated == []  # recorded after the call, ended only when the server stops

    anyio.run(scenario)
    assert inspector.terminated == [helper]  # the host program is not a helper
    assert 301 in inspector.running


class CaseInspector(FakeInspector):
    """Every job member has one child whose image name differs from the configured host name only in case."""

    def children(self, pid: int) -> list[ProcessIdentity]:
        """The host program with another letter case."""
        return [ProcessIdentity(301, "h2", ETABS.lower())]


def test_host_name_is_compared_without_case(tmp_path: Path, make_config: ConfigFactory) -> None:
    inspector = CaseInspector()
    host = inspector.children(0)[0]
    inspector.running[301] = host
    guard = ProcessGuard(inspector, tmp_path / "run", host_exes=[ETABS])

    async def scenario() -> None:
        async with ServerManager(make_config(), tmp_path / "run", helpers=guard) as manager:
            await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)

    anyio.run(scenario)
    assert inspector.terminated == []  # a host instance is closed only by `close_started`
    assert 301 in inspector.running


class BrokenChildren(FakeInspector):
    """An inspector whose child enumeration fails like a failed Win32 call."""

    def children(self, pid: int) -> list[ProcessIdentity]:
        """Always fail."""
        raise OSError("enumeration failed")


def test_failed_helper_observation_does_not_break_calls_or_stop(tmp_path: Path, make_config: ConfigFactory) -> None:
    guard = ProcessGuard(BrokenChildren(), tmp_path / "run", host_exes=[ETABS])
    stopped: list[bool] = []

    async def scenario() -> None:
        async with ServerManager(make_config(), tmp_path / "run", helpers=guard) as manager:
            reply = await manager.call("csi", "main", "csi_status", {}, CallEffect.READ)
            assert not reply.is_error
            stopped.append(True)

    anyio.run(scenario)
    assert stopped == [True]


class DeniedInspector(FakeInspector):
    """Ending the first process is refused (an elevated host)."""

    def terminate(self, identity: ProcessIdentity) -> bool:
        """Refuse pid 100, end the others."""
        if identity.pid == 100:
            raise PermissionError("access denied")
        return super().terminate(identity)


def test_failed_terminate_is_listed_and_the_rest_is_closed(tmp_path: Path, make_config: ConfigFactory) -> None:
    inspector = DeniedInspector()
    guard = ProcessGuard(inspector, tmp_path / "run", host_exes=[ETABS])
    first = StartedInstance(pid=100, started_at="a", program=ETABS, visible=False)
    second = StartedInstance(pid=200, started_at="b", program=ETABS, visible=False)
    inspector.running.update({100: first.identity, 200: second.identity})

    async def scenario() -> None:
        async with ServerManager(make_config(), tmp_path / "run", helpers=guard) as manager:
            left = await guard.close_started(Recording(manager), [first, second])
            assert left == [first]

    anyio.run(scenario)
    assert inspector.terminated == [second.identity]
    listed = json.loads((tmp_path / "run" / "hosts" / "left_open.json").read_text())
    assert listed == [{"pid": 100, "started_at": "a", "program": ETABS}]


def test_graceful_exit_clears_an_earlier_left_open(tmp_path: Path, make_config: ConfigFactory) -> None:
    async def body(manager: ServerManager, guard: ProcessGuard, inspector: FakeInspector) -> None:
        started = await _launch(manager, guard, inspector, visible=True)
        await manager.call("csi", "main", "csi_attach", {"pid": 9999, "product": "ETABS"}, CallEffect.WRITE)
        recording = Recording(manager)
        assert await guard.close_started(recording, [started]) == [started]  # another target is current
        listing = tmp_path / "run" / "hosts" / "left_open.json"
        assert listing.exists()

        await manager.call("csi", "main", "csi_launch", {"product": "ETABS", "visible": True}, CallEffect.WRITE)
        assert await guard.close_started(recording, [started]) == []  # now the current target: exited gracefully

        assert recording.tools[-1] == "csi_exit"
        assert json.loads(listing.read_text()) == []

    _run(tmp_path, make_config(), body)
