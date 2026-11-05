"""Journal schema, hash chain and verification (spec 0001 sections 4.4.1 and 4.4.2).

Errors: `JournalIntegrityError` names the first bad `seq`.
"""

import hashlib
import sqlite3
from collections.abc import Iterator

from eng_contract.canonical import CanonicalJsonError, canonical_json, loads, payload_sha256
from pydantic import BaseModel

from eng_harness.errors import JournalIntegrityError
from eng_harness.journal._events import PAYLOAD_MODELS, Event, EventType

SCHEMA_VERSION = "1"
ZERO_CHAIN = "0" * 64
_GUARDS = """
CREATE TRIGGER {t}_no_update BEFORE UPDATE ON {t} BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
CREATE TRIGGER {t}_no_delete BEFORE DELETE ON {t} BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
"""
SCHEMA = (
    """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE events (
  seq INTEGER PRIMARY KEY, type TEXT NOT NULL CHECK (type IN (<types>)), path TEXT,
  attempt INTEGER CHECK (attempt IS NULL OR attempt >= 1), at TEXT NOT NULL, payload BLOB NOT NULL,
  payload_sha256 TEXT NOT NULL, chain_sha256 TEXT NOT NULL
) STRICT;
CREATE TRIGGER events_next_seq BEFORE INSERT ON events
  WHEN NEW.seq IS NOT (SELECT COALESCE(MAX(seq), 0) + 1 FROM events)
  BEGIN SELECT RAISE(ABORT, 'journal seq must be the next integer'); END;
CREATE TRIGGER meta_insert_once BEFORE INSERT ON meta WHEN EXISTS (SELECT 1 FROM meta WHERE key = NEW.key)
  BEGIN SELECT RAISE(ABORT, 'journal meta is write-once'); END;
""".replace("<types>", ", ".join(f"'{t.value}'" for t in EventType))
    + _GUARDS.replace("{t}", "events")
    + _GUARDS.replace("{t}", "meta")
)
"""The DDL of a new journal (WAL mode is set by the writer)."""


def chain_hash(prev: str, seq: int, type_: str, path: str | None, attempt: int | None, at: str, digest: str) -> str:
    """`sha256(prev || canonical {seq, type, path, attempt, at, payload_sha256})` as lower-case hex."""
    row = {"seq": seq, "type": type_, "path": path, "attempt": attempt, "at": at, "payload_sha256": digest}
    return hashlib.sha256(prev.encode("ascii") + canonical_json(row)).hexdigest()


def iter_events(conn: sqlite3.Connection) -> Iterator[Event]:
    """Yield the events in `seq` order, verifying the sequence, payload hashes, chain and payload models.

    Raises:
        JournalIntegrityError: the file is not a journal of this schema, or `seq` N is the first bad event.
    """
    prev, expected = ZERO_CHAIN, 1
    try:
        version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if version != (SCHEMA_VERSION,):
            raise JournalIntegrityError("journal schema version is missing or unknown")
        rows = conn.execute(
            "SELECT seq, type, path, attempt, at, payload, payload_sha256, chain_sha256 FROM events ORDER BY seq"
        )
        for seq, type_, path, attempt, at, payload, digest, chain in rows:
            prev = chain_hash(prev, seq, type_, path, attempt, at, digest)
            if seq != expected or chain != prev:
                raise _damaged(expected)
            yield Event(seq, EventType(type_), path, attempt, at, _body(seq, type_, payload, digest))
            expected += 1
    except sqlite3.DatabaseError as exc:
        raise JournalIntegrityError(f"journal cannot be read: {exc}") from exc


def _damaged(seq: int) -> JournalIntegrityError:
    return JournalIntegrityError(f"journal event seq {seq} is damaged", evidence=[f"seq:{seq}"])


def _body(seq: int, type_: str, payload: bytes, digest: str) -> BaseModel:
    """The validated payload model; a hash, encoding or model mismatch is `JournalIntegrityError`."""
    try:
        data = loads(payload)
        if payload_sha256(data) != digest or canonical_json(data) != payload:
            raise _damaged(seq)
        return PAYLOAD_MODELS[EventType(type_)].model_validate(data)
    except (CanonicalJsonError, ValueError) as exc:
        raise _damaged(seq) from exc
