"""The scripted journal the edit-cycle report tests share (plan 0007 T10; spec 0007 section 4.9).

`Script` writes events with chosen times into a real journal. Times are seconds after the run start.
"""

from pathlib import Path
from typing import Any

from eng_contract.envelope import Provenance
from eng_contract.ids import IdSource
from eng_contract.store import ResultStore
from fixtures.report_run import SHA, START_MS, ScriptedClock

from eng_harness.journal import EventType, JournalWriter

PRODUCER = Provenance(tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0)
_BLOCK = {"name": "edit_cycle_once", "version": "1", "code_sha256": SHA}
_KINDS = EventType


class Script:
    """Writes events with chosen times into a real journal."""

    def __init__(self, run_dir: Path, store: ResultStore, ids: IdSource) -> None:
        """Open the journal and store the blob every event reference points at."""
        self.store = store
        self.clock = ScriptedClock()
        self.writer = JournalWriter(run_dir, store, self.clock, ids)
        self.base = store.put("harness.journal_blob/1", {"value": 1}, PRODUCER).result_id

    def at(self, seconds: float, type_: EventType, payload: dict[str, Any], path: str | None = None) -> None:
        """Append one event at `seconds` after the start."""
        self.clock.ms = START_MS + int(seconds * 1000)
        self.writer.append(type_, payload, path=path, attempt=1 if path else None)

    def step(
        self, path: str, kind: str, name: str, start: float, ms: int, lasted: float | None = None, **extra: Any
    ) -> None:
        """A step started at `start`, recorded as `ms` long and completed `lasted` seconds later (default `ms`)."""
        body = {"kind": kind, "name": name, "args": {}, "args_sha256": SHA, "effect": "read", **extra}
        result = {"ref": self.base, "summary": {}, "warnings": [], "complete": True}
        self.at(start, _KINDS.STEP_STARTED, body, path)
        self.at(
            start + (ms / 1000 if lasted is None else lasted),
            _KINDS.STEP_COMPLETED,
            {"result": result, "duration_ms": ms},
            path,
        )

    def fail(self, path: str, kind: str, name: str, start: float, ms: int) -> None:
        """A step started at `start` that failed `ms` later."""
        body = {"kind": kind, "name": name, "args": {}, "args_sha256": SHA, "effect": "read"}
        error = {"harness_code": "NEEDS_ENGINEER", "message": "m"}
        self.at(start, _KINDS.STEP_STARTED, body, path)
        self.at(start + ms / 1000, _KINDS.STEP_FAILED, {"error": error, "retryable": False, "duration_ms": ms}, path)

    def started(self, path: str, kind: str, name: str, start: float) -> None:
        """A step that started and has not ended."""
        body = {"kind": kind, "name": name, "args": {}, "args_sha256": SHA, "effect": "read"}
        self.at(start, _KINDS.STEP_STARTED, body, path)

    def answer(self, label: str | None) -> str:
        """The stored change-set answer, carrying the optional `benchmark_request` label."""
        who = {"unit": None, "entered_by": "x", "entered_at": "2026-01-01T00:00:00.000Z"}
        fields: dict[str, Any] = {} if label is None else {"benchmark_request": {"value": label, **who}}
        body: dict[str, Any] = {"step": "1", "fields": fields}
        return self.store.put("basis.engineer_input/1", body, PRODUCER).result_id

    def asked(self, rid: str, kind: str, title: str, start: float, wait: float, label: str | None = None) -> None:
        """An input request answered `wait` seconds later by the engineer."""
        self.at(
            start,
            _KINDS.INPUT_REQUESTED,
            {"request_id": rid, "kind": kind, "title": title, "fields_schema_sha256": SHA},
        )
        reply = {"request_id": rid, "answer_ref": self.answer(label), "by": "engineer:x"}
        self.at(start + wait, _KINDS.INPUT_PROVIDED, reply)

    def approval(self, rid: str, kind: str, start: float, wait: float | None, by: str = "engineer:x") -> None:
        """An approval request answered `wait` seconds later by `by` (never, when `wait` is None)."""
        shown = {"request_id": rid, "kind": kind, "title": rid, "shown_sha256": SHA, "binding": {}, "items": []}
        self.at(start, _KINDS.APPROVAL_REQUESTED, {**shown, "preview_ref": self.base})
        if wait is None:
            return
        resolved = {"request_id": rid, "shown_sha256": SHA, "decision": "approve", "rejected_items": [], "by": by}
        self.at(start + wait, _KINDS.APPROVAL_RESOLVED, resolved)

    def decision(self, rid: str, point: str, choice: str, start: float, wait: float) -> None:
        """An engineer decision request answered `wait` seconds later."""
        asked = {"request_id": rid, "kind": "engine.decision", "title": point, "fields_schema_sha256": SHA}
        self.at(start, _KINDS.INPUT_REQUESTED, asked)
        made = {
            "point": point, "options": [choice], "choice": choice, "decided_by": "engineer:x", "confidence": None,
            "latency_ms": 0, "state_sha256": SHA, "suggestions": [], "request_id": rid,
        }  # fmt: skip
        self.at(start + wait, _KINDS.DECISION_MADE, made, None)

    def begin(self, path: str, start: float) -> None:
        """The `edit_cycle_once` block step at `path` starts."""
        body = {
            "kind": "block",
            "name": "edit_cycle_once",
            "args": {},
            "args_sha256": SHA,
            "effect": "read",
            "child": _BLOCK,
        }
        self.at(start, _KINDS.STEP_STARTED, body, path)

    def end(self, path: str, start: float, end: float) -> None:
        """The block step at `path`, started at `start`, completes at `end`."""
        done = {"output_ref": self.base, "duration_ms": int((end - start) * 1000)}
        self.at(end, _KINDS.STEP_COMPLETED, done, path)
