"""The task-log store: chained appends under the task or need lock (spec 0015 sections 4.2, 4.3, 4.3.1).

Purpose: `append_record` and `append_triage` assign `seq` and `prev_sha256` under the `RunLock` kept in
`.eng/tasklog/locks/`, refuse appends to a closed task and appends past the 900 000-byte cap, and fsync every
line, which is one canonical JSON object with LF.
Units: `seq` starts at 1; sizes are bytes; `*_sha256` are lowercase hex.
Errors: `ClosedTaskError` after `task_closed` (only harness run records of attached runs and `withheld_after`
are accepted); `TasklogFullError` past the cap; `RunLocked` from the existing lock helper propagates.
"""

import contextlib
import hashlib
import os
from collections.abc import Iterator
from pathlib import Path

from eng_contract.canonical import canonical_json
from pydantic import BaseModel, TypeAdapter

from eng_harness._runlock import RunLock
from eng_harness.tasklog._records import (
    SEQ_MIN,
    RunAttached,
    RunFact,
    TaskClosed,
    TaskRecord,
    TriageLine,
    WithheldAfter,
)

__all__ = ["MAX_FILE_BYTES", "ClosedTaskError", "TasklogFullError", "append_record", "append_triage"]

MAX_FILE_BYTES = 900_000
"""Largest size of `records.jsonl` or a triage file; an append past it is refused (spec 0015 §4.2, §5)."""

_SHA_HEX_DIGITS = 64
"""Hex digits of a SHA-256 (spec 0015 §4.3: the `*_sha256` fields)."""

_ZERO_SHA256 = "0" * _SHA_HEX_DIGITS
"""`prev_sha256` of the first line of a file (spec 0015 §4.3: 64 zeros for seq 1)."""

_SEQ_STEP = 1
"""Seq numbering is consecutive: each line follows the last by one (spec 0015 §4.3, §4.3.1)."""

_LF = b"\n"
"""Line terminator of the log files: LF only (spec 0015 §4.2)."""

_HARNESS_BY = "harness"
"""The `by` value of harness-written run records (spec 0015 §4.3)."""

_RECORDS = TypeAdapter(TaskRecord)
"""Validates and dumps task records (spec 0015 §4.3)."""

_TRIAGE = TypeAdapter(TriageLine)
"""Validates and dumps triage lines (spec 0015 §4.3.1)."""


class ClosedTaskError(Exception):
    """An append refused because the task is closed; names the task and kind, never the text (spec 0015 §6)."""

    def __init__(self, task_id: str, kind: str) -> None:
        """Build the refusal naming `task_id` and `kind`."""
        super().__init__(f"task {task_id} is closed: {kind} refused")
        self.task_id = task_id
        self.kind = kind


class TasklogFullError(Exception):
    """An append refused past the file cap; names the file, never the text (spec 0015 §4.2, §5, §6)."""

    def __init__(self, path: Path) -> None:
        """Build the refusal naming `path`."""
        super().__init__(f"task log file is full: {path}")
        self.path = path


@contextlib.contextmanager
def _locked(locks: Path, lock_id: str) -> Iterator[None]:
    """Hold the `RunLock` of `locks/lock_id`; `RunLocked` propagates (spec 0015 §4.2, §6)."""
    lock_dir = locks / lock_id
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = RunLock(lock_dir)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def _read_lines(path: Path) -> tuple[bytes, list[bytes]]:
    """The current bytes and non-empty lines of `path` (a missing file reads as empty)."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raw = b""
    return raw, [line for line in raw.split(_LF) if line]


def _sha(data: bytes) -> str:
    """The SHA-256 of `data` as lowercase hex (spec 0015 §4.3: the `*_sha256` fields)."""
    return hashlib.sha256(data).hexdigest()


def _seal[ModelT: BaseModel](model: ModelT, adapter: TypeAdapter[ModelT], seq: int, prev: str) -> tuple[ModelT, bytes]:
    """`model` with `seq` and `prev_sha256` assigned, plus its canonical line bytes with LF (spec 0015 §4.2)."""
    stored = model.model_copy(update={"seq": seq, "prev_sha256": prev})
    return stored, canonical_json(adapter.dump_python(stored, mode="json")) + _LF


def _check_cap(path: Path, current_size: int, line: bytes) -> None:
    """Raise `TasklogFullError` when appending `line` would take the file past the cap (spec 0015 §4.2, §5)."""
    if current_size + len(line) > MAX_FILE_BYTES:
        raise TasklogFullError(path)


def _write_line(path: Path, line: bytes) -> None:
    """Append `line` to `path` with fsync (spec 0015 §4.2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _require_open(record: TaskRecord, parsed: list[TaskRecord]) -> None:
    """Raise `ClosedTaskError` unless `record` may append to a closed task (spec 0015 §4.3, AC11).

    After `task_closed` only harness `run_attached` and `run_fact` records of runs already attached, and
    `withheld_after`, are accepted.
    """
    if not any(isinstance(past, TaskClosed) for past in parsed):
        return
    if isinstance(record, WithheldAfter):
        return
    attached = {past.run_id for past in parsed if isinstance(past, RunAttached)}
    if isinstance(record, RunAttached | RunFact) and record.by == _HARNESS_BY and record.run_id in attached:
        return
    raise ClosedTaskError(record.task_id, record.kind)


def append_record(records: Path, locks: Path, record: TaskRecord) -> TaskRecord:
    """Append `record` to `records`, assigning `seq` and `prev_sha256` under the task lock (spec 0015 §4.2).

    The stored copy is returned. The lock is taken before the closed and cap checks, so a held lock refuses
    with `RunLocked` having written nothing.

    Raises:
        RunLocked: another writer holds the task's lock.
        ClosedTaskError: the task is closed and `record` is not an allowed post-close record.
        TasklogFullError: the append would take the file past the cap.
    """
    with _locked(locks, record.task_id):
        raw, blobs = _read_lines(records)
        parsed = [_RECORDS.validate_json(blob) for blob in blobs]
        _require_open(record, parsed)
        if parsed:
            seq = parsed.pop().seq + _SEQ_STEP
            prev = _sha(blobs.pop() + _LF)
        else:
            seq, prev = SEQ_MIN, _ZERO_SHA256
        stored, line = _seal(record, _RECORDS, seq, prev)
        _check_cap(records, len(raw), line)
        _write_line(records, line)
        return stored


def append_triage(triage: Path, locks: Path, line_model: TriageLine) -> TriageLine:
    """Append `line_model` to the triage file, chained like a record under the need's lock (§4.2, §4.3.1).

    The stored copy is returned. A held need lock refuses with `RunLocked` having written nothing.

    Raises:
        RunLocked: another writer holds the need's lock.
        TasklogFullError: the append would take the file past the cap.
    """
    with _locked(locks, line_model.need_id):
        raw, blobs = _read_lines(triage)
        parsed = [_TRIAGE.validate_json(blob) for blob in blobs]
        if parsed:
            seq = parsed.pop().seq + _SEQ_STEP
            prev = _sha(blobs.pop() + _LF)
        else:
            seq, prev = SEQ_MIN, _ZERO_SHA256
        stored, line = _seal(line_model, _TRIAGE, seq, prev)
        _check_cap(triage, len(raw), line)
        _write_line(triage, line)
        return stored
