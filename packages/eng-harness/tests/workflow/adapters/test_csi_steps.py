"""CSI edit tools through the ToolPort against the synthetic fake (plan 0002 T12; spec 0002 AC25, 4.6.1, 4.6.2).

The arguments the fake receives are compared with the spec's mapping: the tool's own names, the explicit `target`,
the `units` token (`kN_mm_C` for the wall thickness, `kN_m_C` for the loads, none for the rest) and `confirm` only for
the owned delete under the engine's approval. The expected values are derived by hand: 250 mm is 250 in `kN_mm_C`.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore
from mcp import types

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect, ServerManager

from .test_csi_session_ops import ConfigFactory

HOST = HostInfo(program="ETABS", version="22.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0)
SHA = "d" * 64
CHECK = ServerCheck(
    server="csi", build="0123456789ab+fedcba987654", min_build="", fingerprint=SHA, expected_fingerprint=SHA, ok=True,
    reason=None,
)  # fmt: skip
SEED = {
    "frames": [{"name": "F1", "section": "C30"}],
    "areas": [{"name": "A1", "section": "SL"}],
    "load_combos": [{"name": "C1", "type": 0, "items": []}],
}
Case = tuple[str, dict[str, Any], dict[str, Any]]  # tool, canonical arguments, host arguments before the target


class Recorder:
    """The session side: the manager, noting what each tool was sent."""

    def __init__(self, manager: ServerManager) -> None:
        self.manager = manager
        self.sent: list[tuple[str, dict[str, Any]]] = []

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        self.sent.append((tool, dict(arguments)))
        return await self.manager.call(server, role, tool, arguments, effect)


class Binder:
    """The bound instance of the only model."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    async def binding(self, host_key: str, model: str | None) -> Binding:
        return Binding(target=HostTarget(product="ETABS", pid=self.pid), host=HOST, owned=True)

    def revision(self, model_id: str) -> int | None:
        return None


def _cases(pid: int, value: Any) -> list[Case]:
    return [
        ("csi_assign_frame_section", {"frame": "F1", "section": "C40"}, {"name": "F1", "section": "C40"}),
        ("csi_assign_area_section", {"area": "A1", "section": "SL20"}, {"name": "A1", "section": "SL20"}),
        (
            "csi_define_wall_section",
            {"name": "W1", "material": "C30", "thickness_mm": value("thickness_mm", 250.0)},
            {"name": "W1", "material": "C30", "thickness": 250.0, "wall_type": "Specified", "shell_type": "ShellThin"}
            | {"units": "kN_mm_C"},
        ),
        (
            "csi_set_frame_load_distributed",
            {"frame": "F1", "pattern": "DEAD", "w_kN_m": value("w_kN_m", 12.5)},
            {"name": "F1", "load_pattern": "DEAD", "value": 12.5, "direction": "gravity", "units": "kN_m_C"},
        ),
        (
            "csi_set_area_load_uniform",
            {"area": "A1", "pattern": "LIVE", "q_kPa": value("q_kPa", 6.25)},
            {"name": "A1", "load_pattern": "LIVE", "value": 6.25, "direction": "gravity", "units": "kN_m_C"},
        ),
        (
            "csi_add_load_pattern",
            {"name": "SNOW1", "type": "snow", "self_weight_ratio": value("self_weight_ratio", 0.0)},
            {"name": "SNOW1", "type": "Snow", "self_weight": 0.0},
        ),
        (
            "csi_add_load_combo",
            {
                "name": "C2",
                "type": "envelope",
                "items": [{"case": {"case": "C1", "case_type": "load_combination"}, "scale_ratio": 1.0}],
            },
            {"name": "C2", "combo_type": 1, "components": [{"name": "C1", "factor": 1.0, "kind": "combo"}]},
        ),
        ("csi_delete_load_combo", {"name": "C1"}, {"name": "C1", "confirm": True}),
        (
            "csi_set_point_restraint",
            {"joint": "P1", "ux": True, "uy": True, "uz": True, "rx": False, "ry": False, "rz": False},
            {"name": "P1", "values": [True, True, True, False, False, False]},
        ),
    ]


@pytest.mark.parametrize("index", range(9))
def test_step_mapping(
    index: int, tmp_path: Path, make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """The arguments the fake receives equal the mapping; the reply is stored as a result of the stated kind."""
    from eng_harness.adapters.csi._tools import CsiToolPort

    control.write_text(json.dumps({"faults": [], "seed": SEED}))
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"steps", clock)
    producer = Provenance(
        tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
    )

    def value(name: str, number: float) -> dict[str, str]:
        record = store.put("harness.run_input/1", {"value": {name: number}}, producer)
        return {"$ref": f"{record.result_id}#/value/{name}"}

    async def body() -> None:
        manager = ServerManager(make_config(), run_dir)
        async with manager:
            launched = await manager.call("csi", "main", "csi_launch", {"product": "ETABS"}, CallEffect.WRITE)
            block = launched.content[0]
            assert isinstance(block, types.TextContent)
            pid = json.loads(block.text)["pid"]
            tool, canonical, host_args = _cases(pid, value)[index]
            recorder = Recorder(manager)
            port = CsiToolPort(
                binder=Binder(pid), config=make_config(), server="csi", caller=recorder, store=store,
                ledger=WriteLedger(run_dir), clock=clock, ids=ids, check=CHECK,
            )  # fmt: skip
            reply = await port.call(tool, {"model": "m", **canonical}, op_id="op-1", model="m")
            assert isinstance(reply, SuccessEnvelope), reply
            assert reply.kind == "harness.run_output/1"
            assert recorder.sent == [(tool, host_args | {"target": {"product": "ETABS", "pid": pid}})]
            info = await port.describe(tool)
            assert info.effect == "write"
            assert info.model_param == "model"

    anyio.run(body)
