"""Journal reader API, views, follow and the run lock probe (plan 0001 T4; AC25, AC68)."""

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore

from eng_harness._runlock import RunLock
from eng_harness.errors import JournalIntegrityError, RunLocked
from eng_harness.journal import EventType, JournalReader, JournalWriter, is_locked

T = EventType
REF = "res_" + "0" * 26
SHA = "a" * 64
HEADER: dict[str, Any] = {
    "run_id": "run_x", "workflow": "w", "block": {"name": "b", "version": "1", "code_sha256": SHA},
    "input_ref": REF, "input_sha256": SHA, "basis_ref": REF, "mode": "work_on_copy", "run_class": "trial",
    "engine_version": "1", "contract_version": "eng-contract/1", "settings_sha256": SHA, "servers": [],
    "always_ask": [],
}  # fmt: skip
STARTED = {"kind": "tool", "name": "t", "args": {"a": 1}, "args_sha256": SHA, "effect": "read"}
COMPLETED = {"result": {"ref": REF, "summary": {}, "warnings": [], "complete": True}, "duration_ms": 3}
FAILED = {"error": {"harness_code": "NEEDS_ENGINEER", "message": "m"}, "retryable": False, "duration_ms": 1}
SAVED = {
    "model_key": "m", "model_id": "mdl_" + "0" * 26, "revision": 1, "fingerprint": "f", "file_sha256": SHA,
    "file_name": "a.edb", "role": "working_copy",
}  # fmt: skip
INPUT = {"request_id": "r", "kind": "block", "title": "t", "fields_schema_sha256": SHA}
APPROVAL = {
    "request_id": "r", "kind": "INFO", "title": "t", "preview_ref": REF, "shown_sha256": SHA, "binding": {},
    "items": [],
}  # fmt: skip
APPROVED = {"request_id": "r", "shown_sha256": SHA, "decision": "approve", "rejected_items": [], "by": "engineer:x"}
DECISION = {
    "point": "p", "options": ["a", "b"], "choice": "a", "decided_by": "rule", "confidence": None, "latency_ms": 0,
    "state_sha256": SHA, "suggestions": [],
}  # fmt: skip
RESUMED = {"resume_no": 1, "code_hash_changed": False, "servers": []}
ESCALATED = {"reason": "attempts_exhausted", "detail": "d", "evidence": []}
DONE = {"output_ref": REF, "output_sha256": SHA, "draft": True}


def _writer(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> JournalWriter:
    return JournalWriter(run_dir, store, FixedClock(1_767_225_600_000, 1), ids)


def _step(
    writer: JournalWriter, path: str, done: tuple[T, dict[str, Any]] | None = (T.STEP_COMPLETED, COMPLETED)
) -> None:
    writer.append(T.STEP_STARTED, STARTED, path=path, attempt=1)
    if done:
        writer.append(done[0], done[1], path=path, attempt=1)


def test_views_and_follow(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    writer = _writer(run_dir, store, ids)
    writer.append(T.RUN_STARTED, HEADER)
    reader = JournalReader(run_dir)
    assert reader.header().workflow == "w"
    assert reader.run().status == "INTERRUPTED"  # no engine holds the lock and the run is neither paused nor ended
    _step(writer, "0")
    _step(writer, "1", (T.STEP_FAILED, FAILED))
    _step(writer, "1~post.check.x", None)
    writer.append(T.MODEL_SAVED, SAVED, path="0")
    writer.append(T.MODEL_SAVED, {**SAVED, "revision": 2, "role": "revision"}, path="1")
    steps = reader.steps()  # the reader sees events appended after it opened
    assert [(s.path, s.attempt, s.status, s.inserted) for s in steps] == [
        ("0", 1, "completed", False), ("1", 1, "failed", False), ("1~post.check.x", 1, "running", True),
    ]  # fmt: skip
    assert steps[0].result_ref == REF
    assert steps[0].duration_ms == 3
    assert steps[1].error is not None
    assert [m.saved.revision for m in reader.models()] == [1, 2]
    assert [e.seq for e in reader.events()] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert [e.seq for e in reader.follow(5)] == [6, 7, 8]
    assert reader.follow(8) == []
    # requests: an approval, a block input, and an engine.decision input resolved by the first decision_made
    writer.append(T.APPROVAL_REQUESTED, {**APPROVAL, "request_id": "a1"})
    writer.append(T.INPUT_REQUESTED, {**INPUT, "request_id": "i1"})
    writer.append(T.INPUT_REQUESTED, {**INPUT, "request_id": "d1", "kind": "engine.decision"})
    writer.append(T.RUN_PAUSED, {"reason": "awaiting_approval", "request_ids": ["a1", "i1", "d1"]})
    run = reader.run()
    assert (run.status, run.pending) == ("PAUSED", ("a1", "i1", "d1"))
    assert [(r.request_id, r.kind, r.resolution) for r in reader.requests()] == [
        ("a1", "INFO", None), ("i1", "block", None), ("d1", "engine.decision", None),
    ]  # fmt: skip
    writer.append(T.DECISION_MADE, DECISION)  # request_id null: answers no request
    assert reader.requests()[2].resolution is None
    writer.append(T.DECISION_MADE, {**DECISION, "request_id": "d1", "choice": "first"})
    writer.append(T.DECISION_MADE, {**DECISION, "request_id": "d1", "choice": "second"})
    writer.append(T.APPROVAL_RESOLVED, {**APPROVED, "request_id": "a1"})
    writer.append(T.INPUT_PROVIDED, {"request_id": "i1", "answer_ref": REF, "by": "engineer:x"})
    by_id = {r.request_id: r for r in reader.requests()}
    assert getattr(by_id["d1"].resolution, "choice", None) == "first"
    assert all(r.resolution is not None for r in by_id.values())
    assert reader.run().pending == ()
    assert len(reader.decisions()) == 3
    writer.append(T.RUN_ESCALATED, ESCALATED)
    assert reader.run().status == "NEEDS_ENGINEER"
    assert reader.run().escalation is not None
    writer.append(T.RUN_RESUMED, RESUMED)
    assert reader.run().escalation is None
    writer.append(T.RUN_COMPLETED, DONE)
    signed = {"outputs": [REF], "approval_request_id": "a1", "by": "engineer:x"}
    writer.append(T.SIGNED_OFF, signed)  # accepted after a terminal event, which stays terminal
    done = reader.run()
    assert (done.status, done.draft, done.run_id, done.mode) == ("COMPLETED", True, "run_x", "work_on_copy")
    assert done.started_at == reader.events()[0].at
    assert done.ended_at == reader.events()[-2].at
    writer.close()
    reader.close()


def test_status_failed_and_running(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    writer = _writer(run_dir, store, ids)
    writer.append(T.RUN_STARTED, HEADER)
    lock = RunLock(run_dir)
    lock.acquire()
    reader = JournalReader(run_dir)
    assert reader.run().status == "RUNNING"  # a live engine holds the lock
    lock.release()
    writer.append(T.RUN_FAILED, {"reason": "abandoned", "by": "engineer:x"})
    assert reader.run().status == "FAILED"
    assert reader.run().ended_at is not None


def test_run_class_and_unreleased_tools(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    writer = _writer(run_dir, store, ids)
    rec_a, rec_b, runtime = {"since": "b-1"}, {"since": "b-2"}, {"providers": ["p"]}
    writer.append(T.RUN_STARTED, {**HEADER, "run_class": "production", "unreleased_tools": {"t_a": rec_a}})
    reader = JournalReader(run_dir)
    run = reader.run()
    assert run.run_class == "production"
    assert dict(run.unreleased_tools) == {"t_a": rec_a}
    assert dict(run.decision_runtime) == {}
    writer.append(T.RUN_RESUMED, {**RESUMED, "unreleased_tools": {"t_b": rec_b}})  # AC68: the union
    writer.append(T.RUN_RESUMED, {**RESUMED, "resume_no": 2})  # unchanged: not recorded
    writer.append(T.RUN_RESUMED, {**RESUMED, "resume_no": 3, "decision_runtime": runtime})
    run = reader.run()
    assert dict(run.unreleased_tools) == {"t_a": rec_a, "t_b": rec_b}
    assert dict(run.decision_runtime) == runtime  # AC69: the last recorded object


def test_reader_verifies(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    with pytest.raises(JournalIntegrityError):
        JournalReader(run_dir)  # no journal file
    assert not (run_dir / "journal.sqlite").exists()  # a failed open creates nothing
    writer = _writer(run_dir, store, ids)
    with pytest.raises(JournalIntegrityError, match="run_started"):
        JournalReader(run_dir).header()
    writer.append(T.RUN_STARTED, HEADER)
    writer.append(T.STEP_RERUN, {"reason": "read_in_flight"}, path="0", attempt=1)
    writer.close()
    reader = JournalReader(run_dir)
    with pytest.raises(JournalIntegrityError, match="step"):
        reader.steps()  # a step event with no step_started
    reader.close()
    conn = sqlite3.connect(run_dir / "journal.sqlite", isolation_level=None)
    conn.execute("DROP TRIGGER events_no_update")
    conn.execute("UPDATE events SET at = '2030-01-01T00:00:00.000Z' WHERE seq = 2")
    conn.close()
    with pytest.raises(JournalIntegrityError, match=r"seq 2\b"):
        JournalReader(run_dir)


def test_is_locked(run_dir: Path) -> None:
    assert not is_locked(run_dir)  # no lock file, and the probe creates none
    assert not (run_dir / "run.lock").exists()
    first, second = RunLock(run_dir), RunLock(run_dir)
    first.acquire()
    assert is_locked(run_dir)
    with pytest.raises(RunLocked):
        second.acquire()
    first.release()
    assert not is_locked(run_dir)
    second.acquire()  # the lock is free again after release
    second.release()
