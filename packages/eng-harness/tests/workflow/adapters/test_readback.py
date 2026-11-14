"""CSI read-back and `check_model` against the synthetic fake (plan 0002 T12b; spec 0002 AC24, sections 4.5.8, 4.6.2).

Edits go through `CsiToolPort`, which records each written item and marks the write on the host port; `check_model` then
reads every item back. The edits the "engineer" makes behind the harness are sent straight to the fake. The tolerance is
a value the test hands to `ReadBack`, as the workflow's basis value would be: the adapter holds none of its own.
Expected values are derived by hand: 250 mm written in `kN_mm_C` is 0.25 in the `kN_m_C` table, which reads back as
250 mm; the same 250 sent in `kN_m_C` is 250 m, which reads back as 250 000 mm (the x1000 case of AC24).
The adapter imports are inside the tests so a missing module fails the test.
"""

import json
import os
from pathlib import Path
from typing import Any

import anyio
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ModelStateStore, ResultStore, Workspace

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

from .test_csi_session_ops import ETABS_EXE, LaunchInspector
from .test_csi_state import _seed

HOST = HostInfo(program="ETABS", version="22.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0)
SHA = "d" * 64
CHECK = ServerCheck(
    server="csi", build="0123456789ab+fedcba987654", min_build="", fingerprint=SHA, expected_fingerprint=SHA, ok=True,
    reason=None,
)  # fmt: skip
TOLERANCE = 0.001  # a test input: the value a workflow's frozen basis would hand over
KIND = "issues.model_check/1"


class Binder:
    """The bound instance of the only model."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    async def binding(self, host_key: str, model: str | None, descriptor: ToolDescriptor) -> Binding:
        return Binding(target=HostTarget(product="ETABS", pid=self.pid), host=HOST, owned=True)

    def revision(self, model_id: str) -> int | None:
        return None


def _seeded(control: Path) -> None:
    seed = _seed()
    seed["frame_sections"] = [{"name": "C30"}, {"name": "C40"}]
    seed["area_sections"] = [{"name": "SL", "type": "slab"}, {"name": "SL20", "type": "slab"}]
    control.write_text(json.dumps({"faults": [], "seed": seed}))


def _summary(envelope: Any) -> dict[str, Any]:
    assert isinstance(envelope, SuccessEnvelope), envelope
    assert envelope.kind == KIND
    return dict(envelope.summary)


def _issues(envelope: Any) -> list[tuple[str, str, str, str]]:
    assert isinstance(envelope, SuccessEnvelope)
    rows = envelope.data["issues"]
    return [(i["severity"], i["code"], i["subject"]["kind"], i["subject"]["id"]) for i in rows]


def test_mismatch_detected(tmp_path: Path, make_config: Any, control: Path, store: ResultStore, run_dir: Path) -> None:
    """Items written through the port read back clean; a changed item, or a x1000 thickness, is `READBACK_MISMATCH`."""
    from eng_harness.adapters.csi._checks import ReadBack, WrittenItems

    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.csi._tools import CsiToolPort

    _seeded(control)
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"readback", clock)
    producer = Provenance(
        tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
    )
    config: ServersConfig = make_config()

    def value(name: str, number: float) -> dict[str, str]:
        record = store.put("harness.run_input/1", {"value": {name: number}}, producer)
        return {"$ref": f"{record.result_id}#/value/{name}"}

    async def body() -> None:
        workspace = Workspace(root=tmp_path / "idws", classification=LocationClass.LOCAL)
        states = ModelStateStore(workspace, clock)
        original = tmp_path / "original.EDB"
        original.write_bytes(b"model-v1")
        inspector = LaunchInspector(control)
        guard = ProcessGuard(inspector, run_dir, host_exes=[ETABS_EXE])
        locks = HostLocks(
            tmp_path / "locks", run_id="b466", engine=ProcessIdentity(os.getpid(), "t0", "python"), clock=clock
        )
        manager = ServerManager(config, run_dir, helpers=guard)
        written = WrittenItems()
        host = AdapterHostPort(
            identity=IdentityStore(workspace=workspace, states=states, ids=ids), states=states, sessions=manager,
            guard=guard, inspector=inspector, locks=locks, clock=clock, ids=ids, run_dir=run_dir, product="ETABS",
            program="ETABS", exe_name=ETABS_EXE, files={"m": original},
            readback=ReadBack(written=written, store=store, check=CHECK, tolerance_ratio=TOLERANCE),
        )  # fmt: skip
        async with manager:
            key = await host.working_copy("m", tmp_path / "copies")
            held = await host.locate(key)
            assert held is not None
            target = {"target": {"product": "ETABS", "pid": held.pid}}
            port = CsiToolPort(
                binder=Binder(held.pid), written=written, host=host, config=config, server="csi", caller=manager,
                store=store, ledger=WriteLedger(run_dir), clock=clock, ids=ids, check=CHECK,
            )  # fmt: skip
            count = 0

            async def write(tool: str, **arguments: Any) -> None:
                nonlocal count
                count += 1
                reply = await port.call(tool, {"model": key, **arguments}, op_id=f"op-{count}", model=key)
                assert isinstance(reply, SuccessEnvelope), reply

            async def engineer(tool: str, **arguments: Any) -> None:
                await manager.call("csi", "main", tool, {**target, **arguments}, CallEffect.WRITE)

            await write("csi_assign_frame_section", frame="F1", section="C40")
            await write("csi_assign_area_section", area="A1", section="SL20")
            await write("csi_define_wall_section", name="W1", material="C30", thickness_mm=value("thickness_mm", 250.0))
            await write("csi_set_frame_load_distributed", frame="F1", pattern="DEAD", w_kN_m=value("w_kN_m", 20.0))
            await write("csi_set_area_load_uniform", area="A1", pattern="DEAD", q_kPa=value("q_kPa", 8.0))
            await write("csi_add_load_pattern", name="SNOW1", type="snow", self_weight_ratio=value("w_ratio", 0.0))
            items = [{"case": {"case": "C1", "case_type": "load_combination"}, "scale_ratio": 1.0}]
            await write("csi_add_load_combo", name="C2", type="envelope", items=items)
            await write("csi_set_point_restraint", joint="P1", ux=True, uy=True, uz=True, rx=False, ry=False, rz=False)

            clean = await host.check_model(key)
            assert _summary(clean) == {"errors": 0, "warnings": 0, "infos": 0, "clean": True}
            assert _issues(clean) == []

            await write("csi_define_wall_section", name="W1", material="C30", thickness_mm=value("thickness_mm", 300.0))
            await write("csi_assign_frame_section", frame="F1", section="C30")
            await write("csi_set_area_load_uniform", area="A1", pattern="LIVE", q_kPa=value("q_kPa", 4.0))
            await engineer("csi_define_wall_section", name="W1", material="C30", thickness=300.0, units="kN_m_C")
            await engineer("csi_assign_frame_section", name="F1", section="C40")

            bad = await host.check_model(key)
            assert _summary(bad) == {"errors": 2, "warnings": 0, "infos": 0, "clean": False}
            assert _issues(bad) == [
                ("error", "READBACK_MISMATCH", "section", "W1"),
                ("error", "READBACK_MISMATCH", "frame", "F1"),
            ]
            thickness = bad.data["issues"][0]["message"]
            assert "300000.0" in thickness  # reads 300 000 mm
            assert "300.0" in thickness  # requested 300 mm

            again = await host.check_model(key)  # the items of the last check are not read back twice
            assert _summary(again)["clean"] is True

    anyio.run(body)
