"""B-138 test rig: production wiring and Engine over real synthetic-server processes, never a host program."""

import asyncio
import hashlib
import json
import os
import re
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from eng_contract.envelope import Provenance, SuccessEnvelope
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.refs import Ref
from eng_contract.store import LocationClass, ResultStore, Workspace
from pydantic import BaseModel, JsonValue
from workflow.adapters.test_csi_session_ops import LaunchInspector
from workflow.adapters.test_readback import _seeded
from workflows.chain import ChainInput, ChainOutput, chain

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.basis import StoreBasisPort
from eng_harness.block import Registry, workflow
from eng_harness.engine import Engine, EnginePorts, EngineSettings, PermissionMode, RunRequest
from eng_harness.journal import JournalReader
from eng_harness.ports import InputAnswer, InputRequest, RunClass
from eng_harness.servers import ServersConfig
from eng_harness.servers._launcher import PosixLauncher
from eng_harness.servers._procinfo import PosixProcessInspector, ProcessIdentity
from fakes.ports import FakeApprovalPort, FakeCalcPort, FakeInputPort

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
    return ServersConfig.model_validate(
        {
            "servers": {
                "csi": {
                    "adapter": "sasaah-csi-mcp",
                    "command": sys.executable,
                    "args": [str(Path(__file__).with_name("server.py")), "--disable-script"],
                    "env": {"SASAAH_CSI_FAKE_CONTROL": str(control)},
                    "client_grace_s": 5,
                    "max_restarts_per_run": 1,
                    "shutdown_grace_s": 5,
                    "build": {"sasaah_commit": csi_allowlist().sasaah_commit, "exe_sha256": digest},
                    "host_key": "csi",
                    "product": "ETABS",
                    "roles": {
                        "main": {"classes": ["session", "call"], "call_timeout_s": 30},
                        "long": {"classes": ["long"], "call_timeout_s": 30},
                    },
                }
            },
            "host_programs": {"etabs": {"executables": ["ETABS.exe"], "install_dirs": []}},
        }
    )


class ContinueInput(BaseModel):
    note: str


@workflow(name="chain", version=1, description="Pause while the test observes read-back wiring.")
async def pause(ctx: Any, inp: ChainInput) -> ChainOutput:
    await ctx.ask(ContinueInput, title="Continue")
    return ChainOutput(refs=[])


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

    def value(self, field: str, number: float) -> dict[str, str]:
        provenance = Provenance(
            tool="test/wiring", tool_version="1", inputs={}, started_at=self.clock.now(), duration_ms=0
        )
        record = self.store.put("harness.run_input/1", {"value": {field: number}}, provenance)
        return {"$ref": f"{record.result_id}#/value/{field}"}

    def ports(self, **options: Any) -> Any:
        from eng_harness.adapters import build_ports

        return build_ports(
            options.pop("config", config(self.control)),
            self.workspace,
            self.store,
            self.run_dir,
            self.clock,
            self.ids,
            inspector=Inspector(self.control),
            launcher=PosixLauncher(),
            lock_dir=self.root / "locks",
            files={"m": self.original},
            **options,
        )

    @property
    def run_dir(self) -> Path:
        return self.workspace.root / "runs" / self.run_id

    def engine(self, ports: Any, steps: Any = STEPS, *, inputs: Any = None, paused: bool = False) -> Engine:
        flow = pause if paused else chain(steps)
        flow = replace(flow, min_server_builds={"csi": csi_allowlist().sasaah_commit}, copy_on_open=True)
        return Engine(
            self.workspace,
            Registry([flow]),
            EnginePorts(
                tool=ports.tool_port,
                host=ports.host_port,
                calc=FakeCalcPort(RunClass.TRIAL, []),
                basis=StoreBasisPort(self.store),
                approvals=FakeApprovalPort(),
                inputs=inputs or FakeInputPort(),
            ),
            self.store,
            EngineSettings(),
            self.clock,
            self.ids,
        )

    def request(self, *, mode: PermissionMode = PermissionMode.WORK_ON_COPY) -> RunRequest:
        return RunRequest(
            workflow="chain",
            input={},
            basis_ref=self.basis_ref,
            run_class=RunClass.TRIAL,
            mode=mode,
            run_id=self.run_id,
        )

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
    ids = SeededIdSource(f"b138-wire-{os.getpid()}".encode(), clock)
    workspace = Workspace(root=root / "workspace", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    fields: dict[str, JsonValue] = {}
    basis: dict[str, JsonValue] = {"template": None, "fields": fields}
    if tolerance is not None:
        fields["checks.readback_relative_tolerance_ratio"] = {
            "value": tolerance,
            "unit": "1",
            "source": f"engineer:test@{clock.now()}",
            "confirmed": True,
            "citation": None,
        }
    provenance = Provenance(tool="test/wiring", tool_version="1", inputs={}, started_at=clock.now(), duration_ms=0)
    basis_ref = store.put("basis.design_basis/1", basis, provenance).result_id
    original = root / "original.EDB"
    if not original.exists():
        original.write_bytes(b"synthetic model")
    return Rig(root, control, workspace, store, clock, ids, basis_ref, f"run_{ids.new_ulid()}", original)


class AppliedInput(FakeInputPort):
    """Explicit synthetic engineer confirmation; never a production decision or adapter proof of end."""

    def __init__(self, cut: str) -> None:
        super().__init__()
        self.cut = cut

    async def present(self, request: InputRequest) -> None:
        await super().present(request)
        fields = cast(dict[str, Any], request.fields_schema["properties"])
        why = fields["why"]["default"]
        if request.kind == "engine.host_state":
            assert self.cut == "csi_save_model", request
            assert request.title == "A model changed while the run was stopped (m@copy)", request
            assert re.fullmatch(r"m@copy is at revision 1 \([0-9a-f]{64}\), the journal has 0", why), request
            assert "accept" in fields["state"]["enum"], request
            choices = {"state": "accept"}
        else:
            assert request.kind == "engine.in_flight", request
            assert request.title == f"A write was cut off ({self.cut})", request
            expected = "the adapter has no reconciler for this tool"
            if self.cut in {"csi_run_analysis", "csi_design_run"}:
                expected = "the adapter could not decide: unknown"
            assert why == expected, request
            choices = {"outcome": "applied"}
        self.script(
            request.request_id,
            InputAnswer(
                request_id=request.request_id,
                shown_sha256=request.fields_schema_sha256,
                choices=choices,
                by="engineer:test",
            ),
        )


async def crash_worker(root: Path, cut: str) -> None:
    """Signal after a real write returned, before Engine can record its completion; parent SIGKILLs us."""
    r = rig(root)
    async with r.ports() as ports:
        call = ports.tool_port.call

        async def stopped(tool: str, *args: Any, **kwargs: Any) -> Any:
            result = await call(tool, *args, **kwargs)
            if tool == cut:
                assert isinstance(result, SuccessEnvelope), result
                marker = root / "cut.tmp"
                marker.write_text(json.dumps({"run_id": r.run_id, "basis_ref": r.basis_ref}))
                marker.replace(root / "cut.json")
                await asyncio.Event().wait()
            return result

        ports.tool_port.call = stopped
        outcome = await r.engine(ports).start(r.request())
        raise AssertionError(f"the worker ended before the cut at {cut}: {outcome}")


def run_crash_worker(root: str, cut: str) -> None:
    """Entry of a spawned engine process, with errors retained for the parent's assertion."""
    folder = Path(root)
    with (folder / "worker.log").open("w") as log, redirect_stdout(log), redirect_stderr(log):
        try:
            asyncio.run(crash_worker(folder, cut))
        except BaseException:
            traceback.print_exc()
            raise


# --- SAFE product (plan 0008 T8; spec 0008 AC26, AC27) ---

SAFE_EXE = "SAFE.exe"
SAFE_WRITE_CUTS = frozenset({"csi_set_point_load", "csi_save_model", "csi_run_analysis"})


class SafeInspector(LaunchInspector):
    """Synthetic SAFE pids and real engine identity."""

    def __init__(self, control: Path) -> None:
        super().__init__(control, exe_name=SAFE_EXE)

    def identity(self, pid: int) -> ProcessIdentity | None:
        return PosixProcessInspector().identity(pid) if pid == os.getpid() else super().identity(pid)


def safe_config(control: Path) -> ServersConfig:
    """One CSI server section whose product is SAFE (spec 0008 AC1)."""
    with Path(sys.executable).open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    return ServersConfig.model_validate(
        {
            "servers": {
                "csi": {
                    "adapter": "sasaah-csi-mcp",
                    "command": sys.executable,
                    "args": [str(Path(__file__).with_name("server.py")), "--disable-script"],
                    "env": {"SASAAH_CSI_FAKE_CONTROL": str(control)},
                    "client_grace_s": 5,
                    "max_restarts_per_run": 1,
                    "shutdown_grace_s": 5,
                    "build": {"sasaah_commit": csi_allowlist().sasaah_commit, "exe_sha256": digest},
                    "host_key": "csi",
                    "product": "SAFE",
                    "roles": {
                        "main": {"classes": ["session", "call"], "call_timeout_s": 30},
                        "long": {"classes": ["long"], "call_timeout_s": 30},
                    },
                }
            },
            "host_programs": {"safe": {"executables": [SAFE_EXE], "install_dirs": []}},
        }
    )


def _safe_seed() -> dict[str, Any]:
    """SAFE footing seed: one supported area, defined sections, soil pressures and reactions (spec 0008 §4.4, §4.6).

    Built so `check_model` integrity stays clean (no SECTION_UNDEFINED / AREA_WITHOUT_SOIL_SUPPORT errors).
    """
    from workflow.adapters.test_safe_results import _SOIL_ROW
    from workflow.adapters.test_safe_state import _seed

    seed = _seed(points=1, joint_loads=1)
    # Drop the unsupported second area (A2) so AREA_WITHOUT_SOIL_SUPPORT is not an error for the cycle.
    seed["areas"] = [a for a in seed["areas"] if a["name"] == "A1"]
    seed["area_sections"] = [{"name": "FOOT", "type": "slab"}, {"name": "DROP", "type": "slab"}]
    seed["frame_sections"] = [{"name": "GB"}]
    seed["tables"]["Soil Pressures"] = [{**_SOIL_ROW}]
    seed["results"] = {
        "csi_results_base_reactions": [
            {"case": "DEAD", "F1": 1.0, "F2": -2.0, "F3": 50.0, "M1": 0.5, "M2": -0.25, "M3": 0.0}
        ],
        "csi_results_joint_reactions": [
            {"joint": "P1", "case": "DEAD", "F1": 0.0, "F2": 0.0, "F3": -100.0, "M1": 0.0, "M2": 0.0, "M3": 0.0}
        ],
    }
    return seed


def SAFE_STEPS(r: Rig) -> list[tuple[str, dict[str, Any]]]:
    """AC26 cycle: open, import one point load, save, analyse, base and joint reactions.

    Model state is read by the host port after open (SafeStateReader via the profile); the adapter-local
    `csi_read_model_state` tool is ETABS-shaped (stories/restraints) and is not used for SAFE here.
    Quantity refs are fixed on the rig so a crash worker and its parent resume share the same arguments.
    """
    qty = getattr(r, "_safe_qty")
    return [
        ("csi_open_model", {"model": "m"}),
        (
            "csi_set_point_load",
            {
                "model": "m",
                "joint": "P1",
                "pattern": "DEAD",
                "FX_kN": qty["FX_kN"],
                "FY_kN": qty["FY_kN"],
                "FZ_kN": qty["FZ_kN"],
                "MX_kNm": qty["MX_kNm"],
                "MY_kNm": qty["MY_kNm"],
                "MZ_kNm": qty["MZ_kNm"],
            },
        ),
        ("csi_save_model", {"model": "m", "as_new_revision": True}),
        ("csi_run_analysis", {"model": "m"}),
        ("csi_results_base_reactions", {"model": "m"}),
        ("csi_results_joint_reactions", {"model": "m"}),
    ]


def safe_rig(root: Path, *, tolerance: Any = 0.25) -> Rig:
    """Production wiring over a synthetic SAFE process (plan 0008 T8).

    The first call on `root` writes basis and load quantity results and a marker; later calls (the crash worker,
    the resume) reopen the same workspace and reuse those result ids so tool arguments match the journal.
    """
    root.mkdir(parents=True, exist_ok=True)
    control = root / "control.json"
    if not control.exists():
        control.write_text(json.dumps({"faults": [], "seed": _safe_seed(), "product": "SAFE", "persist_model": True}))
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"b217-safe-fixed", clock)
    workspace = Workspace(root=root / "workspace", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    marker = root / "safe_rig.json"
    provenance = Provenance(tool="test/wiring", tool_version="1", inputs={}, started_at=clock.now(), duration_ms=0)
    if marker.exists():
        data = json.loads(marker.read_text(encoding="utf-8"))
        basis_ref = str(data["basis_ref"])
        qty = {name: Ref.model_validate({"$ref": ref}) for name, ref in data["qty"].items()}
        run_id = f"run_{ids.new_ulid()}"
    else:
        fields: dict[str, JsonValue] = {}
        basis: dict[str, JsonValue] = {"template": None, "fields": fields}
        if tolerance is not None:
            fields["checks.readback_relative_tolerance_ratio"] = {
                "value": tolerance,
                "unit": "1",
                "source": f"engineer:test@{clock.now()}",
                "confirmed": True,
                "citation": None,
            }
        basis_ref = store.put("basis.design_basis/1", basis, provenance).result_id
        qty = {}
        qty_refs: dict[str, str] = {}
        for field, number in (
            ("FX_kN", 0.0),
            ("FY_kN", 0.0),
            ("FZ_kN", -100.0),
            ("MX_kNm", 0.0),
            ("MY_kNm", 0.0),
            ("MZ_kNm", 0.0),
        ):
            result_id = store.put("harness.run_input/1", {"value": {field: number}}, provenance).result_id
            pointer = f"{result_id}#/value/{field}"
            qty[field] = Ref.model_validate({"$ref": pointer})
            qty_refs[field] = pointer
        run_id = f"run_{ids.new_ulid()}"
        marker.write_text(json.dumps({"basis_ref": basis_ref, "qty": qty_refs}), encoding="utf-8")
    original = root / "original.FDB"
    if not original.exists():
        original.write_bytes(b"synthetic safe model")
    r = Rig(root, control, workspace, store, clock, ids, basis_ref, run_id, original)
    r._safe_qty = qty  # type: ignore[attr-defined]

    def ports(**options: Any) -> Any:
        from eng_harness.adapters import build_ports

        return build_ports(
            options.pop("config", safe_config(control)),
            workspace,
            store,
            r.run_dir,
            clock,
            ids,
            inspector=SafeInspector(control),
            launcher=PosixLauncher(),
            lock_dir=root / "locks",
            files={"m": original},
            **options,
        )

    r.ports = ports  # type: ignore[method-assign]

    def engine(ports: Any, steps: Any = None, *, inputs: Any = None, paused: bool = False) -> Engine:
        flow = pause if paused else chain(steps if steps is not None else SAFE_STEPS(r))
        flow = replace(flow, min_server_builds={"csi": csi_allowlist().sasaah_commit}, copy_on_open=True)
        return Engine(
            workspace,
            Registry([flow]),
            EnginePorts(
                tool=ports.tool_port,
                host=ports.host_port,
                calc=FakeCalcPort(RunClass.TRIAL, []),
                basis=StoreBasisPort(store),
                approvals=FakeApprovalPort(),
                inputs=inputs or FakeInputPort(),
            ),
            store,
            EngineSettings(),
            clock,
            ids,
        )

    r.engine = engine  # type: ignore[method-assign]

    async def read_soil_pressures(ports: Any, *, model: str = "m@copy") -> Any:
        from eng_harness.adapters.csi.products._safe_results import read_soil_pressures as _read
        from eng_harness.servers import CallEffect
        from eng_harness.servers._session import reply_body

        held = await ports.host_port.locate(model)
        assert held is not None

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            # safe_config names the server section `csi`.
            reply = await ports.servers.call("csi", "main", tool, arguments, effect)
            body = reply_body(reply)
            assert body is not None
            return body

        assert held.pid is not None
        return await _read(call, product="SAFE", pid=held.pid, cases=["DEAD"], units="kN_m_C")

    r.read_soil_pressures = read_soil_pressures  # type: ignore[attr-defined]
    return r


class SafeAppliedInput(FakeInputPort):
    """Explicit synthetic engineer confirmation for SAFE write cuts (AC27)."""

    def __init__(self, cut: str) -> None:
        super().__init__()
        self.cut = cut

    async def present(self, request: InputRequest) -> None:
        await super().present(request)
        fields = cast(dict[str, Any], request.fields_schema["properties"])
        why = fields["why"]["default"]
        if request.kind == "engine.host_state":
            assert self.cut == "csi_save_model", request
            assert request.title == "A model changed while the run was stopped (m@copy)", request
            assert re.fullmatch(r"m@copy is at revision 1 \([0-9a-f]{64}\), the journal has 0", why), request
            assert "accept" in fields["state"]["enum"], request
            choices = {"state": "accept"}
        else:
            assert request.kind == "engine.in_flight", request
            assert request.title == f"A write was cut off ({self.cut})", request
            expected = "the adapter has no reconciler for this tool"
            if self.cut == "csi_run_analysis":
                expected = "the adapter could not decide: unknown"
            assert why == expected, request
            choices = {"outcome": "applied"}
        self.script(
            request.request_id,
            InputAnswer(
                request_id=request.request_id,
                shown_sha256=request.fields_schema_sha256,
                choices=choices,
                by="engineer:test",
            ),
        )


async def safe_crash_worker(root: Path, cut: str) -> None:
    """Signal after a real SAFE write returned, before Engine can record its completion; parent SIGKILLs us."""
    r = safe_rig(root)
    async with r.ports() as ports:
        call = ports.tool_port.call

        async def stopped(tool: str, *args: Any, **kwargs: Any) -> Any:
            result = await call(tool, *args, **kwargs)
            if tool == cut:
                assert isinstance(result, SuccessEnvelope), result
                marker = root / "cut.tmp"
                marker.write_text(json.dumps({"run_id": r.run_id, "basis_ref": r.basis_ref}))
                marker.replace(root / "cut.json")
                await asyncio.Event().wait()
            return result

        ports.tool_port.call = stopped
        outcome = await r.engine(ports).start(r.request())
        raise AssertionError(f"the worker ended before the cut at {cut}: {outcome}")


def safe_run_crash_worker(root: str, cut: str) -> None:
    """Entry of a spawned SAFE engine process, with errors retained for the parent's assertion."""
    folder = Path(root)
    with (folder / "worker.log").open("w") as log, redirect_stdout(log), redirect_stderr(log):
        try:
            asyncio.run(safe_crash_worker(folder, cut))
        except BaseException:
            traceback.print_exc()
            raise


if __name__ == "__main__":
    run_crash_worker(sys.argv[1], sys.argv[2])
