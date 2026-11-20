"""SAP2000 edits: add-frame name from reply, typed read-back, SP-4 gaps (plan 0012 T5; spec 0012 AC11, AC13).

Adapter imports sit inside the tests so a missing module fails the test. Lengths are millimetres under `kN_mm_C`
(spec 0012 section 5); expected host names and geometry come from the synthetic fake (spec 0012 section 4.1).
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.model import CombinationItem, CombinationType, PatternType
from eng_contract.store import LocationClass, ModelStateStore, ResultStore, Workspace
from pydantic import JsonValue

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.errors import HarnessCode, NotImplementedGap
from eng_harness.ports import ServerCheck
from eng_harness.servers import ServerManager, ServersConfig
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

from .test_sap2000_session_ops import SAP2000_EXE, _Sap2000Inspector
from .test_sap2000_state import _seed

ConfigFactory = Callable[..., ServersConfig]
_START = 1_700_000_000_000
SHA = "d" * 64
CHECK = ServerCheck(
    server="csi_sap2000",
    build="0123456789ab+fedcba987654",
    min_build="",
    fingerprint=SHA,
    expected_fingerprint=SHA,
    ok=True,
    reason=None,
)
TOLERANCE = 0.001
HOST = HostInfo(program="SAP2000", version="26.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0)


def _issues(envelope: Any) -> list[tuple[str, str, str, str]]:
    assert isinstance(envelope, SuccessEnvelope)
    data: Any = envelope.data
    return [(i["severity"], i["code"], i["subject"]["kind"], i["subject"]["id"]) for i in data["issues"]]


@dataclass
class Rig:
    host: Any
    port: Any
    manager: ServerManager
    key: str
    store: ResultStore
    pid: int
    count: int = 0

    def value(self, name: str, number: float) -> dict[str, str]:
        producer = Provenance(
            tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
        )
        record = self.store.put("harness.run_input/1", {"value": {name: number}}, producer)
        return {"$ref": f"{record.result_id}#/value/{name}"}

    async def write(self, tool: str, **arguments: Any) -> SuccessEnvelope:
        self.count += 1
        reply = await self.port.call(tool, {"model": self.key, **arguments}, op_id=f"op-{self.count}", model=self.key)
        assert isinstance(reply, SuccessEnvelope), reply
        return reply


class Binder:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    async def binding(self, host_key: str, model: str | None, descriptor: Any) -> Binding:
        return Binding(target=HostTarget(product="SAP2000", pid=self.pid), host=HOST, owned=True)

    def revision(self, model_id: str) -> int | None:
        return None


@asynccontextmanager
async def _rig(
    config: ServersConfig, control: Path, store: ResultStore, tmp_path: Path, *, seed: dict[str, Any] | None = None
) -> AsyncIterator[Rig]:
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.csi._checks import ReadBack, WrittenItems
    from eng_harness.adapters.csi._reconcile import CsiReconciler
    from eng_harness.adapters.csi._tools import CsiToolPort

    control.write_text(json.dumps({"faults": [], "seed": seed if seed is not None else _seed(), "product": "SAP2000"}))
    clock = FixedClock(_START, 1)
    ids = SeededIdSource(b"sap-edits", clock)
    run_dir = tmp_path / "run"
    inspector = _Sap2000Inspector(control)
    guard = ProcessGuard(inspector, run_dir, host_exes=[SAP2000_EXE])
    locks = HostLocks(
        tmp_path / "locks", run_id="b249", engine=ProcessIdentity(os.getpid(), "t0", "python"), clock=clock
    )
    base = config.servers["csi"].model_copy(update={"product": "SAP2000", "host_key": "csi_sap2000"})
    sap_config = ServersConfig(servers={"csi_sap2000": base})
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    original = tmp_path / "frame.SDB"
    original.write_bytes(b"sap2000-model-v1")
    written = WrittenItems()
    readback = ReadBack(written=written, store=store, check=CHECK, tolerance_ratio=TOLERANCE)
    async with ServerManager(sap_config, run_dir, helpers=guard) as manager:
        host = AdapterHostPort(
            identity=IdentityStore(workspace=workspace, states=states, ids=ids),
            states=states,
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
            readback=readback,
        )
        key = await host.working_copy("m", run_dir / "copies")
        held = await host.locate(key)
        assert held is not None
        assert held.pid is not None
        pid = held.pid
        binder = Binder(pid)
        port = CsiToolPort(
            binder=binder,
            config=sap_config,
            server="csi_sap2000",
            caller=manager,
            store=store,
            ledger=WriteLedger(run_dir),
            clock=clock,
            ids=ids,
            check=CHECK,
            errors=CsiErrorMapper(ids),
            written=written,
            wrote=host.wrote,
            reconciler=CsiReconciler(product="SAP2000", tolerance_ratio=TOLERANCE),
        )
        yield Rig(host, port, manager, key, store, pid)


@pytest.fixture
def store(tmp_path: Path) -> ResultStore:
    from eng_harness._kinds import HARNESS_KINDS

    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"sap-edits-store", clock)
    workspace = Workspace(root=tmp_path / "ws-store", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS, ids, clock)


def _build(tool: str, model: Any, units: str | None = None) -> dict[str, JsonValue]:
    from eng_harness.adapters.csi import csi_allowlist
    from eng_harness.adapters.csi._tools import edit_builders

    binding = Binding(target=HostTarget(product="SAP2000", pid=4242), units_system=units)
    return edit_builders()[tool](model, csi_allowlist().for_product("SAP2000").descriptor(tool), binding)


def test_add_frame_name_from_reply(
    make_config: ConfigFactory, control: Path, store: ResultStore, tmp_path: Path
) -> None:
    """AC11: add-frame uses the reply name; section must exist; read-back compares points and section."""

    async def body() -> None:
        from eng_harness.adapters.csi.products import _sap2000_edits as edits

        edits.clear_name_map()
        # Spec 0012 section 6: empty section list → NOT_FOUND field section before any host call.
        with pytest.raises(ContractError) as missing:
            edits.require_section("C300", set())
        assert missing.value.detail.code is ErrorCode.NOT_FOUND
        assert missing.value.detail.field == "section"

        seed = _seed(frames=1)
        async with _rig(make_config(), control, store, tmp_path, seed=seed) as rig:
            reply = await rig.write(
                "csi_add_frame_by_coord",
                name="RequestedCol",
                section="C300",
                xi_mm=rig.value("xi_mm", 1000.0),
                yi_mm=rig.value("yi_mm", 2000.0),
                zi_mm=rig.value("zi_mm", 0.0),
                xj_mm=rig.value("xj_mm", 1000.0),
                yj_mm=rig.value("yj_mm", 2000.0),
                zj_mm=rig.value("zj_mm", 3000.0),
            )
            payload = reply.data if isinstance(reply.data, dict) else store.payload(reply.result_id)
            assert isinstance(payload, dict)
            value = payload.get("value")
            assert isinstance(value, dict)
            host_name = value["name"]
            assert host_name == "Frame2"
            assert host_name != "RequestedCol"
            assert edits.name_map().get("RequestedCol") == "Frame2"

            checked = await rig.host.check_model(rig.key)
            codes = [code for _, code, _, _ in _issues(checked)]
            assert "READBACK_MISMATCH" not in codes
            held = await rig.host.locate(rig.key)
            assert held is not None
            assert held.instance_id is not None
            await rig.host.model_state(rig.key, held.instance_id)
            read = rig.host.last_read(rig.key)
            assert read is not None
            frames = read.payloads["model.frame_placements/1"]
            found = next(frame for frame in frames.frames if frame.id == "Frame2")
            assert found.section == "C300"
            assert (found.i.x_mm, found.i.y_mm, found.i.z_mm) == (1000.0, 2000.0, 0.0)
            assert (found.j.x_mm, found.j.y_mm, found.j.z_mm) == (1000.0, 2000.0, 3000.0)

            args = _build(
                "csi_add_frame_by_coord",
                edits.AddFrameByCoordArgs(
                    model="m",
                    name="X",
                    section="C300",
                    xi_mm=0.0,
                    yi_mm=0.0,
                    zi_mm=0.0,
                    xj_mm=0.0,
                    yj_mm=0.0,
                    zj_mm=1000.0,
                ),
                units="kN_mm_C",
            )
            assert args["section"] == "C300"
            assert args["start"] == [0.0, 0.0, 0.0]
            assert args["end"] == [0.0, 0.0, 1000.0]

    anyio.run(body)


def test_typed_readback_edits(make_config: ConfigFactory, control: Path, store: ResultStore, tmp_path: Path) -> None:
    """AC13: assign frame section, add area, pattern and combination use the 0002 argument mapping."""

    async def body() -> None:
        from eng_harness.adapters.csi import _edits as base
        from eng_harness.adapters.csi.products import _sap2000_edits as edits

        async with _rig(make_config(), control, store, tmp_path) as rig:
            await rig.write("csi_assign_frame_section", frame="F1", section="C400")
            reply = await rig.write(
                "csi_add_area_by_coord",
                name="A2",
                section="SLAB1",
                points=[
                    [0.0, 0.0, 0.0],
                    [1000.0, 0.0, 0.0],
                    [1000.0, 1000.0, 0.0],
                    [0.0, 1000.0, 0.0],
                ],
            )
            assert isinstance(reply, SuccessEnvelope)
            await rig.write(
                "csi_add_load_pattern",
                name="LIVE1",
                type="live",
                self_weight_ratio=rig.value("sw_ratio", 0.0),
            )
            await rig.write(
                "csi_add_load_combo",
                name="C2",
                type="linear_add",
                items=[{"case": {"case": "DEAD", "case_type": "load_pattern"}, "scale_ratio": 1.4}],
            )
            await rig.write("csi_delete_load_combo", name="C1")
            checked = await rig.host.check_model(rig.key)
            codes = {code for _, code, _, _ in _issues(checked)}
            assert "READBACK_MISMATCH" not in codes

        assert _build(
            "csi_assign_frame_section", base.AssignFrameSectionArgs(model="m", frame="F1", section="C400")
        ) == {"name": "F1", "section": "C400"}
        area = edits.AddAreaByCoordArgs(
            model="m",
            name="A2",
            section="SLAB1",
            points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
        )
        built = _build("csi_add_area_by_coord", area, units="kN_mm_C")
        assert built["section"] == "SLAB1"
        assert built["points"] == [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]]
        pattern = base.AddLoadPatternArgs(model="m", name="P", type=PatternType.LIVE, self_weight_ratio=1.0)
        assert _build("csi_add_load_pattern", pattern) == {
            "name": "P",
            "type": "Live",
            "self_weight": 1.0,
        }
        combo = base.AddLoadComboArgs(
            model="m",
            name="C2",
            type=CombinationType.LINEAR_ADD,
            items=[
                CombinationItem.model_validate(
                    {"case": {"case": "DEAD", "case_type": "load_pattern"}, "scale_ratio": 1.4}
                )
            ],
        )
        assert _build("csi_add_load_combo", combo)["combo_type"] == 0

    anyio.run(body)


def test_pattern_partial_readback(
    make_config: ConfigFactory, control: Path, store: ResultStore, tmp_path: Path
) -> None:
    """AC13: a pattern is read back by name only; READBACK_PARTIAL warns for type and self-weight."""

    async def body() -> None:
        async with _rig(make_config(), control, store, tmp_path) as rig:
            await rig.write(
                "csi_add_load_pattern",
                name="SNOW1",
                type="snow",
                self_weight_ratio=rig.value("sw_ratio", 0.25),
            )
            checked = await rig.host.check_model(rig.key)
            issues = _issues(checked)
            partial = [item for item in issues if item[1] == "READBACK_PARTIAL"]
            assert partial, issues
            assert all(item[0] == "warning" for item in partial)
            messages = [row["message"] for row in checked.data["issues"] if row["code"] == "READBACK_PARTIAL"]
            assert any("type" in msg and "self-weight" in msg for msg in messages)

    anyio.run(body)


def test_table_readback_edits_are_gap() -> None:
    """AC13: edits whose read-back needs a table raise NotImplementedGap SP-4."""
    from eng_harness.adapters.csi.products import _sap2000_edits as edits

    for kind in (
        "set_frame_load_distributed",
        "set_area_load_uniform",
        "set_point_restraint",
        "set_point_load",
        "assign_area_section",
    ):
        with pytest.raises(NotImplementedGap) as caught:
            edits.refuse_table_edit(kind)
        assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
        assert caught.value.evidence == ("SP-4",)
