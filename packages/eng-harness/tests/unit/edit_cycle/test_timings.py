"""Edit-cycle timings over a scripted journal (plan 0007 T10b; spec 0007 section 4.9, AC29).

`write_cycles` is the scripted run the prompt tests share. Times are seconds after the run start; every
expected number below is the sum of the scripted times it names.
"""

import json
from pathlib import Path

import pytest
from eng_contract.ids import FixedClock, IdSource
from eng_contract.store import ResultStore
from fixtures.report_run import HEADER, SHA, build_report_run

from eng_harness import __version__
from eng_harness._text import format_duration_ms
from eng_harness.journal import EventType, JournalReader
from eng_harness.report import ReleaseMarks, build_report

from .journal_script import PRODUCER, Script

TURN = "edit_cycle_engineer_turn"
_KINDS = EventType


def fail(s: Script, path: str, kind: str, name: str, start: float, ms: int) -> None:
    """A step started at `start` that failed `ms` later."""
    body = {"kind": kind, "name": name, "args": {}, "args_sha256": SHA, "effect": "read"}
    error = {"harness_code": "NEEDS_ENGINEER", "message": "m"}
    s.at(start, _KINDS.STEP_STARTED, body, path)
    s.at(start + ms / 1000, _KINDS.STEP_FAILED, {"error": error, "retryable": False, "duration_ms": ms}, path)


def started(s: Script, path: str, kind: str, name: str, start: float) -> None:
    """A step that started and has not ended."""
    body = {"kind": kind, "name": name, "args": {}, "args_sha256": SHA, "effect": "read"}
    s.at(start, _KINDS.STEP_STARTED, body, path)


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


def test_benchmark_skips_a_missing_answer(run_dir: Path, store: ResultStore, ids: IdSource) -> None:
    """A stored answer that cannot be read is skipped like a request without a label, not raised."""
    from eng_harness.report._edit_cycle import edit_cycle_timings

    s = _script(run_dir, store, ids)
    s.begin("1/0/0", 10)
    s.at(13, _KINDS.INPUT_REQUESTED, {"request_id": "bad", "kind": "block", "title": "t", "fields_schema_sha256": SHA})
    s.at(14, _KINDS.INPUT_PROVIDED, {"request_id": "bad", "answer_ref": "res_" + "0" * 26, "by": "engineer:x"})
    s.asked("good", "block", "Change set", 15, 5, "R1")
    s.end("1/0/0", 10, 30)
    s.writer.close()
    found = edit_cycle_timings(JournalReader(run_dir), store).benchmarks
    assert [b.label for b in found] == ["R1"]


def test_benchmark_label_in_the_change_set_answer(run_dir: Path, store: ResultStore, ids: IdSource) -> None:
    """AC29: the label is read where the engine stores the answer (field `change_set`, member `benchmark_request`)."""
    from eng_harness.report._edit_cycle import edit_cycle_timings

    s = _script(run_dir, store, ids)
    s.begin("1/0/0", 10)
    s.at(13, _KINDS.INPUT_REQUESTED, {"request_id": "cs1", "kind": "block", "title": "t", "fields_schema_sha256": SHA})
    who = {"unit": None, "entered_by": "x", "entered_at": "2026-01-01T00:00:00.000Z"}
    held = {"change_set": {"value": {"items": [], "benchmark_request": "R7"}, **who}}
    answer = store.put("basis.engineer_input/1", {"step": "1/0/0/1", "fields": held}, PRODUCER).result_id
    s.at(14, _KINDS.INPUT_PROVIDED, {"request_id": "cs1", "answer_ref": answer, "by": "engineer:x"})
    s.decision("dec1", TURN, "accept", 20, 10)
    s.end("1/0/0", 10, 40)
    s.writer.close()
    found = edit_cycle_timings(JournalReader(run_dir), store).benchmarks
    assert [(b.label, b.elapsed_ms, b.cycles) for b in found] == [("R7", 17_000, 1)]


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


def _script(run_dir: Path, store: ResultStore, ids: IdSource) -> Script:
    s = Script(run_dir, store, ids)
    s.at(0, _KINDS.RUN_STARTED, {**HEADER, "input_ref": s.base, "basis_ref": s.base})
    return s


def test_an_answer_before_its_request_is_an_error(run_dir: Path, store: ResultStore, ids: IdSource) -> None:
    """An answer dated before its request is a `ReportError`, not a negative wait."""
    from eng_harness.report._edit_cycle import edit_cycle_timings
    from eng_harness.report._lineage import ReportError

    s = _script(run_dir, store, ids)
    s.begin("1/0/0", 10)
    s.asked("early", "block", "Change set", 20, -5)
    s.end("1/0/0", 10, 30)
    s.writer.close()
    with pytest.raises(ReportError):
        edit_cycle_timings(JournalReader(run_dir))


def test_a_cycle_ending_before_it_starts_is_an_error(run_dir: Path, store: ResultStore, ids: IdSource) -> None:
    """A cycle whose end is dated before its start is a `ReportError`."""
    from eng_harness.report._edit_cycle import edit_cycle_timings
    from eng_harness.report._lineage import ReportError

    s = _script(run_dir, store, ids)
    s.begin("1/0/0", 10)
    s.at(5, _KINDS.STEP_COMPLETED, {"output_ref": s.base, "duration_ms": 0}, "1/0/0")
    s.writer.close()
    with pytest.raises(ReportError):
        edit_cycle_timings(JournalReader(run_dir))


def test_a_step_belongs_to_a_cycle_by_whole_path_segments(run_dir: Path, store: ResultStore, ids: IdSource) -> None:
    """`1/0/01/0` is not inside `1/0/0`: its time is in no cycle and it is not listed."""
    from eng_harness.report._edit_cycle import edit_cycle_timings

    s = _script(run_dir, store, ids)
    s.begin("1/0/0", 10)
    s.step("1/0/0/0", "tool", "csi_read_model_state", 10, 1_000)
    s.step("1/0/01/0", "tool", "csi_open_model", 12, 4_000)
    s.end("1/0/0", 10, 20)
    s.writer.close()
    timings = edit_cycle_timings(JournalReader(run_dir))
    assert [(c.machine_ms, c.host_ms) for c in timings.cycles] == [(1_000, 1_000)]
    assert [s.path for s in timings.steps] == ["1/0/0", "1/0/0/0"]


def test_machine_time_counts_only_completed_work_steps(run_dir: Path, store: ResultStore, ids: IdSource) -> None:
    """Scopes, engineer steps, failed and unfinished steps are not machine time; a failure ends the cycle."""
    from eng_harness.report._edit_cycle import edit_cycle_timings

    s = _script(run_dir, store, ids)
    s.begin("1/0/0", 10)
    s.step("1/0/0/0", "tool", "csi_read_model_state", 10, 1_000)
    s.step("1/0/0/1", "calc", "harness.model_diff", 11, 2_000)
    s.step("1/0/0/2", "parallel", "p", 13, 5_000)
    s.step("1/0/0/3", "attempts", "a", 18, 7_000)
    s.step("1/0/0/4", "decide_many", "d", 25, 11_000)
    fail(s, "1/0/0/5", "tool", "csi_save_model", 36, 13_000)
    started(s, "1/0/0/6", "tool", "csi_frame_section", 49)
    s.at(60, _KINDS.STEP_FAILED, {
        "error": {"harness_code": "NEEDS_ENGINEER", "message": "m"}, "retryable": False, "duration_ms": 50_000,
    }, "1/0/0")  # fmt: skip
    s.writer.close()
    (cycle,) = edit_cycle_timings(JournalReader(run_dir)).cycles
    assert (cycle.wall_ms, cycle.machine_ms, cycle.host_ms) == (50_000, 3_000, 1_000)
