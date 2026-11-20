"""SAFE model-state reader, kinds and fingerprint (plan 0008 T5; spec 0008 AC9, AC10, section 4.4).

List reads use the token `kN_mm_C` (millimetres map to themselves). Table values are in the model's present
units (`kN_m_C`). Adapter imports sit inside the tests so a missing module fails the test.
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
from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.store import LocationClass, ModelStateStore, Workspace

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

from .test_csi_session_ops import LaunchInspector
from .test_safe_session_ops import SAFE_EXE

ConfigFactory = Callable[..., ServersConfig]
_START = 1_700_000_000_000
LIMIT = 2000  # S-12 section 2: every list tool and table read is capped at 2000
SAFE_KINDS = (
    "model.grid_system/1",
    "model.area_placements/1",
    "model.frame_placements/1",
    "harness.model_points/1",
    "model.sections/1",
    "model.materials/1",
    "model.load_set/1",
    "harness.joint_loads/1",
    "harness.safe_soil_supports/1",
)
STATUS_KIND = "harness.csi_model_status/1"
JOINT_LOADS = "Joint Loads Assignments - Force"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed(*, points: int = 1, joint_loads: int = 1) -> dict[str, Any]:
    """A SAFE footing model: list values in `kN_mm_C`, table values in present `kN_m_C` (spec 0008 section 4.4)."""
    return {
        "grids": [
            {
                "name": "G1",
                "type": "Cartesian",
                "origin": [0.0, 0.0],
                "rotation_deg": 0.0,
                "x_lines": [{"id": "1", "ordinate": 0.0, "visible": True}, {"id": "2", "ordinate": 4000.0}],
                "y_lines": [{"id": "A", "ordinate": 0.0, "visible": True}],
            }
        ],
        "points": [{"name": f"P{n}", "x": 1000.0 * n, "y": 500.0, "z": 0.0} for n in range(1, points + 1)],
        "frames": [
            {
                "name": "B1",
                "label": "B1",
                "point1": [0.0, 0.0, 0.0],
                "point2": [4000.0, 0.0, 0.0],
                "section": "GB",
                "story": "",
            }
        ],
        "areas": [
            {
                "name": "A1",
                "points": [[0.0, 0.0, 0.0], [4000.0, 0.0, 0.0], [4000.0, 4000.0, 0.0], [0.0, 4000.0, 0.0]],
                "section": "FOOT",
            },
            {
                "name": "A2",
                "points": [[0.0, 0.0, 0.0], [2000.0, 0.0, 0.0], [0.0, 2000.0, 0.0]],
                "section": "DROP",
            },
        ],
        "load_patterns": [{"name": "DEAD", "type": "Dead", "self_weight": 1.0}],
        "load_combos": [{"name": "C1", "type": 0, "items": [{"name": "DEAD", "factor": 1.4, "kind": "case"}]}],
        "tables": {
            "Slab Property Definitions": [
                {"Name": "FOOT", "PropType": "Footing", "Material": "C30", "Thickness": 0.5},
                {"Name": "DROP", "PropType": "Drop", "Material": "C30", "Thickness": 0.3},
            ],
            "Material Properties - General": [{"Material": "C30", "Type": "Concrete"}],
            "Material Properties - Basic Mechanical Properties": [
                {"Material": "C30", "UnitWeight": 24.0, "E1": 25000.0, "U12": 0.2}
            ],
            "Material Properties - Concrete Data": [{"Material": "C30", "Fc": 30.0}],
            "Load Pattern Definitions": [{"Name": "DEAD", "Type": "Dead", "SelfWtMultpl": 1.0}],
            "Load Combination Definitions": [{"Name": "C1", "Type": "Linear Add"}],
            JOINT_LOADS: [
                {
                    "UniqueName": f"P{n}",
                    "LoadPattern": "DEAD",
                    "FX": 0.0,
                    "FY": 0.0,
                    "FZ": -100.0 * n,
                    "MX": 0.0,
                    "MY": 0.0,
                    "MZ": 0.0,
                    "XDim": 0.4,
                    "YDim": 0.4,
                }
                for n in range(1, joint_loads + 1)
            ],
            "Spring Property Definitions - Area Springs": [
                {
                    "Name": "K1",
                    "StiffOpt": "Link",
                    "StiffU1": 0.0,
                    "StiffU2": 0.0,
                    "StiffU3": 20000.0,
                    "NonlinOpt3": "Compression Only",
                }
            ],
            "Area Assignments - Area Springs": [{"UniqueName": "A1", "SpringProp": "K1"}],
        },
    }


def _seeded(control: Path, **sizes: int) -> None:
    control.write_text(json.dumps({"faults": [], "seed": _seed(**sizes), "product": "SAFE"}))


def _port(
    tmp_path: Path, config: ServersConfig, control: Path, clock: FixedClock, ids: IdSource
) -> tuple[Any, ServerManager]:
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    original = tmp_path / "footing.FDB"
    original.write_bytes(b"safe-model-v1")
    run_dir = tmp_path / "run"
    inspector = LaunchInspector(control, exe_name=SAFE_EXE)
    guard = ProcessGuard(inspector, run_dir, host_exes=[SAFE_EXE])
    locks = HostLocks(
        tmp_path / "locks", run_id="b214", engine=ProcessIdentity(os.getpid(), "t0", "python"), clock=clock
    )
    base = config.servers["csi"].model_copy(update={"product": "SAFE", "host_key": "csi_safe"})
    safe_config = ServersConfig(servers={"csi_safe": base})
    manager = ServerManager(safe_config, run_dir, helpers=guard)
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
        product="SAFE",
        program="safe",
        exe_name=SAFE_EXE,
        server="csi_safe",
        host_key="csi_safe",
        files={"m": original},
    )
    return port, manager


async def _write(manager: ServerManager, pid: int, tool: str, **arguments: Any) -> None:
    await manager.call(
        "csi_safe", "main", tool, {"target": {"product": "SAFE", "pid": pid}, **arguments}, CallEffect.WRITE
    )


def test_kinds_and_fingerprint(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC9: SAFE kinds and status validate; one state has one fingerprint; each section 4.4 edit changes it."""
    from eng_harness.adapters.csi._replies import CSI_KINDS
    from eng_harness.adapters.csi.products._safe_state import SafeStateReader  # noqa: F401

    assert "harness.model_points/1" in HARNESS_KINDS
    assert "harness.joint_loads/1" in HARNESS_KINDS
    _seeded(control)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"safe-state", clock))
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
            assert sorted(read.payloads) == sorted(SAFE_KINDS)
            for kind in SAFE_KINDS:
                registry = NEUTRAL_KINDS if kind in NEUTRAL_KINDS else HARNESS_KINDS
                registry[kind].model_validate(read.payloads[kind].model_dump(mode="json"))
            CSI_KINDS[STATUS_KIND].model_validate(read.status.model_dump(mode="json"))

            points = read.payloads["harness.model_points/1"].model_dump(mode="json")["points"]
            assert points[0]["name"] == "P1"
            assert points[0]["x_mm"] == 1000.0
            areas = read.payloads["model.area_placements/1"].model_dump(mode="json")["areas"]
            assert {row["kind"] for row in areas} == {"slab"}
            frames = read.payloads["model.frame_placements/1"].model_dump(mode="json")["frames"]
            assert frames[0]["kind"] == "other"
            sections = read.payloads["model.sections/1"].model_dump(mode="json")["area_sections"]
            assert sections[0]["thickness_mm"] == 500.0  # 0.5 m present -> mm
            materials = read.payloads["model.materials/1"].model_dump(mode="json")["materials"]
            assert materials[0]["fc_MPa"] == 30.0
            loads = read.payloads["model.load_set/1"].model_dump(mode="json")
            assert loads["patterns"][0]["self_weight_ratio"] == 1.0
            assert loads["frame_loads"] == []
            assert loads["area_loads"] == []
            joint = read.payloads["harness.joint_loads/1"].model_dump(mode="json")
            assert joint["axes"] == "global"
            assert joint["loads"][0]["FZ_kN"] == -100.0
            assert joint["loads"][0]["punch_x_mm"] == 400.0
            soil = read.payloads["harness.safe_soil_supports/1"].model_dump(mode="json")
            assert soil["properties"][0]["name"] == "K1"
            assert read.status.units == "kN_m_C"
            assert read.status.file_name == port.model_files(key)[0].name

            seen = {first.fingerprint}
            edits: list[tuple[str, dict[str, Any]]] = [
                ("csi_assign_area_section", {"name": "A1", "section": "DROP"}),
                ("csi_add_load_pattern", {"name": "LIVE", "type": "Live"}),
                (
                    "csi_add_load_combo",
                    {"name": "C2", "combo_type": 0, "components": [{"name": "DEAD", "factor": 1.2}]},
                ),
                ("csi_delete_load_combo", {"name": "C1", "confirm": True}),
                (
                    "csi_set_point_load",
                    {
                        "name": "P1",
                        "load_pattern": "DEAD",
                        "force": [0.0, 0.0, -200.0],
                        "moment": [0.0, 0.0, 0.0],
                    },
                ),
            ]
            for tool, arguments in edits:
                await _write(manager, held.pid, tool, **arguments)
                port.wrote(key)
                fingerprint = (await port.model_state(key, held.instance_id)).fingerprint
                assert fingerprint not in seen
                seen.add(fingerprint)

    anyio.run(body)


@pytest.mark.parametrize(
    ("seed", "where"),
    [({"points": LIMIT + 1}, "csi_list_points"), ({"joint_loads": LIMIT + 1}, JOINT_LOADS)],
)
def test_truncated_raises(
    tmp_path: Path, make_config: ConfigFactory, control: Path, seed: dict[str, int], where: str
) -> None:
    """AC10: a list or table cut at 2000 rows raises LIMIT_EXCEEDED with the count; no partial payload."""
    from eng_harness.adapters.csi.products._safe_state import SafeStateReader  # noqa: F401

    _seeded(control, **seed)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"safe-trunc", clock))
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(key)
            assert held is not None
            with pytest.raises(ContractError) as refused:
                await port.model_state(key, held.instance_id)
            assert refused.value.detail.code is ErrorCode.LIMIT_EXCEEDED
            assert refused.value.detail.received == LIMIT
            assert where in refused.value.detail.message
            assert port.last_read(key) is None

    anyio.run(body)
