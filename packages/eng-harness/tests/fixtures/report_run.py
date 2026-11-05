"""A scripted run for the report tests (plan 0006 T11; reused by T12 and T13).

Purpose: write a real journal with chosen event times, so that timings can be checked against sums stated here.
Units: milliseconds unless the name says seconds. Errors: none beyond the journal writer's.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eng_contract.ids import FixedClock, IdSource
from eng_contract.store import ResultStore

from eng_harness.journal import EventType, JournalWriter

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
REF = "res_" + "0" * 26
SHA = "a" * 64

HEADER: dict[str, Any] = {
    "run_id": "run_x", "workflow": "w", "block": {"name": "b", "version": "1", "code_sha256": SHA},
    "input_ref": REF, "input_sha256": SHA, "basis_ref": REF, "mode": "work_on_copy", "run_class": "trial",
    "engine_version": "1", "contract_version": "eng-contract/1", "settings_sha256": SHA, "servers": [],
    "always_ask": [],
}  # fmt: skip
STARTED = {"kind": "tool", "name": "t", "args": {}, "args_sha256": SHA, "effect": "read"}
INPUT = {"request_id": "in1", "kind": "block", "title": "t", "fields_schema_sha256": SHA}
DECISION_REQUEST = {"request_id": "dec1", "kind": "engine.decision", "title": "t", "fields_schema_sha256": SHA}
APPROVAL = {
    "request_id": "ap1", "kind": "INFO", "title": "t", "preview_ref": REF, "shown_sha256": SHA, "binding": {},
    "items": [],
}  # fmt: skip
APPROVED = {"request_id": "ap1", "shown_sha256": SHA, "decision": "approve", "rejected_items": [], "by": "engineer:x"}
DECISION = {
    "point": "p", "options": ["a", "b"], "choice": "a", "decided_by": "engineer:x", "confidence": None,
    "latency_ms": 0, "state_sha256": SHA, "suggestions": [], "request_id": "dec1",
}  # fmt: skip

WAIT_MS = 60_000 + 30_000 + 5_000
"""Approval 60 s, input 30 s and engine decision 5 s."""
MACHINE_MS = 2_000 + 5_000
"""Completed steps "0" (2 s) and "1" (5 s); the failed step "2" (1.5 s) is not machine time."""
EVENT_COUNT = 15


class ScriptedClock:
    """A clock that returns the time last set (the writer reads it once per event)."""

    def __init__(self) -> None:
        """Start at `START_MS`."""
        self.ms = START_MS

    def now_ms(self) -> int:
        """The time last set."""
        return self.ms

    def now(self) -> str:
        """The time last set as a contract timestamp."""
        return FixedClock(self.ms).now()


@dataclass(frozen=True)
class ReportRun:
    """The scripted run and the sums stated for it."""

    run_dir: Path
    wait_ms: int
    machine_ms: int
    resumes: int


def build_report_run(run_dir: Path, store: ResultStore, ids: IdSource, *, open_approval: bool = False) -> ReportRun:
    """Write the scripted run into `run_dir`; with `open_approval` one more approval stays unanswered at the end."""
    clock = ScriptedClock()
    writer = JournalWriter(run_dir, store, clock, ids)  # type: ignore[arg-type]  # B-185: str stands for Timestamp

    def at(seconds: float, type_: EventType, payload: dict[str, Any], path: str | None = None) -> None:
        clock.ms = START_MS + int(seconds * 1000)
        writer.append(type_, payload, path=path, attempt=1 if path else None)

    def done(ms: int) -> dict[str, Any]:
        return {"result": {"ref": REF, "summary": {}, "warnings": [], "complete": True}, "duration_ms": ms}

    kinds = EventType
    at(0, kinds.RUN_STARTED, HEADER)
    at(1, kinds.STEP_STARTED, STARTED, "0")
    at(3, kinds.STEP_COMPLETED, done(2_000), "0")
    at(3, kinds.APPROVAL_REQUESTED, APPROVAL)
    at(63, kinds.APPROVAL_RESOLVED, APPROVED)
    at(63, kinds.STEP_STARTED, STARTED, "1")
    at(68, kinds.STEP_COMPLETED, done(5_000), "1")
    at(68, kinds.INPUT_REQUESTED, INPUT)
    at(98, kinds.INPUT_PROVIDED, {"request_id": "in1", "answer_ref": REF, "by": "engineer:x"})
    at(100, kinds.RUN_RESUMED, {"resume_no": 1, "code_hash_changed": False, "servers": []})
    at(100, kinds.STEP_STARTED, STARTED, "2")
    failure = {"error": {"harness_code": "NEEDS_ENGINEER", "message": "m"}, "retryable": False, "duration_ms": 1_500}
    at(101.5, kinds.STEP_FAILED, failure, "2")
    at(102, kinds.INPUT_REQUESTED, DECISION_REQUEST)
    at(107, kinds.DECISION_MADE, DECISION)
    if open_approval:
        at(110, kinds.APPROVAL_REQUESTED, {**APPROVAL, "request_id": "ap2"})
    writer.close()
    return ReportRun(run_dir, WAIT_MS, MACHINE_MS, 1)
