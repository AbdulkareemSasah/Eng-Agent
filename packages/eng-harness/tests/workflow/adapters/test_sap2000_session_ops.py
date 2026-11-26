"""SAP2000 session operations on a `.SDB` working copy (plan 0012 T3; spec 0012 AC5)."""

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ModelStateStore, Workspace
from mcp import types

from eng_harness.adapters.csi import csi_allowlist
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

ConfigFactory = Callable[..., ServersConfig]
SAP2000_EXE = "SAP2000.exe"
FIRST_PID = 4242
_START = 1_700_000_000_000


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _body(result: types.CallToolResult) -> dict[str, Any]:
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    body: dict[str, Any] = json.loads(block.text)
    return body


class _Sap2000Inspector:
    """In-memory inspector tracking SAP2000 processes launched by the synthetic fake."""

    def __init__(self, control: Path) -> None:
        self._control = control
        self.running: dict[int, ProcessIdentity] = {}
        self.terminated: list[ProcessIdentity] = []

    def _ingest(self) -> None:
        data = json.loads(self._control.read_text())
        for pid in data.get("launched", []):
            assert isinstance(pid, int)
            if pid not in self.running:
                self.running[pid] = ProcessIdentity(pid, f"t{len(self.running) + 1}", SAP2000_EXE)

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


def test_working_copy_sdb(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC5: working_copy on a `.SDB` launches hidden SAP2000, opens the copy, records units and lineage.

    Pins the T3 SAP2000 gap registry (SP-1): a prepared `.SDB` is the way in; creating a model is not (AC6).
    """
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.csi import products
    from eng_harness.adapters.csi._gaps import SAP2000_GAPS, new_model
    from eng_harness.adapters.csi.products import _sap2000
    from eng_harness.errors import HarnessCode, NotImplementedGap

    assert "SP-1" in SAP2000_GAPS

    control.write_text(json.dumps({"faults": [], "seed": {}, "product": "SAP2000"}))
    base = make_config()
    section = base.servers["csi"].model_copy(update={"product": "SAP2000", "host_key": "csi_sap2000"})
    config = ServersConfig(servers={"csi_sap2000": section})
    allowlist = csi_allowlist().for_product("SAP2000")
    assert products.profile("SAP2000").model_extensions == _sap2000.MODEL_EXTENSIONS == (".SDB",)
    assert products.profile("SAP2000").companion_globs == _sap2000.COMPANION_GLOBS == ()

    clock = FixedClock(_START)
    ids = SeededIdSource(b"sap2000-session", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    original = tmp_path / "tower.SDB"
    original.write_bytes(b"sap2000-model-v1")
    run_dir = tmp_path / "run"
    inspector = _Sap2000Inspector(control)
    guard = ProcessGuard(inspector, run_dir, host_exes=[SAP2000_EXE])
    engine_id = ProcessIdentity(os.getpid(), "t0", "python")
    locks = HostLocks(tmp_path / "locks", run_id="b247", engine=engine_id, clock=clock)
    manager = ServerManager(config, run_dir, helpers=guard, check={"csi_sap2000": allowlist.build_expectation()})
    port = AdapterHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids),
        sessions=manager,
        guard=guard,
        inspector=inspector,
        locks=locks,
        clock=clock,
        ids=ids,
        run_dir=run_dir,
        product="SAP2000",
        program="sap2000",
        exe_name=SAP2000_EXE,
        server="csi_sap2000",
        host_key="csi_sap2000",
        files={"m": original},
    )

    async def body() -> None:
        async with manager:
            [preflight] = await manager.preflight({"csi_sap2000": allowlist.sasaah_commit})
            assert preflight.ok is True
            assert products.product_of_model(str(original), "SAP2000") is products.profile("SAP2000")

            copy_key = await port.working_copy("m", run_dir / "copies")
            assert copy_key == "m@copy"
            copies = port.model_files(copy_key)
            assert len(copies) == 1
            assert copies[0].suffix == ".SDB"
            assert _sha(copies[0]) == _sha(original)

            held = await port.locate(copy_key)
            assert held is not None
            assert held.pid == FIRST_PID
            assert held.program == "sap2000"

            holder = locks.holder("sap2000", ProcessIdentity(held.pid, "t1", SAP2000_EXE))
            assert holder is not None
            assert holder.run_id == "b247"

            status = _body(await manager.call("csi_sap2000", "main", "csi_status", {}, CallEffect.READ))
            assert status["current_target"] == {"product": "SAP2000", "pid": FIRST_PID, "launched": True}

            calls = _calls(control)
            launches = [c for c in calls if c["tool"] == "csi_launch"]
            assert len(launches) == 1
            assert launches[0]["visible"] is False
            assert launches[0]["role"] == "main"
            assert launches[0]["product"] == "SAP2000"
            opens = [c for c in calls if c["tool"] == "csi_open_model"]
            assert len(opens) == 1
            assert opens[0]["path"] == str(copies[0])
            assert opens[0]["confirm"] is True

            recorded = json.loads((run_dir / "adapter" / "state.json").read_text())
            assert recorded["expected_units"][copy_key] == "kN_m_C"

            saved = await port.save(copy_key, "pre_analysis")
            saved_state = states.get(saved.model_id)
            assert saved_state is not None
            assert saved_state.derived_from is not None
            original_state = states.get(saved_state.derived_from)
            assert original_state is not None
            assert original_state.derived_from is None

            with pytest.raises(NotImplementedGap) as refused:
                new_model(product="SAP2000")
            assert refused.value.code is HarnessCode.NOT_IMPLEMENTED
            assert refused.value.evidence == ("SP-1",)
            assert not any(c["tool"] in ("csi_new_model", "csi_new_blank_model") for c in _calls(control))

            await port.close_started("csi_sap2000", [held])
            assert await port.locate(copy_key) is None
            assert inspector.terminated == []

    anyio.run(body)
