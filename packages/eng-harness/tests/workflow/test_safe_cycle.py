"""SAFE end-to-end cycle through Engine and production ports (plan 0008 T8; spec 0008 AC26)."""

import json
from pathlib import Path

import anyio
import pytest

from eng_harness.engine import RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev


def test_cycle_steps(tmp_path: Path) -> None:
    """AC26: open copy, import loads, save, analyse, soil pressures and base reactions; journal holds all."""
    # SAFE cycle wiring (safe_steps / safe_rig) lands in the feat commit; missing names fail at the base (TF004).
    from fakes.sasaah_csi.wiring import safe_rig, safe_steps

    r = safe_rig(tmp_path)
    original = r.original.read_bytes()
    steps = safe_steps(r)

    async def body() -> None:
        async with r.ports() as ports:
            result = await r.engine(ports, steps=steps).start(r.request())
            assert result.status is RunStatus.COMPLETED, result
            assert r.original.read_bytes() == original
            assert ports.host_port.model_files("m@copy")[0].is_file()
            journal = r.events()
            done = [e.payload for e in journal if isinstance(e.payload, ev.StepStarted) and e.payload.kind == "tool"]
            assert [p.name for p in done] == [name for name, _ in steps]
            assert EventType.CHECK_ENFORCED in [e.type for e in journal]
            assert EventType.HOST_STARTED in [e.type for e in journal]
            assert EventType.MODEL_BOUND in [e.type for e in journal]
            assert EventType.MODEL_SAVED in [e.type for e in journal]
            # Host port reads SAFE state after open (SafeStateReader); not the ETABS-shaped csi_read_model_state tool.
            held = await ports.host_port.locate("m@copy")
            assert held is not None
            assert ports.host_port.last_read("m@copy") is not None
            checked = [
                e.payload.model_key
                for e in journal
                if isinstance(e.payload, ev.StepStarted) and e.payload.name == "check_model"
            ]
            assert set(checked) == {"m@copy"}
            assert [c["path"] for c in r.calls("csi_open_model")][:2] == [
                str(r.original.resolve()),
                str(ports.host_port.model_files("m@copy")[0]),
            ]
            calls = json.loads(r.control.read_text())["calls"]
            names = [c["tool"] for c in calls]
            assert names.index("csi_set_point_load") < names.index("csi_save_model") < names.index("csi_run_analysis")
            assert r.calls("csi_run_analysis")[0]["role"] == "long"
            assert r.calls("csi_results_base_reactions")
            # Soil pressures are a table read (spec 0008 §4.6), not a ToolPort step; verify after the run.
            # Seed supplies _SOIL_ROW Pressure 12.5 (same oracle as test_safe_results.py / T7).
            pressures = await r.read_soil_pressures(ports, model="m@copy")
            assert pressures.summary.count == 1
            assert pressures.rows[0].pressure_kpa == pytest.approx(12.5)

    anyio.run(body)
