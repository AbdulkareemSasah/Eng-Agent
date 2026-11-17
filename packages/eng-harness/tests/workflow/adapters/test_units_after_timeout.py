"""The units trap through production wiring and Engine (plan 0002 T19a, AC22)."""

import json
from pathlib import Path

import anyio
from fakes.sasaah_csi.wiring import rig

from eng_harness.engine import PermissionMode, RunStatus
from eng_harness.journal import _events as ev


def test_units_trap(tmp_path: Path) -> None:
    r = rig(tmp_path)
    data = json.loads(r.control.read_text())
    data["faults"] = [
        {"tool": "csi_define_wall_section", "fault": "units_left_changed"},
        {"tool": "csi_define_wall_section", "fault": "timeout_after_apply"},
    ]
    r.control.write_text(json.dumps(data))
    steps = [
        ("csi_open_model", {"model": "m"}),
        ("csi_define_wall_section", {"model": "m", "name": "W1", "material": "C30", "thickness_mm": 250.0,
                                     "shell_type": "ShellThin"}),
        ("csi_read_model_state", {"model": "m"}),
    ]

    async def body() -> None:
        async with r.ports() as p:
            result = await r.engine(p, steps).start(r.request(mode=PermissionMode.AUTONOMOUS_LOGGED))
            assert result.status is RunStatus.NEEDS_ENGINEER, result
            assert result.escalation.reason == "units_mismatch"
            assert "kN_mm_C" in result.escalation.detail
            assert not any(isinstance(e.payload, ev.StepReconciled) for e in r.events())
            assert len(r.calls("csi_define_wall_section")) == 1

    anyio.run(body)
