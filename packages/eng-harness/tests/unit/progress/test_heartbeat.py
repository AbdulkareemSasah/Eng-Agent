"""Heartbeat task, `heartbeat.json` and the liveness reader (plan 0006 T5; spec 0006 AC18)."""

import asyncio
import io
import json
import logging
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from eng_contract.ids import FixedClock

from eng_harness._runlock import RunLock
from eng_harness.journal import PAYLOAD_MODELS, Event, EventType
from eng_harness.progress import ExpectedTimes, Heartbeat, Liveness, ProgressRenderer, TerminalProgress, read_liveness

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
SHA = "a" * 64
STARTED = {"kind": "tool", "name": "read_model", "args": {}, "args_sha256": SHA, "effect": "read"}


def _started() -> Event:
    payload = PAYLOAD_MODELS[EventType.STEP_STARTED].model_validate(STARTED)
    return Event(2, EventType.STEP_STARTED, "0", 1, "2026-01-01T00:00:00.000Z", payload)


class _Out(io.StringIO):
    """A stream that stays readable after the sink closes it."""


def _setup(run_dir: Path | None, step_ms: int = 10_000) -> tuple[TerminalProgress, Heartbeat, _Out]:
    out = _Out()
    sink = TerminalProgress(ProgressRenderer("plain", ExpectedTimes({})), out, mode="plain", queue_lines=100)
    sink.emit(_started())
    clock = FixedClock(START_MS + 10_000, step_ms)
    return sink, Heartbeat(sink, clock, interval_s=10, run_dir=lambda: run_dir), out


def test_heartbeat_without_events(tmp_path: Path) -> None:
    sink, beat, out = _setup(tmp_path)
    beat.beat()
    first = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert first == {
        "pid": os.getpid(), "at": "2026-01-01T00:00:10.000Z", "step": "read_model",
        "step_started_at": "2026-01-01T00:00:00.000Z", "seq": 2,
    }  # fmt: skip
    beat.beat()  # no journal event in between: the file is rewritten with the new time
    second = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert second["at"] == "2026-01-01T00:00:20.000Z"
    assert second["seq"] == 2
    assert list(tmp_path.iterdir()) == [tmp_path / "heartbeat.json"]  # no temporary file is left behind
    sink.close()
    assert out.getvalue().splitlines() == [
        "heartbeat: read_model still running, 00:10, no estimate, journal seq 2",
        "heartbeat: read_model still running, 00:20, no estimate, journal seq 2",
    ]


def test_loop_beats_after_each_interval(tmp_path: Path) -> None:
    sink, _, out = _setup(tmp_path)
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) > 3:
            raise asyncio.CancelledError

    looped = Heartbeat(
        sink, FixedClock(START_MS + 10_000, 10_000), interval_s=10, run_dir=lambda: tmp_path, sleep=sleep
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(looped.run())
    sink.close()
    assert sleeps == [10, 10, 10, 10]
    assert out.getvalue().count("heartbeat:") == 3
    assert json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))["at"] == "2026-01-01T00:00:30.000Z"


@pytest.mark.parametrize("known", [False, True])
def test_unknown_or_missing_run_folder_prints_but_writes_nothing(tmp_path: Path, known: bool) -> None:
    folder = tmp_path / "runs" / "run_x" if known else None
    sink, beat, out = _setup(folder)
    beat.beat()
    sink.close()
    assert "heartbeat: read_model still running" in out.getvalue()
    assert not (tmp_path / "runs").exists()  # the heartbeat never creates the folder


def test_failed_file_write_is_logged_and_the_beat_goes_on(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "heartbeat.json").mkdir()  # a directory in the way: the rename fails
    sink, beat, out = _setup(tmp_path)
    with caplog.at_level(logging.WARNING, logger="eng_harness.progress"):
        beat.beat()
    sink.close()
    assert "heartbeat file not written" in caplog.text
    assert "heartbeat: read_model" in out.getvalue()


@pytest.fixture
def locked(run_dir: Path) -> Iterator[Path]:
    lock = RunLock(run_dir)
    lock.acquire()
    yield run_dir
    lock.release()


def _stamp(ms: int) -> str:
    """The contract timestamp of `ms`, written out here so the test does not use the code under test."""
    moment = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=ms)
    return f"{moment:%Y-%m-%dT%H:%M:%S}.{moment.microsecond // 1000:03d}Z"


def _write_beat(run_dir: Path, at_ms: int, **extra: Any) -> None:
    body = {"pid": 1, "at": "2026-01-01T00:00:00.000Z", "step": "s", "step_started_at": None, "seq": 7, **extra}
    body["at"] = _stamp(at_ms)
    (run_dir / "heartbeat.json").write_text(json.dumps(body), encoding="utf-8")


def _live(run_dir: Path, now_ms: int) -> Liveness:
    return read_liveness(run_dir, now_ms=now_ms, heartbeat_s=10, stale_after_heartbeats=3)


def test_locked_and_fresh_is_running(locked: Path) -> None:
    _write_beat(locked, START_MS)
    assert _live(locked, START_MS + 30_000) == Liveness("running", 30_000, "s", 7)  # exactly 3 intervals is not older


def test_locked_and_stale_reports_no_heartbeat_with_age(locked: Path) -> None:
    _write_beat(locked, START_MS)
    assert _live(locked, START_MS + 30_001) == Liveness("no_heartbeat", 30_001, "s", 7)


def test_not_locked_is_not_running_whatever_the_file(run_dir: Path) -> None:
    _write_beat(run_dir, START_MS)
    assert _live(run_dir, START_MS + 10_000_000).state == "not_running"


def test_locked_without_file_ages_from_the_lock_file(locked: Path) -> None:
    os.utime(locked / "run.lock", (START_MS / 1000, START_MS / 1000))
    assert _live(locked, START_MS + 5_000) == Liveness("running", 5_000, None, None)
    assert _live(locked, START_MS + 100_000) == Liveness("no_heartbeat", 100_000, None, None)


def test_unreadable_file_counts_as_missing_and_is_logged(locked: Path, caplog: pytest.LogCaptureFixture) -> None:
    (locked / "heartbeat.json").write_text("{not json", encoding="utf-8")
    os.utime(locked / "run.lock", (START_MS / 1000, START_MS / 1000))
    with caplog.at_level(logging.WARNING, logger="eng_harness.progress"):
        assert _live(locked, START_MS + 100_000).state == "no_heartbeat"
    assert "heartbeat file unreadable" in caplog.text
