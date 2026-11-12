"""CSI model-state reader on the synthetic fake (plan 0002 T11; spec 0002 AC27, section 4.6.4)."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, IdSource, SeededIdSource
from eng_contract.kinds import NEUTRAL_KINDS

from eng_harness.servers import CallEffect, ServersConfig

from .test_csi_session_ops import _open

ConfigFactory = Callable[..., ServersConfig]
_START = 1_700_000_000_000
KINDS = (
    "model.stories/1",
    "model.grid_system/1",
    "model.frame_placements/1",
    "model.area_placements/1",
    "model.load_set/1",
    "model.joint_restraints/1",
    "harness.csi_model_status/1",
)
LIST_LIMIT = 2000  # S-12 section 2: list and table reads are capped at 2000 (spec 0002 section 4.6.4)


def _seed(*, points: int = 2, stories: int = 1) -> dict[str, Any]:
    return {
        "stories": [
            {
                "name": f"S{n}",
                "elevation": float(n * 3.0),
                "height": 3.0,
                "is_master": n == 0,
                "similar_to": None,
            }
            for n in range(stories)
        ],
        "grids": [
            {
                "name": "G1",
                "type": "Cartesian",
                "origin": [0.0, 0.0],
                "rotation_deg": 0.0,
                "x_lines": [{"id": "1", "ordinate": 0.0, "visible": True}],
                "y_lines": [{"id": "A", "ordinate": 0.0, "visible": True}],
            }
        ],
        "points": [{"name": f"P{n}", "x": float(n), "y": 0.0, "z": 0.0} for n in range(points)],
        "frames": [
            {
                "name": "F1",
                "point1": [0.0, 0.0, 0.0],
                "point2": [0.0, 0.0, 3.0],
                "section": "C30x30",
                "label": "F1",
                "story": "S1",
            }
        ],
        "areas": [{"name": "A1", "points": [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0], [0.0, 5.0, 0.0]], "section": "SLAB1"}],
        "area_sections": [{"name": "SLAB1", "type": "slab", "thickness": 0.2, "material": "C30"}],
        "load_patterns": [{"name": "DEAD", "type": "Dead", "self_weight": 1.0}],
        "load_combos": [{"name": "COMB1", "type": 0, "items": [{"name": "DEAD", "factor": 1.0, "kind": "case"}]}],
        "tables": {
            "Joint Assignments - Restraints": [
                {"UniqueName": "P1", "Ux": True, "Uy": True, "Uz": True, "Rx": False, "Ry": False, "Rz": False}
            ],
            "Load Pattern Definitions": [{"Name": "DEAD", "Type": "Dead", "SelfWtMultpl": 1.0}],
            "Load Combination Definitions": [{"Name": "COMB1", "Type": "Linear Add"}],
            "Frame Loads Assignments - Distributed": [],
            "Area Load Assignments - Uniform": [],
        },
    }


@pytest.fixture
def seeded_control(control: Path) -> Path:
    control.write_text(json.dumps({"faults": [], "seed": _seed()}))
    return control


def test_kinds_and_fingerprint(tmp_path: Path, make_config: ConfigFactory, seeded_control: Path, control: Path) -> None:
    """The reader produces validating kinds, a stable fingerprint, units, and LIMIT_EXCEEDED on truncation."""
    clock = FixedClock(_START)
    ids: IdSource = SeededIdSource(b"state", clock)
    from eng_harness.adapters.csi._replies import CSI_KINDS

    async def happy() -> None:
        port, manager, _inspector, _states, _original = await _open(tmp_path, make_config(), seeded_control, clock, ids)
        async with manager:
            copy_key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(copy_key)
            assert held is not None
            first = await port.model_state(copy_key, held.instance_id)
            second = await port.model_state(copy_key, held.instance_id)
            assert first.loaded
            assert second.loaded
            assert first.fingerprint == second.fingerprint
            assert len(first.fingerprint or "") == 64

            cached = json.loads((tmp_path / "run" / "adapter" / "model_state.json").read_text())
            for kind in KINDS:
                model = NEUTRAL_KINDS.get(kind) or CSI_KINDS[kind]
                model.model_validate(cached["kinds"][kind])

            target = {"target": {"product": "ETABS", "pid": held.pid}}
            await manager.call(
                "csi", "main", "csi_add_point", {**target, "name": "PX", "x": 9.0, "y": 0.0, "z": 0.0}, CallEffect.WRITE
            )
            assert (await port.model_state(copy_key, held.instance_id)).fingerprint != first.fingerprint
            units = await port.read_units(copy_key, held.instance_id)
            assert units.loaded
            assert units.ok
            assert units.present == "kN_m_C"
            assert units.expected == "kN_m_C"

    async def truncated() -> None:
        overflow = tmp_path / "overflow"
        overflow.mkdir()
        (overflow / "original.EDB").write_bytes(b"overflow-model")
        path = overflow / "control.json"
        path.write_text(json.dumps({"faults": [], "seed": _seed(stories=LIST_LIMIT + 1)}))
        port, manager, _inspector, _states, _original = await _open(
            overflow,
            make_config(env={"SASAAH_CSI_FAKE_CONTROL": str(path)}),
            path,
            FixedClock(_START + 1),
            SeededIdSource(b"truncate", clock),
        )
        async with manager:
            copy_key = await port.working_copy("m", overflow / "run" / "copies")
            held = await port.locate(copy_key)
            assert held is not None
            with pytest.raises(ContractError) as trapped:
                await port.model_state(copy_key, held.instance_id)
            assert trapped.value.detail.code is ErrorCode.LIMIT_EXCEEDED

    anyio.run(happy)
    anyio.run(truncated)
