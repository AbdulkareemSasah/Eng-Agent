"""SAFE session operations on a `.FDB` working copy (plan 0008 T3; spec 0008 AC6)."""

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ModelStateStore, Workspace
from mcp import types

from eng_harness.adapters.csi import csi_allowlist
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

ConfigFactory = Callable[..., ServersConfig]
SAFE_EXE = "SAFE.exe"
FIRST_PID = 4242
_START = 1_700_000_000_000


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _body(result: types.CallToolResult) -> dict[str, Any]:
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    body: dict[str, Any] = json.loads(block.text)
    return body


class _SafeInspector:
    """In-memory inspector tracking SAFE processes launched by the synthetic fake."""

    def __init__(self, control: Path) -> None:
        self._control = control
        self.running: dict[int, ProcessIdentity] = {}
        self.terminated: list[ProcessIdentity] = []

    def _ingest(self) -> None:
        data = json.loads(self._control.read_text())
        for pid in data.get("launched", []):
            assert isinstance(pid, int)
            if pid not in self.running:
                self.running[pid] = ProcessIdentity(pid, f"t{len(self.running) + 1}", SAFE_EXE)

    def identity(self, pid: int) -> ProcessIdentity | None:
        self._ingest()
        return self.running.get(pid)

    def alive(self, identity: ProcessIdentity) -> bool:
        self._ingest()
        found = self.running.get(identity.pid)
        return found is not None and found.started_at == identity.started_at

    def children(self, pid: int) -> list[ProcessIdentity]:
        return []

    def snapshot(self, exe_names: list[str]) -> list[ProcessIdentity]:
        self._ingest()
        return [item for item in self.running.values() if item.exe_name in exe_names]

    def terminate(self, identity: ProcessIdentity) -> bool:
        if not self.alive(identity):
            return False
        self.terminated.append(self.running.pop(identity.pid))
        return True


def _calls(control: Path) -> list[dict[str, Any]]:
    data = json.loads(control.read_text())
    calls = data.get("calls", [])
    assert isinstance(calls, list)
    return calls


def test_working_copy_fdb(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC6: working_copy on a `.FDB` launches hidden SAFE, locks it, opens copy, records units and lineage."""
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.csi import products
    from eng_harness.adapters.csi.products import _safe

    control.write_text(json.dumps({"faults": [], "seed": {}, "product": "SAFE"}))
    base = make_config()
    safe_section = base.servers["csi"].model_copy(update={"product": "SAFE", "host_key": "csi_safe"})
    config = ServersConfig(servers={"csi_safe": safe_section})
    safe_allowlist = csi_allowlist().for_product("SAFE")
    assert products.profile("SAFE").model_extensions == _safe.MODEL_EXTENSIONS == (".FDB",)
    assert products.profile("SAFE").companion_globs == _safe.COMPANION_GLOBS == ()

    clock = FixedClock(_START)
    ids = SeededIdSource(b"safe-session", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    original = tmp_path / "footing.FDB"
    original.write_bytes(b"safe-model-v1")
    run_dir = tmp_path / "run"
    inspector = _SafeInspector(control)
    guard = ProcessGuard(inspector, run_dir, host_exes=[SAFE_EXE])
    engine_id = ProcessIdentity(os.getpid(), "t0", "python")
    locks = HostLocks(tmp_path / "locks", run_id="b212", engine=engine_id, clock=clock)
    manager = ServerManager(config, run_dir, helpers=guard, check={"csi_safe": safe_allowlist.build_expectation()})
    port = AdapterHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids),
        sessions=manager,
        guard=guard,
        inspector=inspector,
        locks=locks,
        clock=clock,
        ids=ids,
        run_dir=run_dir,
        product="SAFE",
        program="safe",
        exe_name=SAFE_EXE,
        server="csi_safe",
        host_key="csi_safe",
        files={"m": original},
    )

    async def body() -> None:
        async with manager:
            [preflight] = await manager.preflight({"csi_safe": safe_allowlist.sasaah_commit})
            assert preflight.ok is True
            assert products.product_of_model(str(original), "SAFE") is products.profile("SAFE")

            copy_key = await port.working_copy("m", run_dir / "copies")
            assert copy_key == "m@copy"
            copies = port.model_files(copy_key)
            assert len(copies) == 1
            assert copies[0].suffix == ".FDB"
            assert _sha(copies[0]) == _sha(original)

            held = await port.locate(copy_key)
            assert held is not None
            assert held.pid == FIRST_PID
            assert held.program == "safe"

            holder = locks.holder("safe", ProcessIdentity(held.pid, "t1", SAFE_EXE))
            assert holder is not None
            assert holder.run_id == "b212"

            status = _body(await manager.call("csi_safe", "main", "csi_status", {}, CallEffect.READ))
            assert status["current_target"] == {"product": "SAFE", "pid": FIRST_PID, "launched": True}

            calls = _calls(control)
            launches = [c for c in calls if c["tool"] == "csi_launch"]
            assert len(launches) == 1
            assert launches[0]["visible"] is False
            assert launches[0]["role"] == "main"
            opens = [c for c in calls if c["tool"] == "csi_open_model"]
            assert len(opens) == 1
            assert opens[0]["path"] == str(copies[0])

            recorded = json.loads((run_dir / "adapter" / "state.json").read_text())
            assert recorded["expected_units"][copy_key] == "kN_m_C"

            saved = await port.save(copy_key, "pre_analysis")
            saved_state = states.get(saved.model_id)
            assert saved_state is not None
            assert saved_state.derived_from is not None
            original_state = states.get(saved_state.derived_from)
            assert original_state is not None
            assert original_state.derived_from is None

            await port.close_started("csi_safe", [held])
            assert await port.locate(copy_key) is None
            assert inspector.terminated == []

    anyio.run(body)
