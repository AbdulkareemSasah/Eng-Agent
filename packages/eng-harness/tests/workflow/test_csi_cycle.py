"""The CSI cycle through Engine and production ports (plan 0002 T19a, AC36)."""

import json
from pathlib import Path

import anyio
from fakes.sasaah_csi.wiring import STEPS, rig

from eng_harness.engine import RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev


def test_cycle_steps(tmp_path: Path) -> None:
    r = rig(tmp_path)
    original = r.original.read_bytes()

    async def body() -> None:
        async with r.ports() as ports:
            result = await r.engine(ports).start(r.request())
            assert result.status is RunStatus.COMPLETED, result
            assert r.original.read_bytes() == original
            assert ports.host_port.model_files("m@copy")[0].is_file()
            journal = r.events()
            done = [e.payload for e in journal if isinstance(e.payload, ev.StepStarted) and e.payload.kind == "tool"]
            assert [p.name for p in done] == [name for name, _ in STEPS]
            assert EventType.CHECK_ENFORCED in [e.type for e in journal]
            assert EventType.HOST_STARTED in [e.type for e in journal]
            assert EventType.MODEL_BOUND in [e.type for e in journal]
            assert EventType.MODEL_SAVED in [e.type for e in journal]
            assert [c["path"] for c in r.calls("csi_open_model")][:2] == [
                str(r.original.resolve()),
                str(ports.host_port.model_files("m@copy")[0]),
            ]
            calls = json.loads(r.control.read_text())["calls"]
            names = [c["tool"] for c in calls]
            assert names.index("csi_save_model") < names.index("csi_run_analysis") < names.index("csi_design_run")
            assert r.calls("csi_run_analysis")[0]["role"] == "long"
            assert r.calls("csi_design_run")[0]["role"] == "long"
            assert r.calls("csi_results_joint_reactions")

    anyio.run(body)
