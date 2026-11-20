"""Independent ETABS, SAFE and SAP2000 server sessions in one run (plan 0012 T3; spec 0012 AC4)."""

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
    """In-memory inspector keyed by control file, giving distinct start times per product."""

    def __init__(self, control: Path, exe_name: str, tag: str) -> None:
        self._control, self._exe, self._tag = control, exe_name, tag
        self.running: dict[int, ProcessIdentity] = {}
        self.terminated: list[ProcessIdentity] = []

    def _ingest(self) -> None:
        data = json.loads(self._control.read_text())
        for raw_pid in data.get("launched", []):
            assert isinstance(raw_pid, int)
            if raw_pid not in self.running:
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


def _arm(control: Path, tool: str) -> None:
    data = json.loads(control.read_text())
    data["faults"] = [{"fault": "timeout_after_apply", "tool": tool}]
    control.write_text(json.dumps(data))


def test_epochs_independent(tmp_path: Path, make_config: ConfigFactory) -> None:
    """AC4: ETABS timeout raises only the ETABS epoch; SAFE and SAP2000 stay clear and operable.

    Pins the T3 SAP2000 gap registry so the three-product isolation suite fails at the base until T3 lands.
    """
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.csi._gaps import SAP2000_GAPS

    assert set(SAP2000_GAPS) == {f"SP-{n}" for n in range(1, 9)}

    etabs_control = tmp_path / "etabs_control.json"
    safe_control = tmp_path / "safe_control.json"
    sap_control = tmp_path / "sap2000_control.json"
    frame_seed = {
        "frames": [{"name": "F1", "section": "C30", "point1": [0.0, 0.0, 0.0], "point2": [0.0, 0.0, 3000.0]}],
        "frame_sections": [{"name": "C30"}, {"name": "C40"}],
    }
    etabs_control.write_text(json.dumps({"faults": [], "product": "ETABS", "seed": frame_seed}))
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
    sap_control.write_text(json.dumps({"faults": [], "product": "SAP2000", "seed": frame_seed}))

    base_etabs = make_config().servers["csi"]
    etabs_sec = base_etabs.model_copy(
        update={"product": "ETABS", "host_key": "csi", "env": {"SASAAH_CSI_FAKE_CONTROL": str(etabs_control)}}
    )
    safe_sec = base_etabs.model_copy(
        update={"product": "SAFE", "host_key": "csi_safe", "env": {"SASAAH_CSI_FAKE_CONTROL": str(safe_control)}}
    )
    sap_sec = base_etabs.model_copy(
        update={
            "product": "SAP2000",
            "host_key": "csi_sap2000",
            "env": {"SASAAH_CSI_FAKE_CONTROL": str(sap_control)},
        }
    )
    config = ServersConfig(
        servers={"csi": etabs_sec, "csi_safe": safe_sec, "csi_sap2000": sap_sec},
        host_programs={
            "etabs": HostProgramConfig(executables=("ETABS.exe",)),
            "safe": HostProgramConfig(executables=("SAFE.exe",)),
            "sap2000": HostProgramConfig(executables=("SAP2000.exe",)),
        },
    )

    etabs_allow = csi_allowlist().for_product("ETABS")
    safe_allow = csi_allowlist().for_product("SAFE")
    sap_allow = csi_allowlist().for_product("SAP2000")
    clock = FixedClock(_START)
    ids = SeededIdSource(b"sap2000-isolation", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    states = ModelStateStore(workspace, clock)
    identity = IdentityStore(workspace=workspace, states=states, ids=ids)
    etabs_model = tmp_path / "tower.EDB"
    safe_model = tmp_path / "footing.FDB"
    sap_model = tmp_path / "tower.SDB"
    etabs_model.write_bytes(b"etabs-v1")
    safe_model.write_bytes(b"safe-v1")
    sap_model.write_bytes(b"sap2000-v1")
    run_dir = tmp_path / "run"

    etabs_inspector = _ProductInspector(etabs_control, "ETABS.exe", "etabs")
    safe_inspector = _ProductInspector(safe_control, "SAFE.exe", "safe")
    sap_inspector = _ProductInspector(sap_control, "SAP2000.exe", "sap")
    etabs_guard = ProcessGuard(etabs_inspector, run_dir / "etabs", host_exes=["ETABS.exe"])
    safe_guard = ProcessGuard(safe_inspector, run_dir / "safe", host_exes=["SAFE.exe"])
    sap_guard = ProcessGuard(sap_inspector, run_dir / "sap2000", host_exes=["SAP2000.exe"])
    engine_id = ProcessIdentity(os.getpid(), "t0", "py")
    locks = HostLocks(tmp_path / "locks", run_id="b247-iso", engine=engine_id, clock=clock)
    manager = ServerManager(
        config,
        run_dir,
        check={
            "csi": etabs_allow.build_expectation(),
            "csi_safe": safe_allow.build_expectation(),
            "csi_sap2000": sap_allow.build_expectation(),
        },
    )
    etabs_written, safe_written, sap_written = WrittenItems(), WrittenItems(), WrittenItems()

    def _check(server: str, allow: Any) -> ServerCheck:
        return ServerCheck(
            server=server,
            build=f"{allow.sasaah_commit[:12]}+{'0' * 12}",
            min_build="",
            fingerprint=allow.tool_fingerprint,
            expected_fingerprint=allow.tool_fingerprint,
            ok=True,
            reason=None,
        )

    etabs_check = _check("csi", etabs_allow)
    safe_check = _check("csi_safe", safe_allow)
    sap_check = _check("csi_sap2000", sap_allow)

    def _host(
        *,
        product: str,
        program: str,
        exe_name: str,
        server: str,
        guard: ProcessGuard,
        inspector: _ProductInspector,
        written: WrittenItems,
        check: ServerCheck,
        files: dict[str, Path],
        sub: str,
    ) -> AdapterHostPort:
        return AdapterHostPort(
            identity=identity,
            sessions=manager,
            guard=guard,
            inspector=inspector,
            locks=locks,
            clock=clock,
            ids=ids,
            run_dir=run_dir / sub,
            product=product,
            program=program,
            exe_name=exe_name,
            server=server,
            host_key=server,
            states=states,
            readback=ReadBack(written, store, check),
            files=files,
        )

    etabs_host = _host(
        product="ETABS",
        program="etabs",
        exe_name="ETABS.exe",
        server="csi",
        guard=etabs_guard,
        inspector=etabs_inspector,
        written=etabs_written,
        check=etabs_check,
        files={"e": etabs_model},
        sub="etabs",
    )
    safe_host = _host(
        product="SAFE",
        program="safe",
        exe_name="SAFE.exe",
        server="csi_safe",
        guard=safe_guard,
        inspector=safe_inspector,
        written=safe_written,
        check=safe_check,
        files={"s": safe_model},
        sub="safe",
    )
    sap_host = _host(
        product="SAP2000",
        program="sap2000",
        exe_name="SAP2000.exe",
        server="csi_sap2000",
        guard=sap_guard,
        inspector=sap_inspector,
        written=sap_written,
        check=sap_check,
        files={"p": sap_model},
        sub="sap2000",
    )
    health = HostHealth()
    ledger = WriteLedger(run_dir)

    def _tools(
        server: str, host: AdapterHostPort, check: ServerCheck, written: WrittenItems, product: str
    ) -> CsiToolPort:
        return CsiToolPort(
            config=config,
            server=server,
            caller=manager,
            binder=host,
            store=store,
            ledger=ledger,
            clock=clock,
            ids=ids,
            check=check,
            health=health,
            errors=CsiErrorMapper(ids),
            reconciler=CsiReconciler(product=product, tolerance_ratio=0.01),
            written=written,
            wrote=host.wrote,
        )

    etabs_tools = _tools("csi", etabs_host, etabs_check, etabs_written, "ETABS")
    safe_tools = _tools("csi_safe", safe_host, safe_check, safe_written, "SAFE")
    sap_tools = _tools("csi_sap2000", sap_host, sap_check, sap_written, "SAP2000")

    async def body() -> None:
        async with manager:
            etabs_key = await etabs_host.working_copy("e", run_dir / "copies_e")
            safe_key = await safe_host.working_copy("s", run_dir / "copies_s")
            sap_key = await sap_host.working_copy("p", run_dir / "copies_p")
            etabs_held = await etabs_host.locate(etabs_key)
            safe_held = await safe_host.locate(safe_key)
            sap_held = await sap_host.locate(sap_key)
            assert etabs_held is not None
            assert safe_held is not None
            assert sap_held is not None

            etabs_epoch_0 = manager.session_epoch("csi")
            safe_epoch_0 = manager.session_epoch("csi_safe")
            sap_epoch_0 = manager.session_epoch("csi_sap2000")
            etabs_role_0 = manager.role_session("csi", "main")
            safe_role_0 = manager.role_session("csi_safe", "main")
            sap_role_0 = manager.role_session("csi_sap2000", "main")

            _arm(etabs_control, "csi_assign_frame_section")
            args: dict[str, Any] = {"model": etabs_key, "frame": "F1", "section": "C40"}
            timed_out = await etabs_tools.call("csi_assign_frame_section", args, op_id="op_etabs", model=etabs_key)
            assert isinstance(timed_out, FailureEnvelope)
            assert timed_out.error.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME

            assert etabs_host.session_epoch("csi") + health.epoch_bumps("csi") > etabs_epoch_0
            assert health.epoch_bumps("csi") == 1
            assert health.epoch_bumps("csi_safe") == 0
            assert health.epoch_bumps("csi_sap2000") == 0
            assert safe_host.session_epoch("csi_safe") + health.epoch_bumps("csi_safe") == safe_epoch_0
            assert sap_host.session_epoch("csi_sap2000") + health.epoch_bumps("csi_sap2000") == sap_epoch_0
            assert manager.role_session("csi", "main") > etabs_role_0
            assert manager.role_session("csi_safe", "main") == safe_role_0
            assert manager.role_session("csi_sap2000", "main") == sap_role_0
            assert health.wedged("csi") == "op_etabs"
            assert health.wedged("csi_safe") is None
            assert health.wedged("csi_sap2000") is None
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

            sap_ok = await sap_tools.call(
                "csi_assign_frame_section",
                {"model": sap_key, "frame": "F1", "section": "C40"},
                op_id="op_sap2000",
                model=sap_key,
            )
            assert isinstance(sap_ok, SuccessEnvelope), sap_ok
            assert len(sap_written.items(sap_key)) == 1
            assert await sap_host.locate(sap_key) == sap_held
            assert (await sap_host.read_units(sap_key, sap_held.instance_id)).ok is True
            assert health.wedged("csi") == "op_etabs"

            rec = await etabs_tools.reconcile("csi_assign_frame_section", args, "op_etabs")
            assert rec.outcome == "applied"
            assert health.wedged("csi") is None

            await sap_host.close_started("csi_sap2000", [sap_held])
            assert sap_inspector.terminated == []
            await safe_host.close_started("csi_safe", [safe_held])
            assert safe_inspector.terminated == []
            await etabs_host.close_started("csi", [etabs_held])
            assert len(etabs_inspector.terminated) == 1

    anyio.run(body)
