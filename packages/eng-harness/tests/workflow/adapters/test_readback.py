"""CSI read-back and `check_model` against the synthetic fake (plan 0002 T12b; spec 0002 AC24, sections 4.5.8, 4.6.2).

Edits go through `CsiToolPort`, which records each written item and marks the write on the host port; `check_model` then
reads every item back. The edits the "engineer" makes behind the harness are sent straight to the fake. The tolerance is
a value the test hands to `ReadBack`, as the workflow's basis value would be: the adapter holds none of its own.
Expected values are derived by hand: 250 mm written in `kN_mm_C` is 0.25 in the `kN_m_C` table, which reads back as
250 mm; the same 250 sent in `kN_m_C` is 250 m, which reads back as 250 000 mm (the x1000 case of AC24). The pure
helpers are tested on states built by the T11 mappers, with a tolerance of 0.25 so that every boundary is exact in
binary: 8.0 may read back in [6.0, 10.0].
"""

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode, Precondition, WarningCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.quantity import Quantity
from eng_contract.store import LocationClass, ModelStateStore, ResultStore, Workspace
from eng_contract.verdicts import Subject, SubjectKind
from pydantic import BaseModel

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
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
FRAME, AREA, SECTION, PATTERN = SubjectKind.FRAME, SubjectKind.AREA, SubjectKind.SECTION, SubjectKind.LOAD_PATTERN
COMBINATION, JOINT = SubjectKind.LOAD_COMBINATION, SubjectKind.JOINT


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
    data: Any = envelope.data
    return [(i["severity"], i["code"], i["subject"]["kind"], i["subject"]["id"]) for i in data["issues"]]


@dataclass
class Rig:
    """The wired host port and tool port over the fake, with the engineer's hand."""

    host: Any
    port: Any
    manager: ServerManager
    key: str
    written: Any
    marks: list[str]
    store: ResultStore
    pid: int
    count: int = 0

    def value(self, name: str, number: float) -> dict[str, str]:
        producer = Provenance(
            tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
        )
        record = self.store.put("harness.run_input/1", {"value": {name: number}}, producer)
        return {"$ref": f"{record.result_id}#/value/{name}"}

    async def send(self, tool: str, **arguments: Any) -> Any:
        self.count += 1
        return await self.port.call(tool, {"model": self.key, **arguments}, op_id=f"op-{self.count}", model=self.key)

    async def write(self, tool: str, **arguments: Any) -> None:
        reply = await self.send(tool, **arguments)
        assert isinstance(reply, SuccessEnvelope), reply

    async def engineer(self, tool: str, **arguments: Any) -> None:
        target = {"target": {"product": "ETABS", "pid": self.pid}}
        await self.manager.call("csi", "main", tool, {**target, **arguments}, CallEffect.WRITE)


@asynccontextmanager
async def _rig(
    tmp_path: Path, config: ServersConfig, control: Path, store: ResultStore, run_dir: Path,
    tolerance: float | None = TOLERANCE, *, wired: bool = True, opened: bool = True,
) -> AsyncIterator[Rig]:  # fmt: skip
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.csi._checks import ReadBack, WrittenItems
    from eng_harness.adapters.csi._tools import CsiToolPort

    _seeded(control)
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"readback", clock)
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
    readback = ReadBack(written=written, store=store, check=CHECK, tolerance_ratio=tolerance) if wired else None
    host = AdapterHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids), states=states, sessions=manager,
        guard=guard, inspector=inspector, locks=locks, clock=clock, ids=ids, run_dir=run_dir, product="ETABS",
        program="ETABS", exe_name=ETABS_EXE, files={"m": original}, readback=readback,
    )  # fmt: skip
    marks: list[str] = []

    def wrote(key: str) -> None:
        marks.append(key)
        host.wrote(key)

    async with manager:
        key, pid = "m", 0
        if opened:
            key = await host.working_copy("m", tmp_path / "copies")
            held = await host.locate(key)
            assert held is not None
            pid = held.pid
        port = CsiToolPort(
            binder=Binder(pid), written=written, wrote=wrote, config=config, server="csi", caller=manager,
            store=store, ledger=WriteLedger(run_dir), clock=clock, ids=ids, check=CHECK, errors=CsiErrorMapper(ids),
        )  # fmt: skip
        yield Rig(host, port, manager, key, written, marks, store, pid)


def test_mismatch_detected(tmp_path: Path, make_config: Any, control: Path, store: ResultStore, run_dir: Path) -> None:
    """Items written through the port read back clean; a changed item, or a x1000 thickness, is `READBACK_MISMATCH`."""

    async def body() -> None:
        async with _rig(tmp_path, make_config(), control, store, run_dir) as rig:
            await rig.write("csi_assign_frame_section", frame="F1", section="C40")
            await rig.write("csi_assign_area_section", area="A1", section="SL20")
            wall = rig.value("thickness_mm", 250.0)
            await rig.write("csi_define_wall_section", name="W1", material="C30", thickness_mm=wall)
            load = rig.value("w_kN_m", 20.0)
            await rig.write("csi_set_frame_load_distributed", frame="F1", pattern="DEAD", w_kN_m=load)
            await rig.write("csi_set_area_load_uniform", area="A1", pattern="DEAD", q_kPa=rig.value("q_kPa", 8.0))
            ratio = rig.value("w_ratio", 0.0)
            await rig.write("csi_add_load_pattern", name="SNOW1", type="snow", self_weight_ratio=ratio)
            items = [{"case": {"case": "DEAD", "case_type": "load_pattern"}, "scale_ratio": 1.2}]
            await rig.write("csi_add_load_combo", name="C2", type="envelope", items=items)
            flags = {"ux": True, "uy": True, "uz": True, "rx": False, "ry": False, "rz": False}
            await rig.write("csi_set_point_restraint", joint="P1", **flags)

            clean = await rig.host.check_model(rig.key)
            assert _summary(clean) == {"errors": 0, "warnings": 0, "infos": 0, "clean": True}
            assert _issues(clean) == []

            wall = rig.value("thickness_mm", 300.0)
            await rig.write("csi_define_wall_section", name="W1", material="C30", thickness_mm=wall)
            await rig.write("csi_assign_frame_section", frame="F1", section="C30")
            await rig.write("csi_set_area_load_uniform", area="A1", pattern="DEAD", q_kPa=rig.value("q_kPa", 4.0))
            await rig.engineer("csi_define_wall_section", name="W1", material="C30", thickness=300.0, units="kN_m_C")
            await rig.engineer("csi_assign_frame_section", name="F1", section="C40")

            bad = await rig.host.check_model(rig.key)
            assert _summary(bad) == {"errors": 2, "warnings": 0, "infos": 0, "clean": False}
            assert _issues(bad) == [
                ("error", "READBACK_MISMATCH", "section", "W1"),
                ("error", "READBACK_MISMATCH", "frame", "F1"),
            ]
            thickness = bad.data["issues"][0]["message"]
            assert "300000.0" in thickness  # reads 300 000 mm
            assert "300.0" in thickness  # requested 300 mm

            again = await rig.host.check_model(rig.key)  # the items of the last check are not read back twice
            assert _summary(again)["clean"] is True

    anyio.run(body)


def test_envelope_and_marks(tmp_path: Path, make_config: Any, control: Path, store: ResultStore, run_dir: Path) -> None:
    """The check is a stored result with the build and the model's identity; each write is marked on the port."""

    async def body() -> None:
        async with _rig(tmp_path, make_config(), control, store, run_dir) as rig:
            await rig.write("csi_assign_frame_section", frame="F1", section="C40")
            await rig.write("csi_assign_frame_section", frame="F1", section="C30")
            assert rig.marks == ["m@copy", "m@copy"]
            envelope = await rig.host.check_model(rig.key)
            assert isinstance(envelope, SuccessEnvelope)
            assert envelope.complete is True
            assert envelope.warnings == []
            assert envelope.provenance.tool == "harness/check_model"
            assert envelope.provenance.tool_version == CHECK.build
            assert envelope.provenance.inputs == {}
            host = envelope.provenance.host
            assert host is not None
            assert (host.program, host.version, host.model_revision) == ("ETABS", "22.0.0", 0)
            assert store.get(envelope.result_id).payload == envelope.data  # the issues are the stored payload

    anyio.run(body)


def test_failed_write_is_not_recorded(
    tmp_path: Path, make_config: Any, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """A write the host refuses is not marked and not read back; the next write is paired with its own item."""
    from eng_harness.adapters.csi._checks import Expect

    async def body() -> None:
        async with _rig(tmp_path, make_config(), control, store, run_dir) as rig:
            refused = await rig.send("csi_assign_frame_section", frame="NOPE", section="C40")
            assert not refused.ok
            assert rig.marks == []
            assert rig.written.items(rig.key) == []
            await rig.write("csi_assign_frame_section", frame="F1", section="C40")
            assert rig.marks == [rig.key]
            subject = Subject(kind=FRAME, id="F1")
            assert rig.written.items(rig.key) == [Expect("frame_section", subject, {"section": "C40"})]
            invalid = await rig.send("csi_assign_frame_section", frame="F1")  # no section: nothing is built or noted
            assert not invalid.ok
            assert rig.marks == [rig.key]
            assert len(rig.written.items(rig.key)) == 1

    anyio.run(body)


def test_no_tolerance_is_unavailable(
    tmp_path: Path, make_config: Any, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """Without a tolerance a quantity is `READBACK_UNAVAILABLE`; a name still compares exactly."""

    async def body() -> None:
        async with _rig(tmp_path, make_config(), control, store, run_dir, None) as rig:
            await rig.write("csi_assign_frame_section", frame="F1", section="C40")
            wall = rig.value("thickness_mm", 250.0)
            await rig.write("csi_define_wall_section", name="W1", material="C30", thickness_mm=wall)
            checked = await rig.host.check_model(rig.key)
            assert _issues(checked) == [("error", "READBACK_UNAVAILABLE", "section", "W1")]
            message = checked.data["issues"][0]["message"]
            assert message == "no read-back tolerance (checks.readback_relative_tolerance_ratio)"

    anyio.run(body)


def test_outside_edit_warning_is_drained(
    tmp_path: Path, make_config: Any, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """The warning of an outside edit found by a read comes with the next check, once."""

    async def body() -> None:
        async with _rig(tmp_path, make_config(), control, store, run_dir) as rig:
            held = await rig.host.locate(rig.key)
            await rig.host.model_state(rig.key, held.instance_id)
            await rig.engineer("csi_assign_frame_section", name="F1", section="C40")
            await rig.host.model_state(rig.key, held.instance_id)
            first = await rig.host.check_model(rig.key)
            assert [(w.code, w.message) for w in first.warnings] == [
                (WarningCode.MODEL_CHANGED_OUTSIDE, "m@copy changed outside the harness since the last read")
            ]
            assert _summary(first)["clean"] is True
            assert (await rig.host.check_model(rig.key)).warnings == []

    anyio.run(body)


def test_unwired(tmp_path: Path, make_config: Any, control: Path, store: ResultStore, run_dir: Path) -> None:
    """A port wired without `readback` cannot check: an internal error with an incident id."""

    async def body() -> None:
        async with _rig(tmp_path, make_config(), control, store, run_dir, wired=False) as rig:
            with pytest.raises(ContractError) as unwired:
                await rig.host.check_model(rig.key)
            assert unwired.value.detail.code is ErrorCode.INTERNAL
            assert unwired.value.detail.message == "no read-back wiring"
            assert unwired.value.detail.incident_id is not None

    anyio.run(body)


def test_not_open(tmp_path: Path, make_config: Any, control: Path, store: ResultStore, run_dir: Path) -> None:
    """A model that is not open has nothing to read back: `PRECONDITION_FAILED` (`model_open`)."""

    async def body() -> None:
        async with _rig(tmp_path, make_config(), control, store, run_dir, opened=False) as rig:
            with pytest.raises(ContractError) as closed:
                await rig.host.check_model("m")
            assert closed.value.detail.code is ErrorCode.PRECONDITION_FAILED
            assert closed.value.detail.precondition is Precondition.model_open

    anyio.run(body)


def _snap(**given: Any) -> Any:
    """A `Snapshot` of states the T11 mappers build from host rows; `given` names the rows of each part."""
    from eng_harness.adapters.csi import _replies as r
    from eng_harness.adapters.csi._checks import Snapshot
    from eng_harness.adapters.csi._state import StateRead
    from eng_harness.adapters.csi.products import profile

    units = given.get("units", "kN_m_C")
    loads = r.load_set(
        given.get("patterns", []), given.get("combos", []), [], [], given.get("frame_loads", []),
        given.get("area_loads", []), units,
    )  # fmt: skip
    payloads: dict[str, BaseModel] = {
        "model.frame_placements/1": r.frames(given.get("frames", []), "kN_mm_C"),
        "model.area_placements/1": r.areas(given.get("areas", []), "kN_mm_C", {}),
        "model.load_set/1": loads,
        "model.joint_restraints/1": r.restraints(given.get("restraints", [])),
    }
    status = r.CsiModelStatus(units=units, locked=given.get("locked", False), file_name="m.EDB")
    return Snapshot(
        StateRead(payloads, status, "0" * 64), profile("ETABS"), set(given.get("frame_sections", [])),
        set(given.get("area_sections", [])), given.get("tables", {}),
    )  # fmt: skip


def _frame(name: str, section: str) -> dict[str, Any]:
    return {"name": name, "point1": [0.0, 0.0, 0.0], "point2": [0.0, 0.0, 3000.0], "section": section}


def _area(name: str, section: str) -> dict[str, Any]:
    return {"name": name, "points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], "section": section}


def _load(frame: str, value: float) -> dict[str, Any]:
    return {"Frame": frame, "LoadPattern": "DEAD", "Value": value}


def _one(item: Any, snap: Any, tolerance: float | None = 0.25) -> tuple[str, str, str] | None:
    from eng_harness.adapters.csi._checks import compare

    issue = compare(item, snap, tolerance)
    return None if issue is None else (issue.severity.value, issue.code, issue.message)


def _wanted_load(want: float) -> Any:
    from eng_harness.adapters.csi._checks import Expect

    return Expect("frame_load_table", Subject(kind=FRAME, id="F1", case="DEAD"), {"w_kN_m": want})


@pytest.mark.parametrize(
    ("read", "mismatch"),
    [(8.0, False), (10.0, False), (6.0, False), (10.5, True), (5.5, True)],
)
def test_tolerance_boundary(read: float, mismatch: bool) -> None:
    """A quantity may differ by `tolerance * |wanted|`: the boundary passes, anything beyond it does not."""
    snap = _snap(patterns=[{"name": "DEAD", "type": "Dead"}], frame_loads=[_load("F1", read)])
    issue = _one(_wanted_load(8.0), snap)
    if mismatch:
        assert issue == ("error", "READBACK_MISMATCH", f"F1 reads {{'w_kN_m': {read}}}, requested {{'w_kN_m': 8.0}}")
    else:
        assert issue is None


def test_differs() -> None:
    """A float must be within the tolerance, anything else equal; a field not read, or not a number, differs."""
    from eng_harness.adapters.csi._checks import _differs

    assert _differs({"x": 10.0}, {"x": 8.0}, 0.25) is False
    assert _differs({"x": 10.5}, {"x": 8.0}, 0.25) is True
    assert _differs({"x": 5.5}, {"x": 8.0}, 0.25) is True
    assert _differs({"x": float("nan")}, {"x": 8.0}, 0.25) is True  # a NaN is never within a tolerance
    assert _differs({"x": 9}, {"x": 8.0}, 0.25) is False  # an integer is a number
    assert _differs({}, {"x": 8.0}, 0.25) is True  # not read
    assert _differs({"x": "8.0"}, {"x": 8.0}, 0.25) is True  # not a number
    assert _differs({"x": True}, {"x": True}, 0.0) is False
    assert _differs({"x": False}, {"x": True}, 0.0) is True
    assert _differs({"x": "C40", "y": 1.0}, {"x": "C40", "y": 1.0}, 0.0) is False
    assert _differs({"x": ["A", "B"]}, {"x": ["A"]}, 0.0) is True


def test_zero_is_exact_and_no_tolerance_cases() -> None:
    """A wanted zero allows no difference; an absent item is a mismatch even without a tolerance."""
    from eng_harness.adapters.csi._checks import Expect

    zero = Expect("load_pattern", Subject(kind=PATTERN, id="SNOW1"), {"type": "snow", "self_weight_ratio": 0.0})
    exact = _snap(patterns=[{"name": "SNOW1", "type": "Snow", "self_weight": 0.0}])
    assert _one(zero, exact) is None
    off = _snap(patterns=[{"name": "SNOW1", "type": "Snow", "self_weight": 0.001}])
    issue = _one(zero, off)
    assert issue is not None
    assert issue[1] == "READBACK_MISMATCH"
    snap = _snap(patterns=[{"name": "DEAD", "type": "Dead"}])  # no frame load rows
    assert _one(_wanted_load(8.0), snap, None) == ("error", "READBACK_MISMATCH", "F1 is absent")
    snap = _snap(patterns=[{"name": "DEAD", "type": "Dead"}], frame_loads=[_load("F1", 8.0)])
    unavailable = ("error", "READBACK_UNAVAILABLE", "no read-back tolerance (checks.readback_relative_tolerance_ratio)")
    assert _one(_wanted_load(8.0), snap, None) == unavailable
    assert _one(_wanted_load(8.0), snap, 0.25) is None


def test_exact_fields_and_removal() -> None:
    """Names, types and flags are exact; a deleted combination must be gone; a missing item is a mismatch."""
    from eng_harness.adapters.csi._checks import Expect

    frame = Expect("frame_section", Subject(kind=FRAME, id="F1"), {"section": "C40"})
    other = "F1 reads {'section': 'C30'}, requested {'section': 'C40'}"
    assert _one(frame, _snap(frames=[_frame("F1", "C30")]), None) == ("error", "READBACK_MISMATCH", other)
    assert _one(frame, _snap(frames=[_frame("F1", "C40")]), None) is None
    assert _one(frame, _snap(frames=[_frame("F2", "C40")]), None) == ("error", "READBACK_MISMATCH", "F1 is absent")
    restraint = Expect("restraint_table", Subject(kind=JOINT, id="P1"), {"ux": True, "rz": False})
    row = {"UniqueName": "P1", "Ux": True, "Uy": False, "Uz": False, "Rx": False, "Ry": False, "Rz": True}
    flags = "P1 reads {'ux': True, 'rz': True}, requested {'ux': True, 'rz': False}"
    assert _one(restraint, _snap(restraints=[row]), None) == ("error", "READBACK_MISMATCH", flags)
    assert _one(restraint, _snap(restraints=[row | {"Rz": False}]), None) is None
    combo = {"name": "C1", "type": 0, "items": [{"name": "DEAD", "factor": 1.2, "kind": "case"}]}
    gone = Expect("load_combo", Subject(kind=COMBINATION, id="C1"), None)
    patterns = [{"name": "DEAD", "type": "Dead"}]
    assert _one(gone, _snap(patterns=patterns, combos=[combo]), None) == (
        "error",
        "READBACK_MISMATCH",
        "C1 is still present",
    )
    assert _one(gone, _snap(patterns=patterns), None) is None


def test_combination_fields() -> None:
    """A combination compares its type, its item names (any order) and its factors within the tolerance."""
    from eng_harness.adapters.csi._checks import Expect, _factors

    patterns = [{"name": "DEAD", "type": "Dead"}, {"name": "LIVE", "type": "Live"}]

    def row(*parts: tuple[str, float], kind: int = 0) -> dict[str, Any]:
        return {"name": "C1", "type": kind, "items": [{"name": n, "factor": f, "kind": "case"} for n, f in parts]}

    want = _factors("linear_add", [("LIVE", 1.6), ("DEAD", 1.2)])
    assert want == {"type": "linear_add", "items": ["DEAD", "LIVE"], "factor 0": 1.2, "factor 1": 1.6}
    item = Expect("load_combo", Subject(kind=COMBINATION, id="C1"), want)

    def read(*parts: tuple[str, float], kind: int = 0) -> tuple[str, str, str] | None:
        return _one(item, _snap(patterns=patterns, combos=[row(*parts, kind=kind)]))

    assert read(("LIVE", 1.6), ("DEAD", 1.2)) is None  # the order of the items is free
    assert read(("DEAD", 1.4), ("LIVE", 1.6)) is None  # 0.2 off 1.2 is within the 0.3 allowed
    assert read(("DEAD", 1.6), ("LIVE", 1.6)) is not None  # 0.4 off is beyond it
    assert read(("DEAD", 1.2), ("LIVE", 1.6), ("LIVE", 1.0)) is not None  # an item more
    assert read(("DEAD", 1.2), ("LIVE", 1.6), kind=1) is not None  # another type


def test_table_helpers() -> None:
    """A wall thickness reads in the model's units; a table or column that is not there is unavailable."""
    from eng_harness.adapters.csi._checks import Expect

    wall = Expect("wall_section_table", Subject(kind=SECTION, id="W1"), {"thickness_mm": 250.0})
    metres = {"wall_section": [{"Name": "W1", "Thickness": 0.25}]}  # kN_m_C: 0.25 m is 250 mm
    assert _one(wall, _snap(tables=metres)) is None
    assert _one(wall, _snap(units="kN_mm_C", tables={"wall_section": [{"Name": "W1", "Thickness": 250.0}]})) is None
    wrong = _snap(tables={"wall_section": [{"Name": "W1", "Thickness": 250.0}]})  # 250 m reads as 250 000 mm
    text = "W1 reads {'thickness_mm': 250000.0}, requested {'thickness_mm': 250.0}"
    assert _one(wall, wrong) == ("error", "READBACK_MISMATCH", text)
    unavailable = ("error", "READBACK_UNAVAILABLE", "the read-back of wall_section_table could not be read")
    assert _one(wall, _snap()) == unavailable  # the table was not read
    assert _one(wall, _snap(tables={"wall_section": [{"Name": "W1"}]})) == unavailable  # no Thickness column
    assert _one(wall, _snap(tables={"wall_section": [{"Name": "W1", "Thickness": "x"}]})) == unavailable
    assert _one(wall, _snap(tables={"wall_section": []})) == ("error", "READBACK_MISMATCH", "W1 is absent")
    area = Expect("area_section_table", Subject(kind=AREA, id="A1"), {"section": "SL20"})
    assert _one(area, _snap(tables={"area_section": [{"UniqueName": "A1", "Section": "SL20"}]}), None) is None
    differs = _snap(tables={"area_section": [{"UniqueName": "A1", "Section": "SL"}]})
    text = "A1 reads {'section': 'SL'}, requested {'section': 'SL20'}"
    assert _one(area, differs, None) == ("error", "READBACK_MISMATCH", text)


def test_snapshot_reads() -> None:
    """The section lists and the two tables are read at the cap, for the target; a bad table is left out."""
    from eng_harness.adapters.csi._checks import snapshot
    from eng_harness.adapters.csi._state import LIST_LIMIT
    from eng_harness.adapters.csi.products import profile

    calls: list[tuple[str, str, dict[str, Any], str]] = []
    area_table, wall_table = "Area Assignments - Section Properties", "Wall Property Definitions - Specified"
    tables = {area_table: [{"UniqueName": "A1", "Section": "SL"}], wall_table: [{"Name": "W1"}]}  # no Thickness

    async def rows(tool: str, name: str, arguments: dict[str, Any], what: str) -> list[dict[str, Any]]:
        calls.append((tool, name, arguments, what))
        if tool == "csi_db_table_read":
            return tables[arguments["table"]]
        return [{"name": "C30"}, {"name": "C40"}] if tool == "csi_list_frame_sections" else [{"name": "SL"}]

    async def read(reader: Any) -> Any:
        return await snapshot(reader, target, _snap().state, profile("ETABS"))

    target = {"target": {"product": "ETABS", "pid": 7}}
    snap = anyio.run(read, rows)
    assert snap.frame_sections == {"C30", "C40"}
    assert snap.area_sections == {"SL"}
    assert snap.tables == {"area_section": tables[area_table]}
    limit = {"limit": LIST_LIMIT}
    assert calls == [
        ("csi_list_frame_sections", "items", {**target, **limit}, "csi_list_frame_sections"),
        ("csi_list_area_sections", "items", {**target, **limit}, "csi_list_area_sections"),
        ("csi_db_table_read", "rows", {**target, "table": area_table, "row_limit": LIST_LIMIT}, area_table),
        ("csi_db_table_read", "rows", {**target, "table": wall_table, "row_limit": LIST_LIMIT}, wall_table),
    ]

    async def refused(tool: str, name: str, arguments: dict[str, Any], what: str) -> list[dict[str, Any]]:
        if tool == "csi_db_table_read":
            raise ContractError(ErrorCode.HOST_ERROR, "no such table", retryable=False)
        return [] if tool == "csi_list_frame_sections" else [{"name": "SL"}]

    snap = anyio.run(read, refused)
    assert snap.tables == {}  # unavailable, not empty
    assert snap.frame_sections == set()
    empty: dict[str, list[dict[str, Any]]] = {
        area_table: [],
        wall_table: [],
    }  # tables that hold no rows are readable and empty

    async def none(tool: str, name: str, arguments: dict[str, Any], what: str) -> list[dict[str, Any]]:
        return empty[arguments["table"]] if tool == "csi_db_table_read" else []

    assert anyio.run(read, none).tables == {"area_section": [], "wall_section": []}

    async def cut(tool: str, name: str, arguments: dict[str, Any], what: str) -> list[dict[str, Any]]:
        raise ContractError(ErrorCode.LIMIT_EXCEEDED, "cut")

    with pytest.raises(ContractError):  # a section list that is cut would call every section undefined
        anyio.run(read, cut)


def test_integrity() -> None:
    """Undefined sections, combination parts that are not defined and a locked model; a load case is not checked."""
    from eng_harness.adapters.csi._checks import integrity

    ok = _snap(frames=[_frame("F1", "C30")], areas=[_area("A1", "SL")], frame_sections=["C30"], area_sections=["SL"])
    assert integrity(ok) == []
    snap = _snap(
        frames=[_frame("F1", "C30"), _frame("F2", "CX")], areas=[_area("A1", "SL"), _area("A2", "SLX")],
        frame_sections=["C30", "SL"], area_sections=["SL", "C30"], locked=True,
    )  # fmt: skip
    found = [(i.severity.value, i.code, i.subject.kind.value, i.subject.id, i.message) for i in integrity(snap)]
    assert found == [
        ("error", "SECTION_UNDEFINED", "frame", "F2", "the section CX is not defined"),
        ("error", "SECTION_UNDEFINED", "area", "A2", "the section SLX is not defined"),
        ("info", "MODEL_LOCKED", "model", "model", "the model is locked"),
    ]
    snap = _snap(patterns=[{"name": "DEAD", "type": "Dead"}])
    parts = [
        {"case": {"case": "DEAD", "case_type": "load_pattern"}, "scale_ratio": 1.0},
        {"case": {"case": "NOPE", "case_type": "load_combination"}, "scale_ratio": 1.0},
        {"case": {"case": "EQX", "case_type": "load_case"}, "scale_ratio": 1.0},
        {"case": {"case": "C1", "case_type": "load_combination"}, "scale_ratio": 1.0},
    ]
    loads = snap.state.payloads["model.load_set/1"]
    combinations = [
        {"name": "C1", "type": "linear_add", "items": parts[:3]},
        {"name": "C2", "type": "linear_add", "items": parts[3:]},
    ]
    snap.state.payloads["model.load_set/1"] = type(loads).model_validate(
        loads.model_dump(mode="json") | {"combinations": combinations}
    )
    missing = [(i.code, i.subject.kind.value, i.subject.id, i.message) for i in integrity(snap)]
    assert missing == [("COMBO_REFERENCE_MISSING", "load_combination", "C1", "NOPE is not defined")]


def test_written_items_pairing() -> None:
    """`prepare` and `commit` meet by model key, so interleaved writes to two models keep their own items."""
    from eng_harness.adapters.csi import _edits as e
    from eng_harness.adapters.csi._checks import Expect, WrittenItems

    book = WrittenItems()
    a = e.AssignFrameSectionArgs(model="a", frame="F1", section="C40")
    b = e.AssignFrameSectionArgs(model="b", frame="F2", section="C50")
    book.commit("a")  # nothing was prepared: nothing is recorded
    assert book.items("a") == []
    book.prepare(a)
    book.prepare(b)
    book.commit("b")
    book.commit("a")
    book.commit("a")  # the prepared item is used up
    assert book.items("a") == [Expect("frame_section", Subject(kind=FRAME, id="F1"), {"section": "C40"})]
    assert book.items("b") == [Expect("frame_section", Subject(kind=FRAME, id="F2"), {"section": "C50"})]
    book.items("a").clear()  # a copy: the book is unchanged
    assert len(book.items("a")) == 1
    book.prepare(a)  # prepared and never committed (its call failed), then replaced
    book.prepare(e.AssignFrameSectionArgs(model="a", frame="F3", section="C60"))
    book.commit("a")
    assert [i.subject.id for i in book.items("a")] == ["F1", "F3"]
    book.clear("a")
    assert book.items("a") == []
    assert len(book.items("b")) == 1


def test_expected_state_per_edit() -> None:
    """What each of the nine edit tools must show on read-back (spec 4.6.2); a quantity may be a `Quantity`."""
    from eng_contract.kinds.model import CombinationItem, CombinationType, PatternType

    from eng_harness.adapters.csi import _edits as e
    from eng_harness.adapters.csi._checks import Expect, _num, expect

    assert _num(Quantity(value=2.5, unit="mm")) == 2.5
    assert _num(3) == 3.0
    part = CombinationItem.model_validate({"case": {"case": "DEAD", "case_type": "load_pattern"}, "scale_ratio": 1.2})
    combo = e.AddLoadComboArgs(model="m", name="C", type=CombinationType.ENVELOPE, items=[part])
    flags = {"ux": True, "uy": False, "uz": True, "rx": False, "ry": False, "rz": True}
    cases: list[tuple[Any, Expect]] = [
        (
            e.AssignFrameSectionArgs(model="m", frame="F1", section="C40"),
            Expect("frame_section", Subject(kind=FRAME, id="F1"), {"section": "C40"}),
        ),
        (
            e.AssignAreaSectionArgs(model="m", area="A1", section="SL"),
            Expect("area_section_table", Subject(kind=AREA, id="A1"), {"section": "SL"}),
        ),
        (
            e.DefineWallSectionArgs(model="m", name="W1", material="C30", thickness_mm=250.0),
            Expect("wall_section_table", Subject(kind=SECTION, id="W1"), {"thickness_mm": 250.0}),
        ),
        (
            e.SetFrameLoadDistributedArgs(model="m", frame="F1", pattern="DEAD", w_kN_m=12.5),
            Expect("frame_load_table", Subject(kind=FRAME, id="F1", case="DEAD"), {"w_kN_m": 12.5}),
        ),
        (
            e.SetAreaLoadUniformArgs(model="m", area="A1", pattern="LIVE", q_kPa=6.25),
            Expect("area_load_table", Subject(kind=AREA, id="A1", case="LIVE"), {"q_kPa": 6.25}),
        ),
        (
            e.AddLoadPatternArgs(model="m", name="S", type=PatternType.SNOW, self_weight_ratio=0.0),
            Expect("load_pattern", Subject(kind=PATTERN, id="S"), {"type": "snow", "self_weight_ratio": 0.0}),
        ),
        (
            combo,
            Expect(
                "load_combo",
                Subject(kind=COMBINATION, id="C"),
                {"type": "envelope", "items": ["DEAD"], "factor 0": 1.2},
            ),
        ),
        (e.DeleteLoadComboArgs(model="m", name="C"), Expect("load_combo", Subject(kind=COMBINATION, id="C"), None)),
        (
            e.SetPointRestraintArgs(model="m", joint="P1", **flags),
            Expect("restraint_table", Subject(kind=JOINT, id="P1"), flags),
        ),
    ]
    for model, expected in cases:
        assert expect(model) == expected
    with pytest.raises(TypeError, match="no read-back for str"):
        expect("m")


def test_profile_pins_the_read_back_tables() -> None:
    """The read-back tables and columns are the product profile's, as the spec names them (OQ-G10: to confirm)."""
    from eng_harness.adapters.csi.products import profile

    assert dict(profile("ETABS").readback) == {
        "area_section": ("Area Assignments - Section Properties", "UniqueName", "Section"),
        "wall_section": ("Wall Property Definitions - Specified", "Name", "Thickness"),
    }
    assert profile("ETABS").readback["wall_section"][0] == profile("ETABS").tables["wall_sections"]
