"""The non-blocking terminal sink (plan 0006 T5; spec 0006 AC19)."""

import json
import logging
import threading
import time
from typing import Any

import pytest

from eng_harness.journal import PAYLOAD_MODELS, Event, EventType
from eng_harness.progress import ExpectedTimes, Mode, ProgressRenderer, TerminalProgress

SHA = "a" * 64
SAVED = {
    "model_key": "m", "model_id": "mdl_" + "0" * 26, "revision": 1, "fingerprint": "f", "file_sha256": SHA,
    "file_name": "a.edb", "role": "working_copy",
}  # fmt: skip
STARTED = {"kind": "tool", "name": "read_model", "args": {}, "args_sha256": SHA, "effect": "read"}


def _saved(i: int) -> Event:
    payload = PAYLOAD_MODELS[EventType.MODEL_SAVED].model_validate({**SAVED, "file_name": f"m{i}.edb"})
    return Event(i, EventType.MODEL_SAVED, None, None, "2026-01-01T00:00:00.000Z", payload)


class _BlockingStream:
    """A pipe nobody reads until `release` is set: a write blocks."""

    def __init__(self) -> None:
        self.entered, self.release = threading.Event(), threading.Event()
        self.text = ""

    def write(self, text: str) -> int:
        self.entered.set()
        assert self.release.wait(10), "test did not release the stream"
        self.text += text
        return len(text)

    def flush(self) -> None:
        return None


class _Broken:
    def write(self, text: str) -> int:
        raise BrokenPipeError(text)

    def flush(self) -> None:
        return None


class _Raising(ProgressRenderer):
    def feed(self, event: Event) -> str:
        raise RuntimeError("renderer defect")


def _sink(stream: Any, mode: Mode = "plain", queue_lines: int = 3) -> TerminalProgress:
    return TerminalProgress(ProgressRenderer(mode, ExpectedTimes({})), stream, mode=mode, queue_lines=queue_lines)


def test_blocked_stream_does_not_block_engine() -> None:
    stream = _BlockingStream()
    sink = _sink(stream, queue_lines=2)
    sink.emit(_saved(0))
    assert stream.entered.wait(10)  # the writer thread now sits inside a blocked write
    slowest = 0.0
    for i in range(1, 200):
        started = time.perf_counter()
        sink.emit(_saved(i))
        slowest = max(slowest, time.perf_counter() - started)
    assert slowest < 0.010  # AC19: emit returns within 10 ms
    stream.release.set()
    sink.close()


def test_full_queue_drops_oldest_and_prints_count() -> None:
    stream = _BlockingStream()
    sink = _sink(stream, queue_lines=3)
    sink.emit(_saved(0))
    assert stream.entered.wait(10)
    for i in range(1, 11):
        sink.emit(_saved(i))
    stream.release.set()
    sink.close()
    lines = stream.text.splitlines()
    assert lines[0].startswith("model saved: m0.edb")
    assert lines[1] == "progress: 7 lines dropped (display only, the journal is complete)"
    assert [line.split()[2] for line in lines[2:]] == ["m8.edb", "m9.edb", "m10.edb"]


def test_json_mode_drop_notice_is_a_json_object() -> None:
    stream = _BlockingStream()
    sink = _sink(stream, mode="json", queue_lines=1)
    sink.emit(_saved(0))
    assert stream.entered.wait(10)
    for i in range(1, 4):
        sink.emit(_saved(i))
    stream.release.set()
    sink.close()
    rows = [json.loads(line) for line in stream.text.splitlines()]
    assert rows[1] == {"event": "progress_dropped", "count": 2}
    assert [r["name"] for r in rows if "name" in r] == ["m0.edb", "m3.edb"]


def test_lines_arrive_in_order_and_silent_events_write_nothing() -> None:
    stream = _BlockingStream()
    stream.release.set()
    sink = _sink(stream, queue_lines=100)
    started = PAYLOAD_MODELS[EventType.STEP_STARTED].model_validate(STARTED)
    sink.emit(Event(1, EventType.STEP_STARTED, "0", 1, "2026-01-01T00:00:00.000Z", started))  # plain mode: no line
    for i in range(5):
        sink.emit(_saved(i + 2))
    sink.close()
    assert [line.split()[2] for line in stream.text.splitlines()] == [f"m{i + 2}.edb" for i in range(5)]


def test_raising_renderer_makes_emit_raise() -> None:
    stream = _BlockingStream()
    stream.release.set()
    sink = TerminalProgress(_Raising("plain", ExpectedTimes({})), stream, mode="plain", queue_lines=3)
    with pytest.raises(RuntimeError, match="renderer defect"):
        sink.emit(_saved(0))
    sink.close()
    assert stream.text == ""


def test_broken_stream_is_logged_and_never_blocks_emit(caplog: pytest.LogCaptureFixture) -> None:
    sink = _sink(_Broken())
    with caplog.at_level(logging.WARNING, logger="eng_harness.progress"):
        sink.emit(_saved(0))
        sink.close()
        for i in range(1, 50):
            sink.emit(_saved(i))  # after the failure emit is a cheap no-op and does not raise
    assert any("progress output stream failed" in r.getMessage() for r in caplog.records)
