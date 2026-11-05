"""One engine per run (plan 0001 T9; spec 0001 4.4.4, AC23).

A second engine that opens a run another process holds gets `RunLocked` and the journal stays as it was; when the
holder is killed, the operating system releases the lock and the next engine opens the run. The holder is a child
process, so the lock is the operating system's, not an object of this process. The Windows variant is
`tests/windows/test_run_lock_windows.py`.
"""

import asyncio
from pathlib import Path

import pytest
from eng_contract.errors import ErrorCode
from fakes.ports import Raise, failure
from workflows.chain import chain
from workflows.rig import hold_lock, make_rig, request, steps

from eng_harness.engine import RunStatus
from eng_harness.errors import HarnessCode, RunLocked
from eng_harness.journal import is_locked


def test_one_engine_per_run(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))  # the first run stops after its first step, resumable
    engine = rig.engine(chain(steps("read_a", "read_c")))
    first = asyncio.run(engine.start(request()))
    run_dir = rig.run_dir(first.run_id)
    assert rig.host.locked == [True, True]  # the engine held the lock for both of its calls
    assert not is_locked(run_dir)  # and released it when the run returned
    before = rig.events(first.run_id)
    with hold_lock(run_dir) as holder:
        assert is_locked(run_dir)
        with pytest.raises(RunLocked) as refused:
            asyncio.run(engine.resume(first.run_id))
        assert refused.value.code is HarnessCode.RUN_LOCKED
        assert rig.events(first.run_id) == before  # the journal is unchanged
        assert rig.host.locked == [True, True]  # and the host was not called
        holder.kill()  # the holder dies without releasing anything
    assert not is_locked(run_dir)
    second = asyncio.run(engine.resume(first.run_id))
    assert second.status is RunStatus.COMPLETED
    assert not is_locked(run_dir)


def test_lock_is_released_when_the_run_ends_abnormally(tmp_path: Path) -> None:
    class Crash(BaseException):  # not an engine stop: it leaves the engine as a process crash would
        pass

    rig = make_rig(tmp_path)
    rig.host.script("write_b", Raise(Crash()))
    with pytest.raises(Crash):
        asyncio.run(rig.engine(chain([("write_b", {"n": 0})])).start(request()))
    (run_id,) = rig.run_ids()
    assert not is_locked(rig.run_dir(run_id))
