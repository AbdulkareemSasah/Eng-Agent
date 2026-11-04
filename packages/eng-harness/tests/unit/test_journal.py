"""Journal schema, writer, hash chain, durability, payloads by reference (plan 0001 T3; AC20-22, AC24, AC26)."""

import sqlite3
from pathlib import Path
from typing import Any, ClassVar

import pytest
from eng_contract.canonical import canonical_json, payload_sha256
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore
from eng_harness.journal import INLINE_EVENT_BYTES, PAYLOAD_MODELS, EventType, JournalWriter
from eng_harness.journal._schema import chain_hash, iter_events

from eng_harness.errors import JournalIntegrityError

REF = "res_" + "0" * 26
SHA = "a" * 64
STAMP = "2026-01-01T00:00:00.000Z"
BLOCK = {"name": "b", "version": "1", "code_sha256": SHA}
SPEC_TYPES = [
    "run_started",
    "step_started",
    "step_completed",
    "step_failed",
    "step_reconciled",
    "step_rerun",
    "decision_made",
    "input_requested",
    "input_provided",
    "approval_requested",
    "approval_resolved",
    "host_started",
    "model_bound",
    "check_enforced",
    "model_saved",
    "run_paused",
    "run_resumed",
    "run_escalated",
    "run_completed",
    "run_failed",
    "signed_off",
]
STEP = {"kind": "tool", "name": "t", "args": {"a": 1}, "args_sha256": SHA, "effect": "read"}
SAMPLES: dict[str, dict[str, Any]] = {
    "run_started": {
        "run_id": "run_x",
        "workflow": "w",
        "block": BLOCK,
        "input_ref": REF,
        "input_sha256": SHA,
        "basis_ref": REF,
        "mode": "work_on_copy",
        "run_class": "trial",
        "engine_version": "1",
        "contract_version": "eng-contract/1",
        "settings_sha256": SHA,
        "servers": [],
        "always_ask": [],
    },
    "step_started": STEP,
    "step_completed": {"result": {"ref": REF, "summary": {}, "warnings": [], "complete": True}, "duration_ms": 3},
    "step_failed": {"error": {"harness_code": "NEEDS_ENGINEER", "message": "m"}, "retryable": False, "duration_ms": 1},
    "step_reconciled": {"op_id": "o", "outcome": "applied", "decided_by": "adapter", "evidence": [REF]},
    "step_rerun": {"reason": "read_in_flight"},
    "decision_made": {
        "point": "p",
        "options": ["a", "b"],
        "choice": "a",
        "decided_by": "rule",
        "confidence": None,
        "latency_ms": 0,
        "state_sha256": SHA,
        "suggestions": [],
    },
    "input_requested": {"request_id": "r", "kind": "block", "title": "t", "fields_schema_sha256": SHA},
    "input_provided": {"request_id": "r", "answer_ref": REF, "by": "engineer:x"},
    "approval_requested": {
        "request_id": "r",
        "kind": "INFO",
        "title": "t",
        "preview_ref": REF,
        "shown_sha256": SHA,
        "binding": {},
        "items": [],
    },
    "approval_resolved": {
        "request_id": "r",
        "shown_sha256": SHA,
        "decision": "approve",
        "rejected_items": [],
        "by": "mode:autonomous_logged",
    },
    "host_started": {"host_key": "h", "instance_id": "i", "pid": 7, "process_started_at": STAMP, "program": "etabs"},
    "model_bound": {
        "model_key": "m",
        "host_key": "h",
        "instance_id": "i",
        "reason": "first_use",
        "file_names": ["a.edb"],
    },
    "check_enforced": {"invariant": 1, "model_key": "m", "outcome": "pass"},
    "model_saved": {
        "model_key": "m",
        "model_id": "mdl_" + "0" * 26,
        "revision": 1,
        "fingerprint": "f",
        "file_sha256": SHA,
        "file_name": "a.edb",
        "role": "working_copy",
        "origin_sha256": SHA,
        "origin_file_names": ["a.edb"],
    },
    "run_paused": {"reason": "awaiting_input", "request_ids": ["r"]},
    "run_resumed": {"resume_no": 1, "code_hash_changed": False, "servers": [], "restored_to_seq": None},
    "run_escalated": {"reason": "attempts_exhausted", "detail": "d", "evidence": []},
    "run_completed": {"output_ref": REF, "output_sha256": SHA, "draft": True},
    "run_failed": {"reason": "abandoned", "by": "engineer:x"},
    "signed_off": {"outputs": [REF], "approval_request_id": "r", "by": "engineer:x"},
}
FULL_ALWAYS = {
    "run_started", "run_completed", "step_reconciled", "approval_requested", "approval_resolved", "model_saved",
    "input_provided", "run_failed", "signed_off", "host_started", "model_bound",
}  # fmt: skip


def _open(run_dir: Path, store: ResultStore, ids: SeededIdSource, **kw: Any) -> JournalWriter:
    return JournalWriter(run_dir, store, FixedClock(1_767_225_600_000, 1), ids, **kw)


def _write(writer: JournalWriter, count: int) -> None:
    for _ in range(count):
        writer.append(EventType.STEP_RERUN, SAMPLES["step_rerun"], path="p~1")


def _raw(run_dir: Path) -> sqlite3.Connection:
    return sqlite3.connect(run_dir / "journal.sqlite", isolation_level=None)


def _insert(conn: sqlite3.Connection, verb: str, seq: Any, kind: str = "step_rerun") -> None:
    body = canonical_json(SAMPLES["step_rerun"])
    sql = f"{verb} INTO events VALUES (?, ?, NULL, NULL, ?, ?, ?, ?)"
    conn.execute(sql, (seq, kind, STAMP, body, payload_sha256(SAMPLES["step_rerun"]), SHA))


def test_append_only(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    writer = _open(run_dir, store, ids)
    _write(writer, 2)
    conn = _raw(run_dir)
    assert conn.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    assert meta["run_id"] == run_dir.name
    assert {"schema_version", "created_at"} <= set(meta)
    statements = [
        "UPDATE events SET path = 'x'",
        "DELETE FROM events",
        "UPDATE meta SET value = 'x'",
        "DELETE FROM meta",
        "INSERT OR REPLACE INTO meta VALUES ('run_id', 'x')",
        "REPLACE INTO meta VALUES ('run_id', 'x')",
        "INSERT OR IGNORE INTO meta VALUES ('run_id', 'x')",
    ]
    for sql in statements:
        with pytest.raises(sqlite3.IntegrityError, match=r"append-only|write-once"):
            conn.execute(sql)
    for verb in ("INSERT OR REPLACE", "REPLACE", "INSERT OR IGNORE"):
        with pytest.raises(sqlite3.IntegrityError, match="next integer"):
            _insert(conn, verb, 1)
    for seq in (5, None, 2, 0):
        with pytest.raises(sqlite3.IntegrityError, match="next integer"):
            _insert(conn, "INSERT", seq)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        _insert(conn, "INSERT", 3, kind="bogus")
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone() == (2,)
    conn.close()
    assert writer.append(EventType.STEP_RERUN, SAMPLES["step_rerun"]) == 3
    writer.close()
    again = _open(run_dir, store, ids)  # a reopened journal continues the sequence and the chain
    assert again.append(EventType.STEP_RERUN, SAMPLES["step_rerun"]) == 4
    again.close()
    assert [e.seq for e in iter_events(_raw(run_dir))] == [1, 2, 3, 4]
    schema = " ".join(row[0] for row in _raw(run_dir).execute("SELECT sql FROM sqlite_master WHERE type='table'"))
    assert all(f"'{name}'" in schema for name in SPEC_TYPES)
    assert [t.value for t in EventType] == SPEC_TYPES
    assert set(PAYLOAD_MODELS) == set(EventType)


def _tamper(run_dir: Path, sql: str, *args: Any) -> None:
    conn = _raw(run_dir)
    for trigger in ("events_no_update", "events_no_delete"):
        conn.execute(f"DROP TRIGGER {trigger}")
    conn.execute(sql, args)
    conn.close()


@pytest.mark.parametrize(
    ("sql", "args", "bad_seq"),
    [
        ("UPDATE events SET payload = ? WHERE seq = 2", (b'{"reason":"restored"}',), 2),
        ("UPDATE events SET payload = ?, payload_sha256 = ? WHERE seq = 2", (b'{"reason":"restored"}', SHA), 2),
        ("UPDATE events SET chain_sha256 = ? WHERE seq = 3", (SHA,), 3),
        ("UPDATE events SET at = ? WHERE seq = 3", ("2027-01-01T00:00:00.000Z",), 3),
        ("DELETE FROM events WHERE seq = 2", (), 2),
        ("UPDATE events SET payload = ?, payload_sha256 = ? WHERE seq = 1", (b"{}", payload_sha256({})), 1),
    ],
)
def test_hash_chain_detects_tampering(
    run_dir: Path, store: ResultStore, ids: SeededIdSource, sql: str, args: tuple[Any, ...], bad_seq: int
) -> None:
    writer = _open(run_dir, store, ids)
    _write(writer, 3)
    writer.close()
    _tamper(run_dir, sql, *args)
    with pytest.raises(JournalIntegrityError, match=f"seq {bad_seq}\\b") as caught:
        _open(run_dir, store, ids)
    assert caught.value.code == "JOURNAL_INTEGRITY"
    assert caught.value.evidence == (f"seq:{bad_seq}",)


def test_untouched_journal_verifies_and_garbage_file_is_refused(
    run_dir: Path, store: ResultStore, ids: SeededIdSource
) -> None:
    writer = _open(run_dir, store, ids)
    _write(writer, 3)
    writer.close()
    _open(run_dir, store, ids).close()
    (run_dir / "journal.sqlite").write_bytes(b"this is not a database" * 100)
    with pytest.raises(JournalIntegrityError):
        _open(run_dir, store, ids)


class _Recording(sqlite3.Connection):
    modes: ClassVar[list[int]] = []

    def commit(self) -> None:
        if self.in_transaction:
            self.modes.append(self.execute("PRAGMA synchronous").fetchone()[0])
        super().commit()


def test_durability_policy(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    def connect(path: str) -> sqlite3.Connection:
        return _Recording(path, isolation_level=None)

    writer = _open(run_dir, store, ids, connect=connect)
    full, normal = 2, 1  # PRAGMA synchronous: FULL = 2, NORMAL = 1
    cases = [(name, SAMPLES[name]) for name in SPEC_TYPES]
    cases.append(("step_started", {**STEP, "effect": "write", "op_id": "o"}))
    for name, payload in cases:
        _Recording.modes.clear()
        writer.append(EventType(name), payload)
        is_full = payload.get("effect") == "write" or name in FULL_ALWAYS
        assert _Recording.modes == [full if is_full else normal], name
    assert {n for n, _ in cases if n not in FULL_ALWAYS and n != "step_started"} == {
        "step_completed", "step_failed", "step_rerun", "decision_made", "input_requested", "check_enforced",
        "run_paused", "run_resumed", "run_escalated",
    }  # fmt: skip


def _args(size: int) -> dict[str, Any]:
    return {"v": "x" * (size - len(canonical_json({"v": ""})))}


def test_large_payloads_by_reference(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    assert INLINE_EVENT_BYTES == 16384
    writer = _open(run_dir, store, ids)
    exact, big = _args(INLINE_EVENT_BYTES), _args(INLINE_EVENT_BYTES + 1)
    assert len(canonical_json(exact)) == INLINE_EVENT_BYTES
    writer.append(EventType.STEP_STARTED, {**STEP, "args": exact})
    writer.append(EventType.STEP_STARTED, {**STEP, "args": big})
    writer.close()
    first, second = (e.payload for e in iter_events(_raw(run_dir)))
    assert first.args == exact
    assert first.args_ref is None
    assert second.args is None
    assert second.args_ref is not None
    assert store.get(second.args_ref).kind == "harness.journal_blob/1"
    assert store.payload(second.args_ref) == {"value": big}
    stored = _raw(run_dir).execute("SELECT length(payload) FROM events WHERE seq = 2").fetchone()[0]
    assert stored < INLINE_EVENT_BYTES
    huge = {**SAMPLES["run_started"], "decision_runtime": {"k": "y" * INLINE_EVENT_BYTES}}
    with pytest.raises(ContractError) as caught:
        _open(run_dir, store, ids).append(EventType.RUN_STARTED, huge)
    assert caught.value.detail.code is ErrorCode.INTERNAL


def test_harness_kinds_are_registered() -> None:
    from eng_harness._kinds import HARNESS_KINDS

    for name in ("run_input", "run_output", "approval_preview", "journal_blob"):
        assert f"harness.{name}/1" in HARNESS_KINDS
    assert "model.stories/1" in HARNESS_KINDS


@pytest.mark.parametrize("name", SPEC_TYPES)
def test_payload_models(name: str, run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    writer = _open(run_dir, store, ids)
    kind = EventType(name)
    sample = SAMPLES[name]
    assert writer.append(kind, sample) == 1
    model = PAYLOAD_MODELS[kind]
    assert model.model_validate(sample) == next(iter_events(_raw(run_dir))).payload
    assert writer.append(kind, model.model_validate(sample)) == 2  # a model instance is accepted too
    bad: list[dict[str, Any]] = [{**sample, "unknown_field": 1}, dict(list(sample.items())[1:])]
    for payload in bad:
        with pytest.raises(ContractError) as caught:
            writer.append(kind, payload)
        assert caught.value.detail.code is ErrorCode.INTERNAL
        assert caught.value.detail.incident_id
    assert writer.last_seq == 2  # a refused payload leaves no event
    writer.close()


def test_stored_invalid_payload_is_integrity_error(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    writer = _open(run_dir, store, ids)
    _write(writer, 1)
    writer.close()
    conn = _raw(run_dir)
    bad = {"reason": "not_a_reason"}
    digest = payload_sha256(bad)
    prev = conn.execute("SELECT chain_sha256 FROM events WHERE seq = 1").fetchone()[0]
    chain = chain_hash(prev, 2, "step_rerun", None, None, STAMP, digest)  # a consistent row with an invalid payload
    conn.execute(
        "INSERT INTO events VALUES (2, 'step_rerun', NULL, NULL, ?, ?, ?, ?)",
        (STAMP, canonical_json(bad), digest, chain),
    )
    conn.close()
    with pytest.raises(JournalIntegrityError, match=r"seq 2\b"):
        _open(run_dir, store, ids)


def test_chain_hash_definition() -> None:
    zero = "0" * 64
    digest = chain_hash(zero, 1, "run_failed", None, None, STAMP, SHA)
    import hashlib

    row = {"seq": 1, "type": "run_failed", "path": None, "attempt": None, "at": STAMP, "payload_sha256": SHA}
    assert digest == hashlib.sha256(zero.encode() + canonical_json(row)).hexdigest()
    assert chain_hash(zero, 2, "run_failed", None, None, STAMP, SHA) != digest
