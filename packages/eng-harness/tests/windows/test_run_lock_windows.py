"""The run lock on Windows (plan 0001 T9; spec 0001 4.4.4, AC23): the lock dies with its killed holder.

Defined only on Windows (as `tests/windows/test_jobs.py` does), so no skip enters the ratchet; it runs in the Windows CI
job and has not run on Windows yet (owner local test, `docs/local-testing.md`).
"""

import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    import pytest
    from eng_contract.errors import ErrorCode
    from fakes.ports import failure
    from workflows.chain import chain
    from workflows.rig import hold_lock, make_rig, request, steps

    from eng_harness.engine import RunStatus
    from eng_harness.errors import RunLocked
    from eng_harness.journal import is_locked

    @pytest.mark.windows
    def test_killed_holder_releases_the_run_lock(tmp_path: Path) -> None:
        rig = make_rig(tmp_path)
        rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))
        engine = rig.engine(chain(steps("read_a", "read_c")))
        first = asyncio.run(engine.start(request()))
        run_dir = rig.run_dir(first.run_id)
        before = rig.events(first.run_id)
        with hold_lock(run_dir) as holder:
            assert is_locked(run_dir)
            with pytest.raises(RunLocked):
                asyncio.run(engine.resume(first.run_id))
            assert rig.events(first.run_id) == before
            holder.kill()
        assert not is_locked(run_dir)
        assert asyncio.run(engine.resume(first.run_id)).status is RunStatus.COMPLETED
