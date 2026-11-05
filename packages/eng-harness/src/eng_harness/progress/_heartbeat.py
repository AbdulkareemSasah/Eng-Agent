"""The heartbeat task, `heartbeat.json` and the liveness reader (spec 0006 section 4.3, AC18).

Purpose: tell a person or `status` that a run is alive while no journal event arrives. The heartbeat is an asyncio task
on the engine loop (not a thread, so a stalled loop stops it). Units: intervals in seconds, ages in milliseconds. The
file is process information, not a journal event. Errors: a file that cannot be written is logged and the beat goes
on; a file that cannot be read counts as missing.
"""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from eng_contract.ids import Clock
from pydantic import BaseModel, ConfigDict, ValidationError

from eng_harness._runlock import is_locked
from eng_harness.progress._render import _ms
from eng_harness.progress._sink import TerminalProgress

_LOG = logging.getLogger("eng_harness.progress")
_FILE = "heartbeat.json"
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class _Beat(BaseModel):
    """The content of `heartbeat.json`."""

    model_config = ConfigDict(extra="forbid", strict=True)

    pid: int
    at: str
    step: str | None
    step_started_at: str | None
    seq: int


@dataclass(frozen=True)
class Liveness:
    """What `status` says about a run folder: `running`, `no_heartbeat` (locked but silent) or `not_running`.

    `age_ms` is the time since the last heartbeat (since the run lock was created when there is no readable file); it is
    None when the run is not running.
    """

    state: Literal["running", "no_heartbeat", "not_running"]
    age_ms: int | None
    step: str | None
    seq: int | None


class Heartbeat:
    """Prints a heartbeat line and rewrites `<run>/heartbeat.json` every `interval_s` seconds."""

    def __init__(
        self,
        sink: TerminalProgress,
        clock: Clock,
        *,
        interval_s: int,
        run_dir: Callable[[], Path | None],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """`run_dir` is read at each beat; None or a folder that does not exist yet means: print, write no file."""
        self._sink, self._clock, self._interval, self._run_dir, self._sleep = sink, clock, interval_s, run_dir, sleep

    async def run(self) -> None:
        """Beat every interval until cancelled."""
        while True:
            await self._sleep(self._interval)
            self.beat()

    def beat(self) -> None:
        """One beat: queue the heartbeat line, then write the file when the run folder exists (never creating it)."""
        now_ms = self._clock.now_ms()
        snap = self._sink.heartbeat(now_ms)
        folder = self._run_dir()
        if folder is None or not folder.is_dir():
            return
        moment = _EPOCH + timedelta(milliseconds=now_ms)
        at = f"{moment:%Y-%m-%dT%H:%M:%S}.{moment.microsecond // 1000:03d}Z"
        beat = _Beat(pid=os.getpid(), at=at, step=snap.step, step_started_at=snap.step_started_at, seq=snap.seq)
        temporary = folder / f"{_FILE}.tmp"
        try:
            temporary.write_text(beat.model_dump_json(), encoding="utf-8")
            os.replace(temporary, folder / _FILE)
        except OSError:
            temporary.unlink(missing_ok=True)
            _LOG.warning("heartbeat file not written in %s", folder.name, exc_info=True)


def read_liveness(run_dir: Path, *, now_ms: int, heartbeat_s: int, stale_after_heartbeats: int) -> Liveness:
    """Combine the run lock and the heartbeat file: locked and fresh is running, locked and older than
    `stale_after_heartbeats` intervals is `no_heartbeat`, not locked is `not_running`.

    A locked run with no readable file ages from the creation of `run.lock`, so that a run that never beats is reported.
    """
    if not is_locked(run_dir):
        return Liveness("not_running", None, None, None)
    beat = _read(run_dir)
    since = (run_dir / "run.lock").stat().st_mtime_ns // 1_000_000 if beat is None else _ms(beat.at)
    age = max(0, now_ms - since)
    stale = age > stale_after_heartbeats * heartbeat_s * 1000
    return Liveness(
        "no_heartbeat" if stale else "running", age, beat.step if beat else None, beat.seq if beat else None
    )


def _read(run_dir: Path) -> _Beat | None:
    try:
        text = (run_dir / _FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        return _Beat.model_validate_json(text)
    except ValidationError:
        _LOG.warning("heartbeat file unreadable in %s", run_dir.name, exc_info=True)
        return None
