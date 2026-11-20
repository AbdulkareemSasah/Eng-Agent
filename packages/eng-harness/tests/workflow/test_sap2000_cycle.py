"""SAP2000 end-to-end cycle through Engine and production ports (plan 0012 T7; spec 0012 AC18)."""

import json
from pathlib import Path

import anyio

from eng_harness.engine import RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev


def test_cycle_steps(tmp_path: Path) -> None:
    """AC18: open copy, read state, assign section, save, analyse, frame forces and reactions; journal holds all."""
    # SAP2000 cycle wiring (sap2000_steps / sap2000_rig) lands in the feat commit; missing names fail at the base (TF004).
    from fakes.sasaah_csi.wiring import sap2000_rig, sap2000_steps

    r = sap2000_rig(tmp_path)
    original = r.original.read_bytes()
    steps = sap2000_steps(r)

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
            # Host port reads SAP2000 state after open (Sap2000StateReader); not the ETABS-shaped csi_read_model_state tool.
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
            assert (
                names.index("csi_assign_frame_section")
                < names.index("csi_save_model")
                < names.index("csi_run_analysis")
            )
            assert r.calls("csi_run_analysis")[0]["role"] == "long"
            assert r.calls("csi_results_frame_forces")
            assert r.calls("csi_results_joint_reactions")
            # AC18: only the started instance is closed.
            assert len(r.calls("csi_exit")) == 1

    anyio.run(body)
