"""Independent ETABS and SAFE server sessions in one run (plan 0008 T3; spec 0008 AC5)."""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
from eng_contract.envelope import FailureEnvelope, SuccessEnvelope
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ModelStateStore, ResultStore, Workspace

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters._errors import HostHealth
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.adapters.csi._checks import ReadBack, WrittenItems
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.adapters.csi._reconcile import CsiReconciler
from eng_harness.adapters.csi._tools import CsiToolPort
from eng_harness.ports import ServerCheck
from eng_harness.servers import HostProgramConfig, ServerManager, ServersConfig
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

ConfigFactory = Callable[..., ServersConfig]
_START = 1_700_000_000_000


class _ProductInspector:
    """In-memory inspector keyed by control file, giving distinct PIDs/start times per product."""

    def __init__(self, control: Path, exe_name: str, tag: str, pid_offset: int) -> None:
        self._control, self._exe, self._tag, self._offset = control, exe_name, tag, pid_offset
        self.running: dict[int, ProcessIdentity] = {}
        self.terminated: list[ProcessIdentity] = []
        self._pid_map: dict[int, int] = {}

    def _ingest(self) -> None:
        data = json.loads(self._control.read_text())
        for raw_pid in data.get("launched", []):
            assert isinstance(raw_pid, int)
            if raw_pid not in self._pid_map:
                self._pid_map[raw_pid] = raw_pid + self._offset
                self.running[raw_pid] = ProcessIdentity(raw_pid, f"{self._tag}-{len(self.running) + 1}", self._exe)

    def identity(self, pid: int) -> ProcessIdentity | None:
        self._ingest()
        return self.running.get(pid)

    def alive(self, identity: ProcessIdentity) -> bool:
        self._ingest()
        found = self.running.get(identity.pid)
        return found is not None and found.started_at == identity.started_at and found.exe_name == identity.exe_name

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


def _arm(control: Path, tool: str, fault: str) -> None:
    data = json.loads(control.read_text())
    data["faults"] = [{"fault": fault, "tool": tool}]
    control.write_text(json.dumps(data))


def test_epochs_independent(tmp_path: Path, make_config: ConfigFactory) -> None:
    """AC5: ETABS timeout raises ETABS epoch, loses launch ownership and wedges ETABS, leaving SAFE untouched."""
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore

    etabs_control = tmp_path / "etabs_control.json"
    safe_control = tmp_path / "safe_control.json"
    etabs_control.write_text(
        json.dumps(
            {
                "faults": [],
                "product": "ETABS",
                "seed": {
                    "frames": [{"name": "F1", "section": "C30"}],
                    "frame_sections": [{"name": "C30"}, {"name": "C40"}],
                    "area_sections": [{"name": "SL20"}],
                },
            }
        )
    )
    safe_control.write_text(
        json.dumps(
            {
                "faults": [],
                "product": "SAFE",
                "seed": {
                    "areas": [{"name": "A1", "section": "FT20"}],
                    "area_sections": [{"name": "FT20"}, {"name": "FT30"}],
                },
            }
        )
    )

    base_etabs = make_config().servers["csi"]
    etabs_sec = base_etabs.model_copy(
        update={
            "product": "ETABS",
            "host_key": "csi",
            "env": {"SASAAH_CSI_FAKE_CONTROL": str(etabs_control)},
        }
    )
    safe_sec = base_etabs.model_copy(
        update={
            "product": "SAFE",
            "host_key": "csi_safe",
            "env": {"SASAAH_CSI_FAKE_CONTROL": str(safe_control)},
        }
    )
    config = ServersConfig(
        servers={"csi": etabs_sec, "csi_safe": safe_sec},
        host_programs={
            "etabs": HostProgramConfig(executables=("ETABS.exe",)),
            "safe": HostProgramConfig(executables=("SAFE.exe",)),
        },
    )

    etabs_allow = csi_allowlist().for_product("ETABS")
    safe_allow = csi_allowlist().for_product("SAFE")
    clock = FixedClock(_START)
    ids = SeededIdSource(b"isolation", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    states = ModelStateStore(workspace, clock)
    identity = IdentityStore(workspace=workspace, states=states, ids=ids)
    etabs_model = tmp_path / "tower.EDB"
    safe_model = tmp_path / "footing.FDB"
    etabs_model.write_bytes(b"etabs-v1")
    safe_model.write_bytes(b"safe-v1")
    run_dir = tmp_path / "run"

    etabs_inspector = _ProductInspector(etabs_control, "ETABS.exe", "etabs", 0)
    safe_inspector = _ProductInspector(safe_control, "SAFE.exe", "safe", 1000)
    etabs_guard = ProcessGuard(etabs_inspector, run_dir / "etabs", host_exes=["ETABS.exe"])
    safe_guard = ProcessGuard(safe_inspector, run_dir / "safe", host_exes=["SAFE.exe"])
    engine_id = ProcessIdentity(os.getpid(), "t0", "py")
    locks = HostLocks(tmp_path / "locks", run_id="b212-iso", engine=engine_id, clock=clock)
    manager = ServerManager(
        config,
        run_dir,
        check={"csi": etabs_allow.build_expectation(), "csi_safe": safe_allow.build_expectation()},
    )
    etabs_written, safe_written = WrittenItems(), WrittenItems()
    etabs_check = ServerCheck(
        server="csi",
        build=f"{etabs_allow.sasaah_commit[:12]}+{'0' * 12}",
        min_build="",
        fingerprint=etabs_allow.tool_fingerprint,
        expected_fingerprint=etabs_allow.tool_fingerprint,
        ok=True,
    )
    safe_check = ServerCheck(
        server="csi_safe",
        build=f"{safe_allow.sasaah_commit[:12]}+{'0' * 12}",
        min_build="",
        fingerprint=safe_allow.tool_fingerprint,
        expected_fingerprint=safe_allow.tool_fingerprint,
        ok=True,
    )
    etabs_host = AdapterHostPort(
        identity=identity,
        sessions=manager,
        guard=etabs_guard,
        inspector=etabs_inspector,
        locks=locks,
        clock=clock,
        ids=ids,
        run_dir=run_dir / "etabs",
        product="ETABS",
        program="etabs",
        exe_name="ETABS.exe",
        server="csi",
        host_key="csi",
        states=states,
        readback=ReadBack(etabs_written, store, etabs_check),
        files={"e": etabs_model},
    )
    safe_host = AdapterHostPort(
        identity=identity,
        sessions=manager,
        guard=safe_guard,
        inspector=safe_inspector,
        locks=locks,
        clock=clock,
        ids=ids,
        run_dir=run_dir / "safe",
        product="SAFE",
        program="safe",
        exe_name="SAFE.exe",
        server="csi_safe",
        host_key="csi_safe",
        states=states,
        readback=ReadBack(safe_written, store, safe_check),
        files={"s": safe_model},
    )
    health = HostHealth()
    ledger = WriteLedger(run_dir)
    etabs_tools = CsiToolPort(
        config=config,
        server="csi",
        caller=manager,
        binder=etabs_host,
        store=store,
        ledger=ledger,
        clock=clock,
        ids=ids,
        check=etabs_check,
        health=health,
        errors=CsiErrorMapper(ids),
        reconciler=CsiReconciler(product="ETABS", tolerance_ratio=0.01),
        written=etabs_written,
        wrote=etabs_host.wrote,
    )
    safe_tools = CsiToolPort(
        config=config,
        server="csi_safe",
        caller=manager,
        binder=safe_host,
        store=store,
        ledger=ledger,
        clock=clock,
        ids=ids,
        check=safe_check,
        health=health,
        errors=CsiErrorMapper(ids),
        reconciler=CsiReconciler(product="SAFE", tolerance_ratio=0.01),
        written=safe_written,
        wrote=safe_host.wrote,
    )

    async def body() -> None:
        async with manager:
            etabs_key = await etabs_host.working_copy("e", run_dir / "copies_e")
            safe_key = await safe_host.working_copy("s", run_dir / "copies_s")
            etabs_held = await etabs_host.locate(etabs_key)
            safe_held = await safe_host.locate(safe_key)
            assert etabs_held is not None
            assert safe_held is not None

            etabs_epoch_0 = manager.session_epoch("csi")
            safe_epoch_0 = manager.session_epoch("csi_safe")
            etabs_role_0 = manager.role_session("csi", "main")
            safe_role_0 = manager.role_session("csi_safe", "main")

            _arm(etabs_control, "csi_assign_frame_section", "timeout_after_apply")
            args: dict[str, Any] = {"model": etabs_key, "frame": "F1", "section": "C40"}
            timed_out = await etabs_tools.call("csi_assign_frame_section", args, op_id="op_etabs", model=etabs_key)
            assert isinstance(timed_out, FailureEnvelope)
            assert timed_out.error.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME

            assert etabs_host.session_epoch("csi") > etabs_epoch_0
            assert safe_host.session_epoch("csi_safe") == safe_epoch_0
            assert manager.role_session("csi", "main") > etabs_role_0
            assert manager.role_session("csi_safe", "main") == safe_role_0
            assert health.wedged("csi") == "op_etabs"
            assert health.wedged("csi_safe") is None
            assert etabs_written.items(etabs_key) == []

            blocked = await etabs_tools.call("csi_assign_frame_section", args, op_id="op_blocked", model=etabs_key)
            assert isinstance(blocked, FailureEnvelope)
            assert blocked.error.code is ErrorCode.HOST_WEDGED

            safe_ok = await safe_tools.call(
                "csi_assign_area_section",
                {"model": safe_key, "area": "A1", "section": "FT30"},
                op_id="op_safe",
                model=safe_key,
            )
            assert isinstance(safe_ok, SuccessEnvelope), safe_ok
            assert len(safe_written.items(safe_key)) == 1
            assert await safe_host.locate(safe_key) == safe_held
            assert (await safe_host.read_units(safe_key, safe_held.instance_id)).ok is True
            assert health.wedged("csi") == "op_etabs"

            rec = await etabs_tools.reconcile("csi_assign_frame_section", args, "op_etabs")
            assert rec.outcome == "applied"
            assert health.wedged("csi") is None

            await safe_host.close_started("csi_safe", [safe_held])
            assert safe_inspector.terminated == []
            await etabs_host.close_started("csi", [etabs_held])
            assert len(etabs_inspector.terminated) == 1

    anyio.run(body)
