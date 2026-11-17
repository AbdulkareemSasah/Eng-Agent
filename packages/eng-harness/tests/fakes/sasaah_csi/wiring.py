"""B-138 test rig: production wiring and Engine over real synthetic-server processes, never a host program."""

import asyncio
import hashlib
import json
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from eng_contract.envelope import Provenance
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from fakes.ports import FakeApprovalPort, FakeCalcPort, FakeInputPort
from workflow.adapters.test_csi_session_ops import LaunchInspector
from workflow.adapters.test_readback import _seeded
from workflows.chain import chain

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.basis import StoreBasisPort
from eng_harness.block import Registry
from eng_harness.engine import Engine, EnginePorts, EngineSettings, PermissionMode, RunRequest
from eng_harness.journal import JournalReader
from eng_harness.ports import RunClass
from eng_harness.servers import ServersConfig
from eng_harness.servers._launcher import PosixLauncher
from eng_harness.servers._procinfo import PosixProcessInspector, ProcessIdentity

EDITS = [
    ("csi_assign_frame_section", {"model": "m", "frame": "F1", "section": "C40"}),
    ("csi_assign_area_section", {"model": "m", "area": "A1", "section": "SL20"}),
]
STEPS = [
    ("csi_open_model", {"model": "m"}),
    ("csi_read_model_state", {"model": "m"}),
    *EDITS,
    ("csi_save_model", {"model": "m", "as_new_revision": True}),
    ("csi_run_analysis", {"model": "m"}),
    ("csi_design_run", {"model": "m", "kind": "steel"}),
    ("csi_design_results", {"model": "m", "kind": "steel"}),
    ("csi_results_joint_reactions", {"model": "m"}),
]


class Inspector(LaunchInspector):
    """Synthetic ETABS pids and real engine identity; real servers use their own POSIX launcher."""

    def identity(self, pid: int) -> ProcessIdentity | None:
        return PosixProcessInspector().identity(pid) if pid == os.getpid() else super().identity(pid)


def config(control: Path) -> ServersConfig:
    with Path(sys.executable).open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    return ServersConfig.model_validate({
        "servers": {"csi": {
            "adapter": "sasaah-csi-mcp", "command": sys.executable,
            "args": [str(Path(__file__).with_name("server.py")), "--disable-script"],
            "env": {"SASAAH_CSI_FAKE_CONTROL": str(control)}, "client_grace_s": 5,
            "max_restarts_per_run": 1, "shutdown_grace_s": 5,
            "build": {"sasaah_commit": csi_allowlist().sasaah_commit, "exe_sha256": digest}, "host_key": "csi",
            "roles": {"main": {"classes": ["session", "call"], "call_timeout_s": 30},
                      "long": {"classes": ["long"], "call_timeout_s": 30}},
        }},
        "host_programs": {"etabs": {"executables": ["ETABS.exe"], "install_dirs": []}},
    })


@dataclass
class Rig:
    root: Path
    control: Path
    workspace: Workspace
    store: ResultStore
    clock: FixedClock
    ids: SeededIdSource
    basis_ref: str
    run_id: str
    original: Path

    def ports(self, **options: Any) -> Any:
        from eng_harness.adapters import build_ports

        return build_ports(
            options.pop("config", config(self.control)), self.workspace, self.store, self.run_dir, self.clock,
            self.ids, inspector=Inspector(self.control), launcher=PosixLauncher(), lock_dir=self.root / "locks",
            files={"m": self.original}, **options,
        )

    @property
    def run_dir(self) -> Path:
        return self.workspace.root / "runs" / self.run_id

    def engine(self, ports: Any, steps: Any = STEPS) -> Engine:
        workflow = chain(steps)
        workflow = replace(workflow, min_server_builds={"csi": csi_allowlist().sasaah_commit}, copy_on_open=True)
        return Engine(self.workspace, Registry([workflow]), EnginePorts(
            tool=ports.tool_port, host=ports.host_port, calc=FakeCalcPort(RunClass.TRIAL, []),
            basis=StoreBasisPort(self.store), approvals=FakeApprovalPort(), inputs=FakeInputPort(),
        ), self.store, EngineSettings(), self.clock, self.ids)

    def request(self, *, mode: PermissionMode = PermissionMode.WORK_ON_COPY) -> RunRequest:
        return RunRequest(workflow="chain", input={}, basis_ref=self.basis_ref, run_class=RunClass.TRIAL,
                          mode=mode, run_id=self.run_id)

    def events(self) -> list[Any]:
        reader = JournalReader(self.run_dir)
        try:
            return reader.events()
        finally:
            reader.close()

    def calls(self, tool: str) -> list[dict[str, Any]]:
        return [c for c in json.loads(self.control.read_text()).get("calls", []) if c["tool"] == tool]


def rig(root: Path, *, tolerance: Any = 0.25) -> Rig:
    """The explicit tolerance is a synthetic engineer input: 8 may read in [6,10], not a product default."""
    root.mkdir(parents=True, exist_ok=True)
    control = root / "control.json"
    if not control.exists():
        _seeded(control)
        data = json.loads(control.read_text())
        data["persist_model"] = True
        control.write_text(json.dumps(data))
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"b138-wire", clock)
    workspace = Workspace(root=root / "workspace", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    basis = {"template": None, "fields": {}}
    if tolerance is not None:
        basis["fields"]["checks.readback_relative_tolerance_ratio"] = {
            "value": tolerance, "unit": "1", "source": f"engineer:test@{clock.now()}",
            "confirmed": True, "citation": None,
        }
    provenance = Provenance(tool="test/wiring", tool_version="1", inputs={}, started_at=clock.now(), duration_ms=0)
    basis_ref = store.put("basis.design_basis/1", basis, provenance).result_id
    original = root / "original.EDB"
    if not original.exists():
        original.write_bytes(b"synthetic model")
    return Rig(root, control, workspace, store, clock, ids, basis_ref, f"run_{ids.new_ulid()}", original)


async def crash_worker(root: Path, cut: str) -> None:
    """Signal after a real write returned, before Engine can record its completion; parent SIGKILLs us."""
    r = rig(root)
    async with r.ports() as ports:
        call = ports.tool_port.call

        async def stopped(tool: str, *args: Any, **kwargs: Any) -> Any:
            result = await call(tool, *args, **kwargs)
            if tool == cut:
                (root / "cut.json").write_text(json.dumps({"run_id": r.run_id, "basis_ref": r.basis_ref}))
                await asyncio.Event().wait()
            return result

        ports.tool_port.call = stopped
        await r.engine(ports).start(r.request())


if __name__ == "__main__":
    asyncio.run(crash_worker(Path(sys.argv[1]), sys.argv[2]))
