"""The progress renderer: journal events to terminal, plain or JSON text (spec 0006 section 4.3, AC16, AC17, AC21).

Purpose: pure formatting of text. No I/O and no clock: times come from the event timestamps or from the `now_ms`
argument (milliseconds since the Unix epoch). Data-derived text goes through `sanitize_terminal`. The launch address
and tokens are never inputs here, so they cannot appear in the output.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from eng_harness._text import format_duration_ms, sanitize_terminal
from eng_harness.journal import Event, EventType
from eng_harness.journal import _events as ev
from eng_harness.progress._expected import ExpectedTimes

Mode = Literal["terminal", "plain", "json"]
_ERASE = "\r\x1b[2K"
_MAX_SHOWN = 3  # running steps shown on the live line (spec 0006 section 4.3)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_Record = tuple[str | None, int | None, int | None]  # name, elapsed_ms, expected_ms


@dataclass(frozen=True)
class _Running:
    kind: str
    name: str
    started_ms: int


def _ms(at: str) -> int:
    """Milliseconds since the epoch of a contract timestamp, by integer arithmetic."""
    delta = datetime.fromisoformat(at) - _EPOCH
    return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000


class ProgressRenderer:
    """Turns events into the text to write, one mode per instance; events must arrive in journal order."""

    def __init__(self, mode: Mode, expected: ExpectedTimes) -> None:
        """Start with no run, no running step and no open request."""
        self._mode = mode
        self._expected = expected
        self._run_ms: int | None = None
        self._workflow = ""
        self._running: dict[tuple[str, int], _Running] = {}
        self._requests: dict[str, tuple[str, int]] = {}

    def feed(self, event: Event) -> str:
        """The text for one event ("" when the event shows nothing); persistent lines end with a line feed.

        Terminal mode puts an erase sequence before each line and rewrites the live line after it.
        """
        now = _ms(event.at)
        line, record = self._apply(event, now)
        if record is None:
            return ""
        if self._mode == "json":
            fields = {"at": event.at, "event": event.type.value, "path": event.path}
            return (
                json.dumps({**fields, **dict(zip(("name", "elapsed_ms", "expected_ms"), record, strict=True))}) + "\n"
            )
        if self._mode == "plain":
            return f"{line}\n" if line else ""
        live = self._live(now)
        return (f"{_ERASE}{line}\n" if line else "") + (f"{_ERASE}{live}" if live or not line else "")

    def tick(self, now_ms: int) -> str:
        """The live line rewritten for the time `now_ms` (terminal mode only; "" otherwise)."""
        return f"{_ERASE}{self._live(now_ms)}" if self._mode == "terminal" else ""

    def heartbeat_line(self, now_ms: int, seq: int) -> str:
        """`heartbeat: <step> still running, <elapsed>, <expected>, journal seq N` (not used in JSON mode)."""
        if self._mode == "json":
            return ""
        if not self._running:
            return f"heartbeat: no step running, journal seq {seq}\n"
        step = min(self._running.values(), key=lambda r: r.started_ms)
        elapsed = format_duration_ms(max(0, now_ms - step.started_ms))
        expected = self._expected.describe(step.kind, step.name)
        return f"heartbeat: {sanitize_terminal(step.name)} still running, {elapsed}, {expected}, journal seq {seq}\n"

    def _live(self, now: int) -> str:
        if self._requests:
            title, since = next(iter(self._requests.values()))
            return f"waiting for engineer: {title}, {format_duration_ms(max(0, now - since))}"
        if not self._running:
            return ""
        shown = sorted(self._running.values(), key=lambda r: r.started_ms)[:_MAX_SHOWN]
        parts = [
            f"step {sanitize_terminal(r.name)} {format_duration_ms(max(0, now - r.started_ms))}, "
            f"{self._expected.describe(r.kind, r.name)}"
            for r in shown
        ]
        if len(self._running) > _MAX_SHOWN:
            parts.append(f"+{len(self._running) - _MAX_SHOWN} more")
        run = format_duration_ms(max(0, now - (self._run_ms if self._run_ms is not None else now)))
        return " | ".join([f"run {run}", *parts])

    def _apply(self, event: Event, now: int) -> tuple[str | None, _Record | None]:
        """Update the state; return the persistent line and the JSON record (None record: nothing to show)."""
        p, key = event.payload, (event.path or "", event.attempt or 0)
        label = f"{sanitize_terminal(event.path or '')}"
        if isinstance(p, ev.RunHeader):
            self._run_ms, self._workflow = now, sanitize_terminal(p.workflow)
            return f"run started: {self._workflow} ({p.mode})", (self._workflow, 0, None)
        if isinstance(p, ev.StepStarted):
            self._running[key] = _Running(p.kind, p.name, now)
            return None, (sanitize_terminal(p.name), 0, self._est(p.kind, p.name))
        if isinstance(p, ev.StepCompleted | ev.StepFailed | ev.StepReconciled | ev.StepRerun):
            run = self._running.pop(key, _Running("?", "?", now))
            name, expected = sanitize_terminal(run.name), self._est(run.kind, run.name)
            if isinstance(p, ev.StepRerun):
                return None, (name, None, expected)
            if isinstance(p, ev.StepReconciled):
                return f"reconciled: {name} [{label}] {p.outcome}", (name, None, expected)
            took = format_duration_ms(p.duration_ms)
            word = "done" if isinstance(p, ev.StepCompleted) else "failed"
            return f"{word}: {name} [{label}] {took}", (name, p.duration_ms, expected)
        if isinstance(p, ev.DecisionMade):
            choice = p.choice if isinstance(p.choice, str) else json.dumps(p.choice)
            point = sanitize_terminal(p.point)
            return f"decision: {point} -> {sanitize_terminal(choice)}", (point, None, None)
        if isinstance(p, ev.ApprovalRequested | ev.InputRequested):
            title = sanitize_terminal(p.title)
            self._requests[p.request_id] = (title, now)
            return f"waiting for engineer: {title}, {format_duration_ms(0)}", (title, 0, None)
        if isinstance(p, ev.ApprovalResolved | ev.InputProvided):
            asked, since = self._requests.pop(p.request_id, (None, now))
            text = f"approval: {p.decision}" if isinstance(p, ev.ApprovalResolved) else "input provided"
            return text, (asked, now - since, None)
        return self._run_event(event, now)

    def _run_event(self, event: Event, now: int) -> tuple[str | None, _Record | None]:
        p = event.payload
        run = format_duration_ms(max(0, now - (self._run_ms if self._run_ms is not None else now)))
        if isinstance(p, ev.ModelSaved):
            return f"model saved: {sanitize_terminal(p.file_name)} (revision {p.revision})", (p.file_name, None, None)
        if isinstance(p, ev.RunEscalated):
            return f"escalated: {p.reason}", (None, None, None)
        if event.type is EventType.RUN_PAUSED and isinstance(p, ev.RunPaused):
            return f"run paused: {p.reason}", (None, None, None)
        if event.type is EventType.RUN_RESUMED:
            return "run resumed", (None, None, None)
        if event.type in (EventType.RUN_COMPLETED, EventType.RUN_FAILED):
            elapsed = max(0, now - (self._run_ms if self._run_ms is not None else now))
            word = "completed" if event.type is EventType.RUN_COMPLETED else "failed"
            return f"run {word}, {run}", (self._workflow, elapsed, None)
        return None, None

    def _est(self, kind: str, name: str) -> int | None:
        found = self._expected.lookup(kind, name)
        return found.median_ms if found else None
