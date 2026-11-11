"""The terminal progress sink: a bounded queue and one writer thread (spec 0006 section 4.3, AC19, AC20).

Purpose: `TerminalProgress.emit` formats an event and queues the text; it never touches the stream, so a consumer that
stops reading its pipe cannot stall the engine. When the queue is full the oldest line is dropped and counted, and the
count is written before the next lines (a display loss only: the journal is complete). Units: queue size in lines.
Errors: `emit` raises whatever the renderer raises, so that the engine detaches the sink; a failing stream is logged
once and ends the output.
"""

import json
import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from eng_harness.journal import Event, EventType
from eng_harness.journal import _events as ev
from eng_harness.progress._render import Mode, ProgressRenderer

_LOG = logging.getLogger("eng_harness.progress")
_ENDING = (EventType.STEP_COMPLETED, EventType.STEP_FAILED, EventType.STEP_RECONCILED, EventType.STEP_RERUN)


class TextStream(Protocol):
    """The part of a text stream that the writer thread uses."""

    def write(self, text: str, /) -> int:
        """Write text; may block."""
        ...

    def flush(self) -> None:
        """Flush; may block."""
        ...


@dataclass(frozen=True)
class Snapshot:
    """What the heartbeat reports: the last journal sequence number and the oldest running step."""

    seq: int
    step: str | None
    step_started_at: str | None


class TerminalProgress:
    """A `ProgressSink` that writes renderer output to a stream from its own thread."""

    def __init__(self, renderer: ProgressRenderer, stream: TextStream, *, mode: Mode, queue_lines: int) -> None:
        """Start the writer thread (a daemon, so a blocked stream cannot keep the process alive)."""
        self._renderer, self._stream, self._mode, self._cap = renderer, stream, mode, queue_lines
        self._cond = threading.Condition()
        self._queue: deque[str] = deque()
        self._dropped, self._closed, self._broken = 0, False, False
        self._seq = 0
        self._running: dict[tuple[str, int], tuple[str, str]] = {}  # (path, attempt) -> (name, started_at)
        self._thread = threading.Thread(target=self._drain, name="eng-progress-writer", daemon=True)
        self._thread.start()

    def emit(self, event: Event) -> None:
        """Format `event` and queue the text; returns at once, whatever the stream does.

        Raises:
            Exception: whatever the renderer raises (not swallowed, so that the engine can detach this sink).
        """
        text = self._renderer.feed(event)
        self._seq = event.seq
        key = (event.path or "", event.attempt or 0)
        if isinstance(event.payload, ev.StepStarted):
            self._running[key] = (event.payload.name, event.at)
        elif event.type in _ENDING:
            self._running.pop(key, None)
        if text:
            self.write(text)

    def write(self, text: str) -> None:
        """Queue text that is not an event line (a heartbeat line); never blocks."""
        if self._broken:
            return
        with self._cond:
            if len(self._queue) >= self._cap:
                self._queue.popleft()
                self._dropped += 1
            self._queue.append(text)
            self._cond.notify()

    def heartbeat(self, now_ms: int) -> Snapshot:
        """Queue the heartbeat line for `now_ms` and return the state for `heartbeat.json`."""
        self.write(self._renderer.heartbeat_line(now_ms, self._seq))
        name, started_at = min(self._running.values(), key=lambda r: r[1], default=(None, None))
        return Snapshot(self._seq, name, started_at)

    def close(self, timeout_s: float = 5.0) -> None:
        """Let the writer drain the queue and stop; a writer stuck in a blocked write is abandoned after `timeout_s`."""
        with self._cond:
            self._closed = True
            self._cond.notify()
        self._thread.join(timeout_s)
        if self._thread.is_alive():
            _LOG.warning("progress writer still blocked after %s s; abandoned", timeout_s)

    def _notice(self, count: int) -> str:
        if self._mode == "json":
            return json.dumps({"event": "progress_dropped", "count": count}) + "\n"
        return f"progress: {count} lines dropped (display only, the journal is complete)\n"

    def _drain(self) -> None:
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._queue or self._closed)
                if not self._queue:
                    return
                batch, dropped = "".join(self._queue), self._dropped
                self._queue.clear()
                self._dropped = 0
            try:
                self._stream.write((self._notice(dropped) if dropped else "") + batch)
                self._stream.flush()
            except OSError, ValueError:
                _LOG.warning(
                    "progress output stream failed; progress output ends (the journal is complete)", exc_info=True
                )
                self._broken = True
                return
