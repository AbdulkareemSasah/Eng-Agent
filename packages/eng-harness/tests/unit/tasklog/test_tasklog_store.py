"""Chained appends under the lock, closed-task rules and the size cap (plan 0015 T3a; spec 0015 AC10-AC12)."""

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from eng_contract.canonical import canonical_json, loads
from pydantic import TypeAdapter

from eng_harness._runlock import RunLock, is_locked
from eng_harness.errors import HarnessCode, RunLocked
from eng_harness.tasklog._records import Narration, OwnerWords, TaskOpened, TaskRecord, TriageLine
from eng_harness.tasklog._store import ClosedTaskError, TasklogFullError, append_record, append_triage

_TASK_ID = "task_01KDVDNA00EEHMW00B9ZA4ZDSH"
_NEED_ID = "need_01KDVDNA00EEHMW00B9ZA4ZDSH_1"
_RUN_ID = "run_01KDVDNA01NEDC4EXH1ZACT2K2"
_OTHER_RUN_ID = "run_01KDVDNA02BX1SJVXRMXPXQSD9"
_AT = "2026-11-14T10:00:00Z"
_ZERO_SHA = "0" * 64
_BOGUS_SHA = "ab" * 32
_AGENT = "agent:test-tool"
_DEV = "dev-session:B-478"
_ARABIC = "من فضلك نفذ المطلوب"
_MAX_FILE_BYTES = 900_000  # spec 0015 §4.2: an append past this size is refused with TASKLOG_FULL.

_RECORDS = TypeAdapter(TaskRecord)
_TRIAGE = TypeAdapter(TriageLine)


def _sha(data: bytes) -> str:
    """The SHA-256 of `data` as lowercase hex (spec 0015 §4.3: the `*_sha256` fields)."""
    return hashlib.sha256(data).hexdigest()


def _payload(kind: str, by: str, seq: int, prev: str, **fields: Any) -> dict[str, Any]:
    """One task-record payload: the common fields of spec 0015 §4.3 plus the kind's fields."""
    return {
        "schema": "harness.tasklog_record/1",
        "task_id": _TASK_ID,
        "seq": seq,
        "at": _AT,
        "kind": kind,
        "by": by,
        "policy": "full",
        "redactions": [],
        "prev_sha256": prev,
        **fields,
    }


def _task_opened(seq: int = 99, prev: str = _BOGUS_SHA) -> TaskRecord:
    """A `task_opened` record; the wrong seq/prev prove the store assigns both (AC10)."""
    return _RECORDS.validate_python(
        _payload(
            "task_opened",
            _AGENT,
            seq,
            prev,
            title_en="Build the model from the drawings.",
            agent={"tool": "test-tool"},
            session={"place": "local"},
            repo_commit=_sha(b"repo")[:40],
            integration_branch="build/v1",
            harness_version="0.1.0-test",
        )
    )


def _owner_words(
    role: str = "request", text: str = "Fixture owner words.", seq: int = 99, prev: str = _BOGUS_SHA
) -> TaskRecord:
    """An `owner_words` record whose hash is the SHA-256 of the input bytes (spec 0015 §4.3)."""
    return _RECORDS.validate_python(
        _payload(
            "owner_words", _AGENT, seq, prev, role=role, lang="ar", text=text, text_sha256=_sha(text.encode("utf-8"))
        )
    )


def _narration(text: str, seq: int = 99, prev: str = _BOGUS_SHA) -> TaskRecord:
    """A `narration` record carrying `text_en` (spec 0015 §4.3)."""
    return _RECORDS.validate_python(_payload("narration", _AGENT, seq, prev, text_en=text))


def _not_found(need_en: str, seq: int = 99, prev: str = _BOGUS_SHA) -> TaskRecord:
    """A `not_found` record of category `no_workflow` (spec 0015 §4.3)."""
    return _RECORDS.validate_python(
        _payload(
            "not_found",
            _AGENT,
            seq,
            prev,
            need_id=_NEED_ID,
            category="no_workflow",
            need_en=need_en,
            target="model_from_drawings",
            evidence=["#1"],
            blocking=False,
        )
    )


def _run_attached(
    run_id: str, status: str = "PAUSED", event_count: int = 9, last_seq: int = 9, seq: int = 99, prev: str = _BOGUS_SHA
) -> TaskRecord:
    """A harness `run_attached` record for `run_id` (spec 0015 §4.3)."""
    return _RECORDS.validate_python(
        _payload(
            "run_attached",
            "harness",
            seq,
            prev,
            run_id=run_id,
            workflow="model_edit_cycle",
            status=status,
            exit_code=10,
            event_count=event_count,
            last_seq=last_seq,
            chain_sha256=_sha(b"chain"),
            report=f"runs/{run_id}/report/report.html",
            unreleased_tools={},
            timings={"machine_ms": 12, "waiting_ms": 34, "resumes": 1},
            model_files=["m1.EDB"],
        )
    )


def _run_fact(run_id: str, by: str = "harness", seq: int = 99, prev: str = _BOGUS_SHA) -> TaskRecord:
    """A `run_fact` record for `run_id`, harness-written unless `by` says otherwise (spec 0015 §4.3)."""
    return _RECORDS.validate_python(
        _payload("run_fact", by, seq, prev, run_id=run_id, journal_seq=9, event="run_completed", summary_en="Done.")
    )


def _task_closed(status: str = "BLOCKED", seq: int = 99, prev: str = _BOGUS_SHA) -> TaskRecord:
    """A `task_closed` record with the open need (spec 0015 §4.3)."""
    return _RECORDS.validate_python(
        _payload("task_closed", _AGENT, seq, prev, status=status, summary_en="Blocked.", open_needs=[_NEED_ID])
    )


def _withheld_after(seq: int = 99, prev: str = _BOGUS_SHA) -> TaskRecord:
    """A harness `withheld_after` record naming a withheld span (spec 0015 §4.3, §4.4)."""
    return _RECORDS.validate_python(
        _payload(
            "withheld_after",
            "harness",
            seq,
            prev,
            target_seq=2,
            field="text",
            rule="personal-path",
            span_sha256=_sha(b"span"),
            line_sha256_before=_sha(b"line"),
            reason_en="Withheld after the push.",
        )
    )


def _run_refused(seq: int = 99, prev: str = _BOGUS_SHA) -> TaskRecord:
    """A harness `run_refused` record: the wrong kind after the close, whatever its by-line (AC11)."""
    return _RECORDS.validate_python(
        _payload(
            "run_refused",
            "harness",
            seq,
            prev,
            workflow="model_edit_cycle",
            exit_code=2,
            code="NOT_FOUND",
            missing=["models/m1.EDB"],
            message_en="No workflow in this build.",
        )
    )


def _triage_payload(kind: str, by: str, seq: int, prev: str, **fields: Any) -> dict[str, Any]:
    """One triage-line payload: the common fields of spec 0015 §4.3.1 plus the kind's fields."""
    return {
        "schema": "harness.tasklog_triage/1",
        "need_id": _NEED_ID,
        "seq": seq,
        "at": _AT,
        "kind": kind,
        "by": by,
        "redactions": [],
        "prev_sha256": prev,
        **fields,
    }


def _triaged(public_en: str, seq: int = 99, prev: str = _BOGUS_SHA) -> TriageLine:
    """A `triaged` line with outcome `new_spec` (spec 0015 §4.3.1)."""
    return _TRIAGE.validate_python(
        _triage_payload(
            "triaged",
            _DEV,
            seq,
            prev,
            outcome="new_spec",
            public_en=public_en,
            public_en_sha256=_sha(public_en.encode("utf-8")),
        )
    )


def _public_released(seq: int = 99, prev: str = _BOGUS_SHA) -> TriageLine:
    """A `public_released` line for the released text (spec 0015 §4.3.1)."""
    return _TRIAGE.validate_python(
        _triage_payload(
            "public_released",
            _DEV,
            seq,
            prev,
            public_en_sha256=_sha(b"released public text"),
            public_en_released="owner",
            released_on="2026-11-14",
            reply_sha256=_sha(b"owner reply"),
        )
    )


def _answered(seq: int = 99, prev: str = _BOGUS_SHA) -> TriageLine:
    """An `answered` line naming the release and commit (spec 0015 §4.3.1)."""
    return _TRIAGE.validate_python(
        _triage_payload("answered", _DEV, seq, prev, release="eng-harness==0.2.0", commit=_sha(b"commit")[:40])
    )


def _raw_lines(path: Path) -> list[bytes]:
    """The file's lines without terminators; the file is LF-only and newline-terminated (spec 0015 §4.2)."""
    data = path.read_bytes()
    assert b"\r" not in data
    assert data.endswith(b"\n")
    return data.split(b"\n")[:-1]


def _assert_chain(pairs: list[tuple[int, str]], raws: list[bytes]) -> None:
    """Seq runs 1..n; each prev is the SHA-256 of the previous line as written, LF included (spec 0015 §4.3)."""
    assert [seq for seq, _ in pairs] == list(range(1, len(pairs) + 1))
    assert pairs[0][1] == _ZERO_SHA
    for index in range(1, len(pairs)):
        assert pairs[index][1] == hashlib.sha256(raws[index - 1] + b"\n").hexdigest()


def _count_syncs(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count `os.fsync` calls from here on, still syncing (spec 0015 §4.2: appends are fsynced)."""
    synced: list[int] = []
    real_fsync = os.fsync

    def _record(fd: int) -> None:
        synced.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", _record)
    return synced


def test_concurrent_append_never_interleaves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC10: appends chain under the task lock with fsync; a concurrent append is refused, writing nothing (§4.2)."""
    records = tmp_path / "tasklog" / "tasks" / "2026" / "11" / _TASK_ID / "records.jsonl"
    locks = tmp_path / ".eng" / "tasklog" / "locks"
    synced = _count_syncs(monkeypatch)
    first = append_record(records, locks, _task_opened())
    assert (first.seq, first.prev_sha256) == (1, _ZERO_SHA)
    assert isinstance(first, TaskOpened)
    assert first.title_en == "Build the model from the drawings."
    synced.clear()
    second = append_record(records, locks, _owner_words(text=_ARABIC))
    assert second.seq == 2
    assert isinstance(second, OwnerWords)
    assert second.text == _ARABIC
    assert _ARABIC.encode("utf-8") in records.read_bytes()  # byte-exact UTF-8 in the file (§4.2, AC2)
    assert len(synced) >= 1  # the append fsynced (§4.2)
    assert (locks / _TASK_ID / "run.lock").is_file()  # the task's lock (§4.2)
    assert not is_locked(locks / _TASK_ID)  # released when the append returned
    before = records.read_bytes()
    (locks / _TASK_ID).mkdir(parents=True, exist_ok=True)
    holder = RunLock(locks / _TASK_ID)
    holder.acquire()
    try:
        with pytest.raises(RunLocked) as refused:
            append_record(records, locks, _narration("blocked while the lock is held"))
        assert refused.value.code is HarnessCode.RUN_LOCKED  # §6: the CLI maps this to exit 4
        assert _TASK_ID in str(refused.value)  # §6 names the task id
        assert records.read_bytes() == before  # the refused append wrote nothing
    finally:
        holder.release()
    held = threading.Event()
    release = threading.Event()

    def _hold() -> None:
        keeper = RunLock(locks / _TASK_ID)
        keeper.acquire()
        held.set()
        assert release.wait(timeout=5)
        keeper.release()

    worker = threading.Thread(target=_hold, daemon=True)
    worker.start()
    assert held.wait(timeout=5)
    try:
        with pytest.raises(RunLocked):
            append_record(records, locks, _narration("blocked by the other thread"))
        assert records.read_bytes() == before
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    barrier = threading.Barrier(2)
    outcomes: dict[str, TaskRecord | RunLocked] = {}

    def _attempt(name: str, record: TaskRecord) -> None:
        barrier.wait(timeout=5)
        try:
            outcomes[name] = append_record(records, locks, record)
        except RunLocked as busy:
            outcomes[name] = busy

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [
            pool.submit(_attempt, "ann", _narration("ann was here")),
            pool.submit(_attempt, "bob", _narration("bob was here")),
        ]
        for future in pending:
            future.result(timeout=10)
    refused_names = [name for name, outcome in outcomes.items() if isinstance(outcome, RunLocked)]
    stored = [outcome for outcome in outcomes.values() if not isinstance(outcome, RunLocked)]
    assert len(refused_names) == 1  # one append won, the other was refused
    assert len(stored) == 1
    winner = stored[0]
    assert isinstance(winner, Narration)
    assert winner.seq == 3
    assert winner.text_en in ("ann was here", "bob was here")
    raws = _raw_lines(records)
    assert len(raws) == 3
    chained = [_RECORDS.validate_python(loads(raw)) for raw in raws]
    _assert_chain([(record.seq, record.prev_sha256) for record in chained], raws)
    assert winner.text_en.encode("utf-8") in b"\n".join(raws)
    loser = "bob was here" if winner.text_en == "ann was here" else "ann was here"
    assert loser.encode("utf-8") not in b"\n".join(raws)  # the refused append wrote nothing


def test_triage_append_chain_and_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC10: triage lines chain and seq like records, under the need's lock (§4.2, §4.3.1)."""
    triage = tmp_path / "tasklog" / "triage" / f"{_NEED_ID}.jsonl"
    locks = tmp_path / ".eng" / "tasklog" / "locks"
    synced = _count_syncs(monkeypatch)
    first = append_triage(triage, locks, _triaged("Public text for the digest."))
    assert (first.seq, first.prev_sha256) == (1, _ZERO_SHA)
    assert len(synced) >= 1  # the triage append fsynced (§4.2)
    assert append_triage(triage, locks, _public_released()).seq == 2
    assert append_triage(triage, locks, _answered()).seq == 3
    assert (locks / _NEED_ID / "run.lock").is_file()  # the need's lock (§4.2)
    assert not is_locked(locks / _NEED_ID)  # released when the append returned
    raws = _raw_lines(triage)
    lines = [_TRIAGE.validate_python(loads(raw)) for raw in raws]
    _assert_chain([(line.seq, line.prev_sha256) for line in lines], raws)
    assert [line.kind for line in lines] == ["triaged", "public_released", "answered"]
    before = triage.read_bytes()
    (locks / _NEED_ID).mkdir(parents=True, exist_ok=True)
    holder = RunLock(locks / _NEED_ID)
    holder.acquire()
    try:
        with pytest.raises(RunLocked):
            append_triage(triage, locks, _answered())
        assert triage.read_bytes() == before  # the refused append wrote nothing
    finally:
        holder.release()
    # The need's lock, not the task's: a held task lock does not block a triage append (§4.2).
    (locks / _TASK_ID).mkdir(parents=True, exist_ok=True)
    task_holder = RunLock(locks / _TASK_ID)
    task_holder.acquire()
    try:
        assert append_triage(triage, locks, _triaged("Replacement triage text.")).seq == 4
    finally:
        task_holder.release()


def test_closed_task_rules(tmp_path: Path) -> None:
    """AC11: after task_closed only harness run records of attached runs and withheld_after append (§4.3)."""
    records = tmp_path / "tasklog" / "tasks" / "2026" / "11" / _TASK_ID / "records.jsonl"
    locks = tmp_path / ".eng" / "tasklog" / "locks"
    append_record(records, locks, _task_opened())
    append_record(records, locks, _owner_words())
    append_record(records, locks, _run_attached(_RUN_ID))
    append_record(records, locks, _task_closed())
    updated = append_record(records, locks, _run_attached(_RUN_ID, status="COMPLETED", event_count=12, last_seq=12))
    assert updated.seq == 5  # a run that ends after the close still gets its final status (§4.3)
    assert append_record(records, locks, _run_fact(_RUN_ID)).seq == 6
    before = records.read_bytes()
    refused_cases = [
        _run_attached(_OTHER_RUN_ID),  # harness, but the run was never attached
        _run_fact(_OTHER_RUN_ID),  # its facts are refused too
        _run_fact(_RUN_ID, by=_AGENT),  # the run is attached, but the by-line is not harness
        _narration("a late narration"),
        _owner_words(role="correction", text="a late correction"),
        _task_closed(status="DONE"),  # a second close
        _run_refused(),  # harness by-line but the wrong kind
    ]
    for record in refused_cases:
        with pytest.raises(ClosedTaskError):
            append_record(records, locks, record)
        assert records.read_bytes() == before  # every refusal wrote nothing
    with pytest.raises(ClosedTaskError) as correction:
        append_record(records, locks, _owner_words(role="correction", text="zz-closed-text-probe"))
    assert "zz-closed-text-probe" not in str(correction.value)  # §6: never the refused text
    assert records.read_bytes() == before
    assert append_record(records, locks, _withheld_after()).seq == 7
    closed_full = records.read_bytes()
    # The lock is taken before the closed check: a held lock refuses with RunLocked, not ClosedTaskError.
    (locks / _TASK_ID).mkdir(parents=True, exist_ok=True)
    holder = RunLock(locks / _TASK_ID)
    holder.acquire()
    try:
        with pytest.raises(RunLocked):
            append_record(records, locks, _narration("blocked on a closed task"))
        assert records.read_bytes() == closed_full
    finally:
        holder.release()
    raws = _raw_lines(records)
    chained = [_RECORDS.validate_python(loads(raw)) for raw in raws]
    _assert_chain([(record.seq, record.prev_sha256) for record in chained], raws)
    assert [record.kind for record in chained] == [
        "task_opened",
        "owner_words",
        "run_attached",
        "task_closed",
        "run_attached",
        "run_fact",
        "withheld_after",
    ]


def test_size_cap(tmp_path: Path) -> None:
    """AC12: an append past 900 000 bytes is refused and nothing is written (§4.2, §5)."""
    records = tmp_path / "tasklog" / "tasks" / "2026" / "11" / _TASK_ID / "records.jsonl"
    locks = tmp_path / ".eng" / "tasklog" / "locks"
    append_record(records, locks, _not_found("y" * 50))
    first_size = records.stat().st_size
    head = _sha(_raw_lines(records)[0] + b"\n")
    fixed = len(canonical_json(_RECORDS.dump_python(_not_found("", seq=2, prev=head), mode="json"))) + 1
    fill = _MAX_FILE_BYTES - first_size - fixed
    assert fill > 1000
    append_record(records, locks, _not_found("x" * fill))
    assert records.stat().st_size == _MAX_FILE_BYTES  # exactly at the cap is allowed: only past it refuses
    assert len(_raw_lines(records)) == 2
    with pytest.raises(TasklogFullError) as full:
        append_record(records, locks, _not_found("zz-full-probe"))
    assert "zz-full-probe" not in str(full.value)  # §6: never the refused text
    assert records.stat().st_size == _MAX_FILE_BYTES
    assert len(_raw_lines(records)) == 2
    raws = _raw_lines(records)
    chained = [_RECORDS.validate_python(loads(raw)) for raw in raws]
    _assert_chain([(record.seq, record.prev_sha256) for record in chained], raws)
    # The cap covers triage files too (§5: "≤900 000 per file").
    triage = tmp_path / "tasklog" / "triage" / f"{_NEED_ID}.jsonl"
    append_triage(triage, locks, _triaged("seed text"))
    triage_first_size = triage.stat().st_size
    triage_head = _sha(_raw_lines(triage)[0] + b"\n")
    triage_fixed = len(canonical_json(_TRIAGE.dump_python(_triaged("", seq=2, prev=triage_head), mode="json"))) + 1
    triage_fill = _MAX_FILE_BYTES - triage_first_size - triage_fixed
    assert triage_fill > 1000
    append_triage(triage, locks, _triaged("x" * triage_fill))
    assert triage.stat().st_size == _MAX_FILE_BYTES
    with pytest.raises(TasklogFullError):
        append_triage(triage, locks, _answered())
    assert triage.stat().st_size == _MAX_FILE_BYTES
    assert len(_raw_lines(triage)) == 2
