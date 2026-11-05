"""The run lock over `msvcrt.locking` (spec 0001 4.4.4); runs in the Windows CI job (marker `windows`)."""

import sys
from pathlib import Path

import pytest

from eng_harness._runlock import RunLock
from eng_harness.errors import RunLocked
from eng_harness.journal import is_locked

# Defined only on Windows (as tests/windows/test_jobs.py does), so no skip enters the ratchet.
if sys.platform == "win32":

    @pytest.mark.windows
    def test_windows_lock_excludes_and_releases(tmp_path: Path) -> None:
        first, second = RunLock(tmp_path), RunLock(tmp_path)
        first.acquire()
        assert is_locked(tmp_path)
        with pytest.raises(RunLocked):
            second.acquire()
        first.release()
        assert not is_locked(tmp_path)
        second.acquire()
        second.release()
