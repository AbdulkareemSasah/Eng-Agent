"""The run lock: one engine per run (spec 0001 section 4.4.4).

Purpose: an exclusive, non-blocking OS lock on `<run_dir>/run.lock` (`fcntl.flock` on POSIX, `msvcrt.locking` on
Windows), released by the OS when the process dies. Errors: `RunLocked` when another holder has it.
"""

import os
import sys
from pathlib import Path

from eng_harness.errors import RunLocked

if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class RunLock:
    """The lock of one run folder."""

    def __init__(self, run_dir: Path) -> None:
        """Name the lock file `<run_dir>/run.lock`; nothing is opened yet."""
        self._path = run_dir / "run.lock"
        self._fd: int | None = None

    def acquire(self) -> None:
        """Take the lock, creating the file if needed.

        Raises:
            RunLocked: another engine holds it (also when this object already holds it).
        """
        if self._fd is not None:
            raise RunLocked(f"run lock {self._path.name} is already held")
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
        if not _try_lock(fd):
            os.close(fd)
            raise RunLocked(f"run is locked by another engine: {self._path.parent.name}")
        self._fd = fd

    def release(self) -> None:
        """Release the lock; a no-op when not held."""
        if self._fd is not None:
            _unlock(self._fd)
            os.close(self._fd)
            self._fd = None


def is_locked(run_dir: Path) -> bool:
    """True when a live engine holds the lock of `run_dir`. Tries the lock and releases it at once; never creates it."""
    try:
        fd = os.open(run_dir / "run.lock", os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        if _try_lock(fd):
            _unlock(fd)
            return False
        return True
    finally:
        os.close(fd)
