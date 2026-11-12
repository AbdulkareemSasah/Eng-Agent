"""Machine-level host-instance lock (plan 0002 T7; spec 0002 AC13, AC14, section 4.4.1).

One lock file per host instance, keyed by program, pid and start time, in a folder shared by every workspace of the
machine. The lock is an exclusive non-blocking OS lock on byte 0 (`_runlock._try_lock`: `fcntl.flock`,
`msvcrt.locking`) held until release or process exit; the OS frees it when the holder dies, so stale locks need no
cleanup. The holder record is JSON from byte 1 on (byte 0 stays free for the Windows byte-range lock, which would
otherwise stop other processes reading the record). Lock files are never deleted. No units are involved.
"""

import json
import logging
import os
import re
from collections.abc import Mapping
from pathlib import Path

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import Clock
from pydantic import BaseModel, ConfigDict

from eng_harness._runlock import _try_lock
from eng_harness.servers._procinfo import ProcessIdentity

logger = logging.getLogger(__name__)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")  # characters kept out of a file name (a Linux start time holds ":")
_RECORD_AT = 1  # the holder record starts after the lock byte


class HolderRecord(BaseModel):
    """Who holds (or last held) the lock of an instance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    engine_pid: int
    engine_started_at: str
    run_id: str
    acquired_at: str


def default_lock_dir(env: Mapping[str, str], *, home: Path, windows: bool) -> Path:
    """The lock folder: `eng/locks` under `LOCALAPPDATA` (Windows), else under `XDG_STATE_HOME` or `~/.local/state`."""
    if windows:
        return Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local") / "eng" / "locks"
    return Path(env.get("XDG_STATE_HOME") or home / ".local" / "state") / "eng" / "locks"


class HostLocks:
    """The locks one engine process holds on host instances."""

    def __init__(self, lock_dir: Path, *, run_id: str, engine: ProcessIdentity, clock: Clock) -> None:
        """Locks go in `lock_dir`; `engine` and `run_id` identify this driver in the holder record."""
        self._dir, self._run_id, self._engine, self._clock = lock_dir, run_id, engine, clock
        self._held: dict[Path, int] = {}

    def path(self, program: str, instance: ProcessIdentity) -> Path:
        """The lock file of `instance`; another start time of the same pid is another file."""
        name = "-".join(_UNSAFE.sub("_", part) for part in (program, str(instance.pid), instance.started_at))
        return self._dir / f"host-{name}.lock"

    def holder(self, program: str, instance: ProcessIdentity) -> HolderRecord | None:
        """The record in the lock file, or None when there is no file or no readable record."""
        path = self.path(program, instance)
        try:
            with path.open("rb") as handle:
                handle.seek(_RECORD_AT)
                return HolderRecord.model_validate_json(handle.read())
        except FileNotFoundError:
            return None
        except ValueError as error:  # a record torn by a crash
            logger.warning("lock file %s holds no readable record: %s", path.name, error)
            return None

    def acquire(self, program: str, instance: ProcessIdentity) -> None:
        """Lock `instance` for this engine; a no-op when it already does.

        Raises:
            ContractError: `HOST_LOCKED` naming the holder's run, when another live engine holds it (never retried).
        """
        path = self.path(program, instance)
        if path in self._held:
            return
        self._dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        locked = _try_lock(fd)
        previous = self.holder(program, instance)  # read after the attempt: the record is then the last holder's
        if not locked:
            os.close(fd)
            run = "unknown" if previous is None else previous.run_id
            raise ContractError(ErrorCode.HOST_LOCKED, f"host instance driven by run {run}")
        if previous is not None:  # the OS released the lock of a holder that died
            logger.warning("took over the lock of %s pid %d from run %s (dead)", program, instance.pid, previous.run_id)
        record = HolderRecord(
            engine_pid=self._engine.pid,
            engine_started_at=self._engine.started_at,
            run_id=self._run_id,
            acquired_at=self._clock.now(),
        )
        data = json.dumps(record.model_dump(), sort_keys=True).encode("utf-8")
        os.lseek(fd, _RECORD_AT, os.SEEK_SET)
        os.write(fd, data)
        os.ftruncate(fd, _RECORD_AT + len(data))
        self._held[path] = fd

    def release_all(self) -> None:
        """Release every lock this object holds; the files stay. Idempotent."""
        for fd in self._held.values():
            _try_lock(fd, lock=False)
            os.close(fd)
        self._held.clear()
