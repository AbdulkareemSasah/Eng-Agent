"""SIGKILL the real engine after host writes; resume with new production ports (T19a, AC36)."""

import json
import multiprocessing
import time
from pathlib import Path

import anyio
import pytest
from fakes.sasaah_csi.wiring import STEPS, AppliedInput, rig, run_crash_worker

from eng_harness.engine import RunStatus
from eng_harness.journal import _events as ev


@pytest.mark.parametrize(
    "cut",
    [
        name
        for name, _ in STEPS
        if name
        in {
            "csi_open_model",
            "csi_assign_frame_section",
            "csi_assign_area_section",
            "csi_save_model",
            "csi_run_analysis",
            "csi_design_run",
        }
    ],
)
def test_crash_matrix(tmp_path: Path, cut: str) -> None:
    r = rig(tmp_path)
    # Resolve the new builder in the test body, so the base fails as a missing capability, never at collection.
    r.ports()
    worker = multiprocessing.get_context("spawn").Process(target=run_crash_worker, args=(str(tmp_path), cut))
    worker.start()
    try:
        # This is a hang guard for the whole pre-cut sequence, including process startup and disk syncs.
        deadline = time.monotonic() + 120
        while not (tmp_path / "cut.json").exists() and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (tmp_path / "cut.json").exists(), (tmp_path / "worker.log").read_text()
        worker.kill()
        worker.join(timeout=10)
        assert not worker.is_alive()
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=10)
        worker.close()
    data = json.loads((tmp_path / "cut.json").read_text())
    r.run_id, r.basis_ref = data["run_id"], data["basis_ref"]

    def logical_calls() -> list[dict[str, object]]:
        # The original open has its source path; the tool save has no path. Engine copy/save housekeeping is distinct.
        path = str(r.original.resolve()) if cut == "csi_open_model" else None
        return [call for call in r.calls(cut) if call["path"] == path]

    before = len(logical_calls())
    started = next(e for e in r.events() if isinstance(e.payload, ev.StepStarted) and e.payload.name == cut)
    assert isinstance(started.payload, ev.StepStarted)
    op_id = started.payload.op_id

    async def body() -> None:
        async with r.ports() as ports:
            inputs = AppliedInput(cut)
            result = await r.engine(ports, inputs=inputs).resume(r.run_id)
            assert result.status is RunStatus.COMPLETED, result
            assert len(logical_calls()) == before == 1
            journal = r.events()
            (reconciled,) = [e for e in journal if isinstance(e.payload, ev.StepReconciled)]
            assert isinstance(reconciled.payload, ev.StepReconciled)
            assert (reconciled.payload.outcome, reconciled.payload.op_id) == ("applied", op_id)
            attempts = [e for e in journal if e.path == started.path and isinstance(e.payload, ev.StepStarted)]
            assert len(attempts) == 1
            setter = cut in {"csi_assign_frame_section", "csi_assign_area_section"}
            assert reconciled.payload.decided_by == ("adapter" if setter else "engineer:test")
            assert bool(reconciled.payload.evidence) is setter
            expected_requests = [] if setter else ["engine.in_flight"]
            if cut == "csi_save_model":
                expected_requests.append("engine.host_state")
                (baseline,) = [
                    e for e in journal if isinstance(e.payload, ev.ModelSaved) and e.payload.role == "baseline"
                ]
                assert isinstance(baseline.payload, ev.ModelSaved)
                assert baseline.payload.model_key == "m@copy" and baseline.seq > reconciled.seq
                assert reconciled.payload.result is not None and not reconciled.payload.result.complete
                assert not reconciled.payload.result.summary
            assert [request.kind for request in inputs.presented] == expected_requests
            assert r.original.read_bytes() == b"synthetic model"

    anyio.run(body)
