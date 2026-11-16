"""Edit-cycle timings over a scripted journal (plan 0007 T10; spec 0007 section 4.9, AC29).

`write_cycles` is the scripted run the prompt and audit tests share. Times are seconds after the run start; every
expected number below is the sum of the scripted times it names.
"""

import json
from pathlib import Path
from typing import Any

from eng_contract.envelope import Provenance
from eng_contract.ids import FixedClock, IdSource
from eng_contract.store import ResultStore
from fixtures.report_run import HEADER, SHA, START_MS, ScriptedClock, build_report_run

from eng_harness import __version__
from eng_harness._text import format_duration_ms
from eng_harness.journal import EventType, JournalReader, JournalWriter
from eng_harness.report import ReleaseMarks, build_report

TURN = "edit_cycle_engineer_turn"
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


def write_cycles(
    run_dir: Path, store: ResultStore, ids: IdSource, *, open_tail: bool = False, accept: bool = True
) -> JournalReader:
    """Two cycles and the run-level steps; `open_tail` adds a third cycle still running with two open requests."""
    s = Script(run_dir, store, ids)
    s.at(0, _KINDS.RUN_STARTED, {**HEADER, "input_ref": s.base, "basis_ref": s.base})
    s.step("0", "tool", "csi_open_model", 1, 2_000)
    s.begin("1/0/0", 10)
    s.step("1/0/0/0", "tool", "csi_read_model_state", 10, 2_000)
    s.step("1/0/0/1", "calc", "harness.model_diff", 12, 1_000)
    s.asked("ask_a1", "block", "Change set", 13, 30, "R1")
    s.step("1/0/0/2", "ask", "ChangeSetRequest", 43, 0)
    s.step("1/0/0/3", "calc", "harness.change_set_check", 43, 1_000)
    s.asked("ask_a2", "block", "Change set again", 44, 5)
    s.step("1/0/0/4", "ask", "ChangeSetRequest", 49, 0)
    s.step("1/0/0/5", "calc", "harness.change_set_check", 49, 1_000)
    s.approval("ap1", "CHANGE_SET", 50, 30)
    s.step("1/0/0/6", "approve", "CHANGE_SET", 80, 0)
    s.step("1/0/0/7", "tool", "csi_save_model", 80, 3_000, effect="write")
    s.step("1/0/0/8", "tool", "csi_frame_section", 83, 2_000, effect="write")
    s.decision("dec1", TURN, "more_edits", 100, 30)
    s.step("1/0/0/9", "decide", TURN, 130, 30_000, 0)
    s.end("1/0/0", 10, 130)
    s.begin("1/1/0", 131)
    s.step("1/1/0/0", "tool", "csi_read_model_state", 131, 2_000)
    s.asked("ask_b1", "block", "Change set", 133, 1, "R1")
    s.step("1/1/0/1", "ask", "ChangeSetRequest", 134, 0)
    s.approval("ap4", "INFO", 135, 0, by="mode:work_on_copy")
    s.approval("ap2", "CHANGE_SET", 140, 10)
    s.approval("ap3", "CHANGE_SET", 152, 8)
    s.asked("fl1", "engine.in_flight", "In flight", 161, 1)
    s.decision("dec2", "edit_cycle_analysis_messages", "proceed", 170, 5)
    s.step("1/1/0/2", "decide", "edit_cycle_analysis_messages", 175, 5_000, 0)
    s.decision("dec3", TURN, "accept" if accept else "more_edits", 180, 10)
    s.step("1/1/0/3", "decide", TURN, 190, 10_000, 0)
    s.end("1/1/0", 131, 200)
    s.approval("pr1", "PROMOTION", 201, 9)
    if open_tail:
        s.begin("1/2/0", 220)
        s.approval("open1", "INFO", 221, None)
        s.at(
            222,
            _KINDS.INPUT_REQUESTED,
            {"request_id": "dec9", "kind": "engine.decision", "title": "d", "fields_schema_sha256": SHA},
        )
    s.writer.close()
    return JournalReader(run_dir)


def test_cycle_and_turn_timings(run_dir: Path, store: ResultStore, ids: IdSource) -> None:
    """AC29: per-cycle measures, engineer-turn waits and the benchmark request equal the scripted sums."""
    from eng_harness.report._edit_cycle import edit_cycle_timings

    timings = edit_cycle_timings(write_cycles(run_dir, store, ids, open_tail=True), store)
    first, second, third = timings.cycles
    assert (first.path, first.wall_ms, first.machine_ms, first.host_ms, first.wait_ms, first.prompts) == (
        "1/0/0", 120_000, 10_000, 7_000, 95_000, 1,
    )  # fmt: skip
    assert (second.path, second.wall_ms, second.machine_ms, second.host_ms, second.wait_ms, second.prompts) == (
        "1/1/0", 69_000, 2_000, 2_000, 35_000, 3,
    )  # fmt: skip
    assert (third.cycle, third.wall_ms, third.machine_ms, third.wait_ms, third.prompts) == (3, None, 0, 0, 1)
    assert [(t.cycle, t.wait_ms) for t in timings.turns] == [(1, 30_000), (2, 10_000)]
    assert [(b.label, b.elapsed_ms, b.cycles) for b in timings.benchmarks] == [("R1", 177_000, 2)]
    machine = [s.duration_ms or 0 for s in timings.steps if s.kind not in {"block", "ask", "approve", "decide"}]
    assert sum(machine) == first.machine_ms + second.machine_ms == 12_000
    steps = [(s.path, s.kind, s.name, s.duration_ms) for s in timings.steps]
    assert steps[0] == ("1/0/0", "block", "edit_cycle_once", 120_000)
    assert ("1/0/0/9", "decide", TURN, 30_000) in steps
    assert not any(path == "0" for path, *_ in steps)
    assert len(steps) == 1 + 10 + 1 + 4 + 1


def test_benchmark_without_accept_or_label(run_dir: Path, store: ResultStore, ids: IdSource) -> None:
    """Without the store no label is known; a label with no accept has no elapsed time and runs to the last cycle."""
    from eng_harness.report._edit_cycle import edit_cycle_timings

    reader = write_cycles(run_dir, store, ids, accept=False)
    assert edit_cycle_timings(reader).benchmarks == ()
    assert [(b.label, b.elapsed_ms, b.cycles) for b in edit_cycle_timings(reader, store).benchmarks] == [
        ("R1", None, 2)
    ]


def test_report_adds_the_cycle_timings(run_dir: Path, store: ResultStore, ids: IdSource, clock: FixedClock) -> None:
    """The timings section gains the cycle tables only when the journal holds edit-cycle steps (spec 0007 4.9)."""
    reader = write_cycles(run_dir, store, ids)
    html = build_report(reader, store, ReleaseMarks(records={}), clock, __version__)
    assert "Edit cycles" in html
    assert format_duration_ms(120_000) in html
    assert "R1" in html
    plain = tmp_run = run_dir.parent / "plain"
    plain.mkdir()
    build_report_run(plain, store, ids)
    assert "Edit cycles" not in build_report(
        JournalReader(tmp_run), store, ReleaseMarks(records={}), clock, __version__
    )


def test_cycle_timings_file(run_dir: Path, store: ResultStore, ids: IdSource, tmp_path: Path) -> None:
    """`report/cycle-timings.json` holds the measures for the B-1 sheet and no file path."""
    from eng_harness.report._edit_cycle import edit_cycle_timings
    from eng_harness.report._write import write_cycle_timings

    timings = edit_cycle_timings(write_cycles(run_dir, store, ids), store)
    target = tmp_path / "report" / "cycle-timings.json"
    write_cycle_timings(timings, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert [c["wall_ms"] for c in data["cycles"]] == [120_000, 69_000]
    assert data["benchmarks"] == [{"label": "R1", "elapsed_ms": 177_000, "cycles": 2}]
    assert [t["wait_ms"] for t in data["turns"]] == [30_000, 10_000]
    assert data["cycles"][0]["prompts"] == 1
    assert str(tmp_path) not in target.read_text(encoding="utf-8")
