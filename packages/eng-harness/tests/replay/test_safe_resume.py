"""SIGKILL the real engine after SAFE host writes; resume with new production ports (plan 0008 T8; spec 0008 AC27)."""

import json
import multiprocessing
import time
from pathlib import Path

import anyio
import pytest

from eng_harness.engine import RunStatus
from eng_harness.journal import _events as ev

# Write steps of the SAFE cycle (AC27: loads, save, analysis). Names come from SAFE wiring in the feat commit.
_SAFE_WRITE_CUTS = ("csi_set_point_load", "csi_save_model", "csi_run_analysis")


@pytest.mark.parametrize("cut", list(_SAFE_WRITE_CUTS))
def test_crash_matrix(tmp_path: Path, cut: str) -> None:
    """AC27: kill at each write step; resume reconciles without a repeated load write."""
    # SAFE cycle wiring lands in the feat commit; missing names fail at the base (TF004).
    from fakes.sasaah_csi.wiring import SafeAppliedInput, safe_rig, safe_run_crash_worker

    r = safe_rig(tmp_path)
    # Resolve the new builder in the test body, so the base fails as a missing capability, never at collection.
    r.ports()
    worker = multiprocessing.get_context("spawn").Process(target=safe_run_crash_worker, args=(str(tmp_path), cut))
    worker.start()
    try:
        # Hang guard for the whole pre-cut sequence, including process startup and disk syncs.
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
        path = str(r.original.resolve()) if cut == "csi_open_model" else None
        return [call for call in r.calls(cut) if call.get("path") == path]

    before = len(logical_calls())
    started = next(e for e in r.events() if isinstance(e.payload, ev.StepStarted) and e.payload.name == cut)
    assert isinstance(started.payload, ev.StepStarted)
    op_id = started.payload.op_id

    async def body() -> None:
        async with r.ports() as ports:
            inputs = SafeAppliedInput(cut)
            result = await r.engine(ports, inputs=inputs).resume(r.run_id)
            assert result.status is RunStatus.COMPLETED, result
            assert len(logical_calls()) == before == 1
            # AC27: no repeated load write on every cut (spec names the load write, not only the cut tool).
            assert len(r.calls("csi_set_point_load")) == 1
            journal = r.events()
            (reconciled,) = [e for e in journal if isinstance(e.payload, ev.StepReconciled)]
            assert isinstance(reconciled.payload, ev.StepReconciled)
            assert (reconciled.payload.outcome, reconciled.payload.op_id) == ("applied", op_id)
            attempts = [e for e in journal if e.path == started.path and isinstance(e.payload, ev.StepStarted)]
            assert len(attempts) == 1
            setter = cut == "csi_set_point_load"
            assert reconciled.payload.decided_by == ("adapter" if setter else "engineer:test")
            assert bool(reconciled.payload.evidence) is setter
            expected_requests = [] if setter else ["engine.in_flight"]
            if cut == "csi_save_model":
                expected_requests.append("engine.host_state")
                (baseline,) = [
                    e for e in journal if isinstance(e.payload, ev.ModelSaved) and e.payload.role == "baseline"
                ]
                assert isinstance(baseline.payload, ev.ModelSaved)
                assert baseline.payload.model_key == "m@copy"
                assert baseline.seq > reconciled.seq
                assert reconciled.payload.result is not None
                assert not reconciled.payload.result.complete
                assert not reconciled.payload.result.summary
            assert [request.kind for request in inputs.presented] == expected_requests
            checked = [
                e.payload.model_key
                for e in journal
                if isinstance(e.payload, ev.StepStarted) and e.payload.name == "check_model"
            ]
            assert set(checked) == {"m@copy"}
            assert r.original.read_bytes() == b"synthetic safe model"

    anyio.run(body)
