"""CSI session operations on the synthetic fake (plan 0002 T10; spec 0002 AC15, AC30, section 4.5.9).

The host program is an in-memory inspector fed by the pids the fake records as it launches, so a restore can be told
from the instance it must not reopen. The adapter import is inside the test so a missing module fails the test.
"""

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import Clock, FixedClock, IdSource, SeededIdSource
from eng_contract.store import LocationClass, ModelStateStore, Workspace
from mcp import types

from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

ConfigFactory = Callable[..., ServersConfig]
ETABS_EXE = "ETABS.exe"  # spec 0002 section 4.2, the image name that identifies an ETABS instance
PRODUCTS = [
    ("ETABS", "ETABS.exe", ".EDB", "csi"),
    ("SAFE", "SAFE.exe", ".FDB", "csi_safe"),
    ("SAP2000", "SAP2000.exe", ".SDB", "csi_sap2000"),  # plan 0012 T3 / spec 0012 AC5
]
FIRST_PID = 4242  # the pid the CSI fake gives the first instance it launches
_START = 1_700_000_000_000


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _body(result: types.CallToolResult) -> dict[str, Any]:
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    body: dict[str, Any] = json.loads(block.text)
    return body


class LaunchInspector:
    """Processes the fake has launched, read from its control file; `terminate` removes a matching one."""

    def __init__(self, control: Path, exe_name: str = ETABS_EXE) -> None:
        self._control = control
        self._exe = exe_name
        self.running: dict[int, ProcessIdentity] = {}
        self.terminated: list[ProcessIdentity] = []

    def _ingest(self) -> None:
        data = json.loads(self._control.read_text())
        launched = data.get("launched", [])
        assert isinstance(launched, list)
        for pid in launched:
            assert isinstance(pid, int)
            if pid not in self.running:
                self.running[pid] = ProcessIdentity(pid, f"t{len(self.running) + 1}", self._exe)

    def identity(self, pid: int) -> ProcessIdentity | None:
        """The running process with `pid`."""
        self._ingest()
        return self.running.get(pid)

    def alive(self, identity: ProcessIdentity) -> bool:
        """True when pid and start time match a process the fake launched and this inspector has not ended."""
        self._ingest()
        found = self.running.get(identity.pid)
        return found is not None and found.started_at == identity.started_at

    def children(self, pid: int) -> list[ProcessIdentity]:
        """The fake's host processes have no children."""
        return []

    def snapshot(self, exe_names: list[str]) -> list[ProcessIdentity]:
        """Running processes whose image is in `exe_names`."""
        self._ingest()
        return [item for item in self.running.values() if item.exe_name in exe_names]

    def terminate(self, identity: ProcessIdentity) -> bool:
        """End a matching process."""
        if not self.alive(identity):
            return False
        self.terminated.append(self.running.pop(identity.pid))
        return True


def _calls(control: Path) -> list[dict[str, Any]]:
    data = json.loads(control.read_text())
    calls = data.get("calls", [])
    assert isinstance(calls, list)
    return calls


def _arm(control: Path, tool: str, product: str = "ETABS") -> None:
    control.write_text(
        json.dumps({"faults": [{"fault": "timeout_before_apply", "tool": tool}], "seed": {}, "product": product})
    )


def _product_config(make_config: ConfigFactory, product: str, server_name: str, control: Path) -> ServersConfig:
    cfg = make_config()
    control.write_text(json.dumps({"faults": [], "seed": {}, "product": product}))
    if product == "ETABS" and server_name == "csi":
        return cfg
    section = cfg.servers["csi"].model_copy(update={"product": product, "host_key": server_name})
    return ServersConfig(servers={server_name: section})


async def _open(
    tmp_path: Path,
    config: ServersConfig,
    control: Path,
    clock: Clock,
    ids: IdSource,
    *,
    product: str = "ETABS",
    exe_name: str = ETABS_EXE,
    ext: str = ".EDB",
    server: str = "csi",
) -> tuple[Any, ServerManager, LaunchInspector, ModelStateStore, Path]:
    """The port, its server, the inspector, the model-state store and the original file, inside `async with`."""
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    original = tmp_path / f"original{ext}"
    original.write_bytes(b"model-v1")
    run_dir = tmp_path / "run"
    inspector = LaunchInspector(control, exe_name=exe_name)
    guard = ProcessGuard(inspector, run_dir, host_exes=[exe_name])
    locks = HostLocks(
        tmp_path / "locks", run_id="b129", engine=ProcessIdentity(os.getpid(), "t0", "python"), clock=clock
    )
    manager = ServerManager(config, run_dir, helpers=guard)
    port = AdapterHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids),
        sessions=manager,
        guard=guard,
        inspector=inspector,
        locks=locks,
        clock=clock,
        ids=ids,
        run_dir=run_dir,
        product=product,
        program=product,
        exe_name=exe_name,
        server=server,
        host_key=server,
        files={"m": original},
    )
    return port, manager, inspector, states, original


@pytest.mark.parametrize(("product", "exe_name", "ext", "server"), PRODUCTS)
def test_working_copy_restore_save(
    tmp_path: Path, make_config: ConfigFactory, control: Path, product: str, exe_name: str, ext: str, server: str
) -> None:
    """A working copy is a new identity, a save records its hash, and a restore reopens the owned instance."""
    clock = FixedClock(_START)
    ids = SeededIdSource(b"session", clock)

    async def body() -> None:
        cfg = _product_config(make_config, product, server, control)
        port, manager, inspector, states, original = await _open(
            tmp_path, cfg, control, clock, ids, product=product, exe_name=exe_name, ext=ext, server=server
        )
        async with manager:
            copy_key = await port.working_copy("m", tmp_path / "run" / "copies")
            assert copy_key == "m@copy"
            copies = port.model_files(copy_key)
            assert len(copies) == 1
            assert copies[0].suffix == ext
            assert _sha(copies[0]) == _sha(original)
            (copies[0].parent / "companion.$et").write_bytes(b"host")
            assert port.model_files(copy_key) == copies

            saved_id = states.get(  # the copy's identity is derived from the original
                (await port.save(copy_key, "pre_analysis")).model_id
            )
            assert saved_id is not None
            assert saved_id.derived_from is not None
            original_state = states.get(saved_id.derived_from)
            assert original_state is not None
            assert original_state.derived_from is None

            held = await port.locate(copy_key)
            assert held is not None
            assert held.pid == FIRST_PID
            assert held.program == product
            assert await port.locate("missing") is None
            assert [item.pid for item in await port.started_instances(server)] == [FIRST_PID]
            assert await port.started_instances("other") == []

            info = await manager.call(server, "main", "csi_model_info", {}, CallEffect.READ)
            recorded = json.loads((tmp_path / "run" / "adapter" / "state.json").read_text())
            assert recorded["expected_units"][copy_key] == _body(info)["units"]

            saved = await port.save(copy_key, "pre_analysis")
            assert saved.model_id == saved_id.model_id
            assert saved.file_sha256 == _sha(copies[0])
            assert saved.file_name == copies[0].name
            assert saved.revision == saved_id.revision + 1
            state = states.get(saved.model_id)
            assert state is not None
            assert (state.revision, state.file_sha256) == (saved.revision, saved.file_sha256)
            assert saved.fingerprint == (state.fingerprint or "")
            content = tmp_path / "ws" / ".eng" / "state" / "model-files" / "by-sha256" / f"{saved.file_sha256}.json"
            assert json.loads(content.read_text()) == {"model_id": saved.model_id, "revision": saved.revision}
            for path in (tmp_path / "ws" / ".eng" / "state" / "model-files").rglob("*.json"):
                assert "original" not in path.read_text()

            launches = [call for call in _calls(control) if call["tool"] == "csi_launch"]
            assert len(launches) == 1
            assert launches[0]["visible"] is False

            bad = saved.model_copy(update={"file_sha256": "0" * 64})
            with pytest.raises(ContractError, match="hash") as refused:
                await port.restore(copy_key, bad)
            assert refused.value.detail.code is ErrorCode.CONFLICT

            restored = await port.restore(copy_key, saved)
            assert restored.pid == FIRST_PID
            assert [call["tool"] for call in _calls(control) if call["tool"] == "csi_launch"] == ["csi_launch"]
            await port.close_started(server, [restored])
            assert await port.locate(copy_key) is None
            assert inspector.terminated == []  # the owned current target is exited, not killed

    anyio.run(body)


@pytest.mark.parametrize(("product", "exe_name", "ext", "server"), PRODUCTS)
def test_restore_after_timeout(
    tmp_path: Path, make_config: ConfigFactory, control: Path, product: str, exe_name: str, ext: str, server: str
) -> None:
    """After a timeout, restore launches a new hidden instance and does not open the file on the old one."""
    clock = FixedClock(_START)
    ids = SeededIdSource(b"timeout", clock)

    async def body() -> None:
        cfg = _product_config(make_config, product, server, control)
        port, manager, inspector, _states, _original = await _open(
            tmp_path, cfg, control, clock, ids, product=product, exe_name=exe_name, ext=ext, server=server
        )
        async with manager:
            copy_key = await port.working_copy("m", tmp_path / "run" / "copies")
            saved = await port.save(copy_key, "pre_analysis")
            old = await port.locate(copy_key)
            assert old is not None
            assert old.pid == FIRST_PID
            before = manager.role_session(server, "main")
            _arm(control, "csi_list_points", product=product)
            reply = await manager.call(server, "main", "csi_list_points", {}, CallEffect.READ)
            assert _body(reply)["code"] == "timeout"
            assert manager.role_session(server, "main") == before + 1

            restored = await port.restore(copy_key, saved)

            assert restored.pid != old.pid
            calls = _calls(control)
            opens = [call for call in calls if call["tool"] == "csi_open_model"]
            assert opens
            assert all(call["pid"] != old.pid for call in opens)
            assert opens[-1]["pid"] == restored.pid
            launched = [call for call in calls if call["tool"] == "csi_launch"]
            assert len(launched) == 1
            assert launched[0]["pid"] == restored.pid
            assert launched[0]["visible"] is False
            assert {item.pid for item in await port.started_instances(server)} == {old.pid, restored.pid}
            assert inspector.terminated == []  # the old instance is left to close_started

    anyio.run(body)


def test_save_records_the_state_fingerprint(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """`save` keeps the saved state's fingerprint, so the engine's resume check sees no `model_differs` (B-451 L3)."""
    clock = FixedClock(_START)
    ids = SeededIdSource(b"fingerprint", clock)

    async def body() -> None:
        port, manager, _inspector, states, _original = await _open(tmp_path, make_config(), control, clock, ids)
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            saved = await port.save(key, "pre_analysis")
            assert saved.fingerprint != ""
            held = await port.locate(key)
            assert held is not None
            read = await port.model_state(key, held.instance_id)
            assert saved.fingerprint == read.fingerprint
            state = states.get(saved.model_id)
            assert state is not None
            assert state.fingerprint == saved.fingerprint

    anyio.run(body)
