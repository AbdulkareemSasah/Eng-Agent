"""SAP2000 model-state reader, declared absences and fingerprint (plan 0012 T4; spec 0012 AC7 to AC9).

List reads use the token `kN_mm_C` (millimetres map to themselves). The reader does not call stories or grids
(profile declared absences, AC8). Adapter imports sit inside the tests so a missing module fails the test.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, IdSource, SeededIdSource
from eng_contract.issues import Severity
from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.store import LocationClass, ModelStateStore, Workspace
from eng_contract.verdicts import SubjectKind

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

from .test_sap2000_session_ops import SAP2000_EXE, _Sap2000Inspector

ConfigFactory = Callable[..., ServersConfig]
_START = 1_700_000_000_000
LIMIT = 2000  # S-12 section 2: every list tool and table read is capped at 2000
SAP2000_KINDS = (
    "model.frame_placements/1",
    "model.area_placements/1",
    "harness.model_points/1",
    "model.sections/1",
    "model.materials/1",
    "model.load_set/1",
)
STATUS_KIND = "harness.csi_model_status/1"
ABSENT_KINDS = ("model.stories/1", "model.grid_system/1")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed(*, points: int = 1, frames: int = 1) -> dict[str, Any]:
    """A SAP2000 frame model: list values in `kN_mm_C` (spec 0012 section 4.3; no stories or grids)."""
    return {
        "points": [{"name": f"P{n}", "x": 1000.0 * n, "y": 500.0, "z": 0.0} for n in range(1, points + 1)],
        "frames": [
            {
                "name": f"F{n}",
                "point1": [0.0, 0.0, 0.0],
                "point2": [0.0, 0.0, 3000.0 * n],
                "section": "C300",
            }
            for n in range(1, frames + 1)
        ],
        "areas": [
            {
                "name": "A1",
                "points": [[0.0, 0.0, 0.0], [4000.0, 0.0, 0.0], [4000.0, 4000.0, 0.0], [0.0, 4000.0, 0.0]],
                "section": "SLAB1",
            }
        ],
        "frame_sections": [{"name": "C300"}, {"name": "C400"}],
        "area_sections": [{"name": "SLAB1", "type": "slab"}],
        "materials": [{"name": "C30"}],
        "load_patterns": [{"name": "DEAD", "type": "Dead", "self_weight": 1.0}],
        "load_combos": [{"name": "C1", "type": 0, "items": [{"name": "DEAD", "factor": 1.4, "kind": "case"}]}],
        "tables": {},
    }


def _seeded(control: Path, **sizes: int) -> None:
    control.write_text(json.dumps({"faults": [], "seed": _seed(**sizes), "product": "SAP2000"}))


def _port(
    tmp_path: Path, config: ServersConfig, control: Path, clock: FixedClock, ids: IdSource
) -> tuple[Any, ServerManager]:
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    original = tmp_path / "frame.SDB"
    original.write_bytes(b"sap2000-model-v1")
    run_dir = tmp_path / "run"
    inspector = _Sap2000Inspector(control)
    guard = ProcessGuard(inspector, run_dir, host_exes=[SAP2000_EXE])
    locks = HostLocks(
        tmp_path / "locks", run_id="b248", engine=ProcessIdentity(os.getpid(), "t0", "python"), clock=clock
    )
    base = config.servers["csi"].model_copy(update={"product": "SAP2000", "host_key": "csi_sap2000"})
    sap_config = ServersConfig(servers={"csi_sap2000": base})
    manager = ServerManager(sap_config, run_dir, helpers=guard)
    port = AdapterHostPort(
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
    )
    return port, manager


async def _write(manager: ServerManager, pid: int, tool: str, **arguments: Any) -> None:
    await manager.call(
        "csi_sap2000", "main", tool, {"target": {"product": "SAP2000", "pid": pid}, **arguments}, CallEffect.WRITE
    )


def test_kinds_and_fingerprint(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC7: SAP2000 kinds and status validate; one state has one fingerprint; each edit kind changes it."""
    from eng_harness.adapters.csi._replies import CSI_KINDS
    from eng_harness.adapters.csi.products._sap2000_state import Sap2000StateReader

    assert "harness.model_points/1" in HARNESS_KINDS
    _seeded(control)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"sap-state", clock))
        assert isinstance(port._reader, Sap2000StateReader)
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(key)
            assert held is not None
            first = await port.model_state(key, held.instance_id)
            assert await port.model_state(key, held.instance_id) == first
            assert first.loaded
            assert re.fullmatch("[0-9a-f]{64}", first.fingerprint or "")
            assert first.file_sha256 == _sha(port.model_files(key)[0])

            read = port.last_read(key)
            assert read is not None
            assert read.fingerprint == first.fingerprint
            assert sorted(read.payloads) == sorted(SAP2000_KINDS)
            for kind in ABSENT_KINDS:
                assert kind not in read.payloads
            for kind in SAP2000_KINDS:
                registry = NEUTRAL_KINDS if kind in NEUTRAL_KINDS else HARNESS_KINDS
                registry[kind].model_validate(read.payloads[kind].model_dump(mode="json"))
            CSI_KINDS[STATUS_KIND].model_validate(read.status.model_dump(mode="json"))

            points = read.payloads["harness.model_points/1"].model_dump(mode="json")["points"]
            assert points[0]["name"] == "P1"
            assert points[0]["x_mm"] == 1000.0
            frames = read.payloads["model.frame_placements/1"].model_dump(mode="json")["frames"]
            assert frames[0]["kind"] == "other"
            assert frames[0]["story"] is None
            areas = read.payloads["model.area_placements/1"].model_dump(mode="json")["areas"]
            assert areas[0]["id"] == "A1"
            loads = read.payloads["model.load_set/1"].model_dump(mode="json")
            assert loads["patterns"][0]["self_weight_ratio"] == 1.0
            assert loads["frame_loads"] == []
            assert loads["area_loads"] == []
            assert read.status.units == "kN_m_C"
            assert read.status.file_name == port.model_files(key)[0].name

            # Declared absences (empty TABLES) still record the fingerprint on save (B-590 / _record_save).
            saved = await port.save(key, "pre_analysis")
            assert saved.fingerprint
            assert saved.fingerprint == (await port.model_state(key, held.instance_id)).fingerprint

            seen = {first.fingerprint, saved.fingerprint}
            edits: list[tuple[str, dict[str, Any]]] = [
                ("csi_assign_frame_section", {"name": "F1", "section": "C400"}),
                ("csi_add_load_pattern", {"name": "LIVE", "type": "Live"}),
                (
                    "csi_add_load_combo",
                    {"name": "C2", "combo_type": 0, "components": [{"name": "DEAD", "factor": 1.2}]},
                ),
                ("csi_delete_load_combo", {"name": "C1", "confirm": True}),
            ]
            for tool, arguments in edits:
                await _write(manager, held.pid, tool, **arguments)
                port.wrote(key)
                fingerprint = (await port.model_state(key, held.instance_id)).fingerprint
                assert fingerprint not in seen
                seen.add(fingerprint)

    anyio.run(body)


def test_declared_absences(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC8: stories and grids are not called; info issues name the cause; absent kinds are not produced."""
    from eng_harness.adapters.csi.products._sap2000_state import Sap2000StateReader

    _seeded(control)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"sap-absent", clock))
        reader = port._reader
        assert isinstance(reader, Sap2000StateReader)
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(key)
            assert held is not None
            await port.model_state(key, held.instance_id)
            read = port.last_read(key)
            assert read is not None
            for kind in ABSENT_KINDS:
                assert kind not in read.payloads
            tools = [entry.get("tool") for entry in json.loads(control.read_text()).get("calls", [])]
            assert "csi_list_stories" not in tools
            assert "csi_list_grids" not in tools
            codes = {issue.code for issue in reader.issues}
            assert codes == {"LEVELS_NOT_AVAILABLE", "GRID_NOT_AVAILABLE"}
            assert all(issue.severity is Severity.INFO for issue in reader.issues)
            assert all(issue.subject.kind is SubjectKind.MODEL for issue in reader.issues)
            assert re.fullmatch("[0-9a-f]{64}", read.fingerprint)

    anyio.run(body)


def test_other_unsupported_raises(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC8: unsupported_by_version from a served list tool is NOT_SUPPORTED_BY_VERSION, never swallowed."""
    from eng_harness.adapters.csi.products._sap2000_state import Sap2000StateReader

    _seeded(control)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"sap-unsup", clock))
        real = port._session._call

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if tool == "csi_list_points":
                raise ContractError(
                    ErrorCode.NOT_SUPPORTED_BY_VERSION,
                    "csi_list_points is not supported by this version",
                    retryable=False,
                )
            body = await real(tool, arguments, effect)
            assert isinstance(body, dict)
            return body

        # Inject a failing call for one served list tool; production wiring still selected Sap2000StateReader.
        port._reader = Sap2000StateReader(product="SAP2000", call=call)
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(key)
            assert held is not None
            with pytest.raises(ContractError) as refused:
                await port.model_state(key, held.instance_id)
            assert refused.value.detail.code is ErrorCode.NOT_SUPPORTED_BY_VERSION
            assert port.last_read(key) is None

    anyio.run(body)


def test_truncated_raises(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC9: a list cut at 2000 rows raises LIMIT_EXCEEDED with the count; no partial payload."""
    from eng_harness.adapters.csi.products._sap2000_state import Sap2000StateReader

    _seeded(control, points=LIMIT + 1)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"sap-trunc", clock))
        assert isinstance(port._reader, Sap2000StateReader)
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(key)
            assert held is not None
            with pytest.raises(ContractError) as refused:
                await port.model_state(key, held.instance_id)
            assert refused.value.detail.code is ErrorCode.LIMIT_EXCEEDED
            assert refused.value.detail.received == LIMIT
            assert "csi_list_points" in refused.value.detail.message
            assert port.last_read(key) is None

    anyio.run(body)
