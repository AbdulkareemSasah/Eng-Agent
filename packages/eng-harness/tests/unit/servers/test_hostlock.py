"""Machine-level host-instance lock (plan 0002 T7; spec 0002 AC13, AC14, section 4.4.1).

Two `HostLocks` objects in one process stand for two engine processes: the OS lock belongs to the open file, so the
second one is refused exactly as another process would be. A holder that died is simulated by releasing its handles,
which is what the OS does when the process ends.
"""

import logging
from pathlib import Path

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock

from eng_harness.servers._hostlock import HolderRecord, HostLocks, default_lock_dir
from eng_harness.servers._procinfo import ProcessIdentity

INSTANCE = ProcessIdentity(pid=100, started_at="boot:5000", exe_name="ETABS.exe")
REUSED = ProcessIdentity(pid=100, started_at="boot:9000", exe_name="ETABS.exe")


def _locks(lock_dir: Path, run_id: str, engine_pid: int = 11) -> HostLocks:
    engine = ProcessIdentity(pid=engine_pid, started_at=f"boot:{engine_pid}", exe_name="python")
    return HostLocks(lock_dir, run_id=run_id, engine=engine, clock=FixedClock(1_700_000_000_000))


def test_second_driver_refused(tmp_path: Path) -> None:
    first, second = _locks(tmp_path, "run-A"), _locks(tmp_path, "run-B", engine_pid=12)
    first.acquire("ETABS", INSTANCE)
    with pytest.raises(ContractError) as refused:
        second.acquire("ETABS", INSTANCE)
    assert refused.value.detail.code is ErrorCode.HOST_LOCKED
    assert refused.value.detail.retryable is False
    assert "run-A" in refused.value.detail.message
    assert "run-B" not in refused.value.detail.message
    first.release_all()  # a release frees the instance for the second driver
    second.acquire("ETABS", INSTANCE)


def test_stale_and_pid_reuse(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    dead = _locks(tmp_path, "run-A")
    dead.acquire("ETABS", INSTANCE)
    dead.release_all()  # the holder died: the OS released its lock, the file stays
    taker = _locks(tmp_path, "run-B", engine_pid=12)
    with caplog.at_level(logging.WARNING, logger="eng_harness.servers._hostlock"):
        taker.acquire("ETABS", INSTANCE)
    assert any("run-A" in record.getMessage() and "took over" in record.getMessage() for record in caplog.records)
    holder = taker.holder("ETABS", INSTANCE)
    assert holder is not None
    assert holder.run_id == "run-B"
    # The same pid with another start time is another instance, hence another lock file: no conflict with a live holder.
    other = _locks(tmp_path, "run-C", engine_pid=13)
    other.acquire("ETABS", REUSED)
    assert taker.path("ETABS", INSTANCE) != other.path("ETABS", REUSED)


def test_holder_record_and_file_name(tmp_path: Path) -> None:
    locks = _locks(tmp_path, "run-A")
    assert locks.holder("ETABS", INSTANCE) is None  # no file yet
    locks.acquire("ETABS", INSTANCE)
    assert locks.path("ETABS", INSTANCE) == tmp_path / "host-ETABS-100-boot_5000.lock"
    assert locks.holder("ETABS", INSTANCE) == HolderRecord(
        engine_pid=11, engine_started_at="boot:11", run_id="run-A", acquired_at="2023-11-14T22:13:20.000Z"
    )


def test_acquire_again_is_a_no_op_and_files_stay(tmp_path: Path) -> None:
    locks = _locks(tmp_path, "run-A")
    locks.acquire("ETABS", INSTANCE)
    locks.acquire("ETABS", INSTANCE)  # idempotent for the holder
    locks.release_all()
    locks.release_all()
    assert locks.path("ETABS", INSTANCE).exists()  # lock files are never deleted (spec 4.4.1)
    locks.acquire("ETABS", INSTANCE)  # and can be taken again


def test_refusal_without_a_readable_record(tmp_path: Path) -> None:
    first, second = _locks(tmp_path, "run-A"), _locks(tmp_path, "run-B", engine_pid=12)
    first.acquire("ETABS", INSTANCE)
    first.path("ETABS", INSTANCE).write_bytes(b"\0not json")  # a record torn by a crash; byte 0 is the lock byte
    with pytest.raises(ContractError, match="unknown") as refused:
        second.acquire("ETABS", INSTANCE)
    assert refused.value.detail.code is ErrorCode.HOST_LOCKED


def test_default_lock_dir() -> None:
    home = Path("/home/engineer")
    assert default_lock_dir({"XDG_STATE_HOME": "/state"}, home=home, windows=False) == Path("/state/eng/locks")
    assert default_lock_dir({}, home=home, windows=False) == home / ".local" / "state" / "eng" / "locks"
    assert default_lock_dir({"XDG_STATE_HOME": ""}, home=home, windows=False) == home / ".local/state/eng/locks"
    assert default_lock_dir({"LOCALAPPDATA": "/appdata"}, home=home, windows=True) == Path("/appdata/eng/locks")
