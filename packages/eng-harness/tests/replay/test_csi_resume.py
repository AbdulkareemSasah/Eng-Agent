"""SIGKILL the real engine after host writes; resume with new production ports (T19a, AC36)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import anyio
import pytest
from fakes.sasaah_csi.wiring import EDITS, rig

from eng_harness.engine import RunStatus
from eng_harness.journal import _events as ev


@pytest.mark.parametrize("cut", [name for name, _ in EDITS])
def test_crash_matrix(tmp_path: Path, cut: str) -> None:
    r = rig(tmp_path)
    # Resolve the new builder in the test body, so the base fails as a missing capability, never at collection.
    r.ports()
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    with (tmp_path / "worker.log").open("w") as log:
        worker = subprocess.Popen([sys.executable, "-m", "fakes.sasaah_csi.wiring", str(tmp_path), cut],
                                  env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 30
            while not (tmp_path / "cut.json").exists() and worker.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert (tmp_path / "cut.json").exists(), (tmp_path / "worker.log").read_text()
            worker.kill()
            worker.wait(timeout=10)
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=10)
    data = json.loads((tmp_path / "cut.json").read_text())
    r.run_id, r.basis_ref = data["run_id"], data["basis_ref"]
    before = len(r.calls(cut))

    async def body() -> None:
        async with r.ports() as ports:
            result = await r.engine(ports).resume(r.run_id)
            assert result.status is RunStatus.COMPLETED, result
            assert len(r.calls(cut)) == before == 1
            reconciled = [e.payload for e in r.events() if isinstance(e.payload, ev.StepReconciled)]
            assert any(p.outcome == "applied" and p.decided_by == "adapter" for p in reconciled)
            assert r.original.read_bytes() == b"synthetic model"

    anyio.run(body)
