"""The append-only journal writer (spec 0001 sections 4.4.1 to 4.4.3; S-10, ADR-0030).

Purpose: one writer per run appends events to `<run_dir>/journal.sqlite`, one `BEGIN IMMEDIATE` transaction each, with
the hash chain and the per-event `synchronous` mode. Units: sizes in bytes. Errors: `ContractError` `INTERNAL` for an
invalid payload (an engine bug) or a failed write; `JournalIntegrityError` when an existing journal fails verification.
"""

import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path

from eng_contract.canonical import canonical_json, payload_sha256
from eng_contract.envelope import INLINE_DATA_LIMIT_BYTES, Provenance
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import Clock, IdSource
from eng_contract.store import ResultStore
from pydantic import BaseModel, JsonValue, ValidationError

from eng_harness import __version__
from eng_harness.errors import JournalIntegrityError
from eng_harness.journal._events import PAYLOAD_MODELS, EventType
from eng_harness.journal._schema import SCHEMA, SCHEMA_VERSION, ZERO_CHAIN, chain_hash, iter_events

INLINE_EVENT_BYTES = INLINE_DATA_LIMIT_BYTES
"""Largest canonical payload (for `step_started`, its arguments) kept inline in an event: 16384 (spec 4.4.1)."""
_FULL_EVENTS = frozenset(
    (
        EventType.RUN_STARTED, EventType.RUN_COMPLETED, EventType.STEP_RECONCILED, EventType.APPROVAL_REQUESTED,
        EventType.APPROVAL_RESOLVED, EventType.MODEL_SAVED, EventType.INPUT_PROVIDED, EventType.RUN_FAILED,
        EventType.SIGNED_OFF, EventType.HOST_STARTED, EventType.MODEL_BOUND,
    )
)  # fmt: skip
"""Events committed with `synchronous=FULL` regardless of content (spec 4.4.3); a write `step_started` is too."""
_INSERT = "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)"


def _connect(path: str) -> sqlite3.Connection:
    return sqlite3.connect(path, isolation_level=None)


class JournalWriter:
    """Single writer of one run's journal. Opening an existing journal verifies its chain first."""

    def __init__(
        self,
        run_dir: Path,
        store: ResultStore,
        clock: Clock,
        ids: IdSource,
        *,
        connect: Callable[[str], sqlite3.Connection] = _connect,
    ) -> None:
        """Create `<run_dir>/journal.sqlite` (meta: `schema_version`, `run_id` = folder name, `created_at`) or open it.

        `connect` opens the SQLite connection with `isolation_level=None`; tests wrap it to observe commits.

        Raises:
            JournalIntegrityError: the existing journal fails verification (AC21, AC26).
        """
        self._store, self._clock, self._ids = store, clock, ids
        path = run_dir / "journal.sqlite"
        fresh = not path.exists()
        self._conn = connect(str(path))
        self._seq, self._chain = 0, ZERO_CHAIN
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            if fresh:
                self._conn.executescript(SCHEMA)
                meta = {"schema_version": SCHEMA_VERSION, "run_id": run_dir.name, "created_at": clock.now()}
                self._commit("FULL", "INSERT INTO meta VALUES (?, ?)", list(meta.items()))
            for event in iter_events(self._conn):
                self._seq = event.seq
            last = self._conn.execute("SELECT chain_sha256 FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            self._chain = ZERO_CHAIN if last is None else last[0]
        except sqlite3.DatabaseError as exc:
            self._conn.close()
            raise JournalIntegrityError(f"journal cannot be opened: {exc}") from exc
        except JournalIntegrityError:
            self._conn.close()
            raise

    @property
    def last_seq(self) -> int:
        """`seq` of the last event, 0 for an empty journal."""
        return self._seq

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()

    def _internal(self, message: str, hint: str | None = None) -> ContractError:
        return ContractError(ErrorCode.INTERNAL, message, incident_id=self._ids.new_ulid(), hint=hint)

    def _commit(self, mode: str, sql: str, rows: list[tuple[object, ...]]) -> None:
        """One transaction; `mode` ("FULL" or "NORMAL") is the `synchronous` value of its commit."""
        try:
            self._conn.execute(f"PRAGMA synchronous={mode}")
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.executemany(sql, rows)
            self._conn.commit()
        except sqlite3.Error:
            if self._conn.in_transaction:
                self._conn.rollback()
            raise

    def append(
        self, type_: EventType, payload: BaseModel | Mapping[str, object], *, path: str | None = None,
        attempt: int | None = None,
    ) -> int:  # fmt: skip
        """Validate `payload` against the model of `type_` and commit it as the next event; return its `seq`.

        A `step_started` whose `args` exceed `INLINE_EVENT_BYTES` is stored with `args_ref`, a `harness.journal_blob/1`
        result (AC24). `path` is the step path (None for run-level events), `attempt` is at least 1.

        Raises:
            ContractError: `INTERNAL` for an invalid or oversized payload, or a failed write (no event is added).
        """
        try:
            data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
            body = PAYLOAD_MODELS[type_].model_validate(data).model_dump(mode="json")
        except ValidationError as exc:
            raise self._internal(f"payload is not a valid {type_} event", hint=str(exc.errors()[0]["loc"])) from exc
        args = body.get("args")
        if type_ is EventType.STEP_STARTED and args is not None and len(canonical_json(args)) > INLINE_EVENT_BYTES:
            body["args"], body["args_ref"] = None, self._blob(args)
        elif type_ is not EventType.STEP_STARTED and len(canonical_json(body)) > INLINE_EVENT_BYTES:
            raise self._internal(f"{type_} payload exceeds {INLINE_EVENT_BYTES} bytes and has no reference field")
        raw, seq, at = canonical_json(body), self._seq + 1, self._clock.now()
        digest = payload_sha256(body)
        chain = chain_hash(self._chain, seq, type_, path, attempt, at, digest)
        full = type_ in _FULL_EVENTS or body.get("effect") == "write"
        try:
            self._commit(
                "FULL" if full else "NORMAL", _INSERT, [(seq, type_.value, path, attempt, at, raw, digest, chain)]
            )
        except sqlite3.Error as exc:
            raise self._internal(f"journal write failed: {exc}") from exc
        self._seq, self._chain = seq, chain
        return seq

    def _blob(self, value: JsonValue) -> str:
        """Store `value` as a `harness.journal_blob/1` result and return its result id."""
        producer = Provenance(
            tool="harness", tool_version=__version__, inputs={}, started_at=self._clock.now(), duration_ms=0
        )
        return self._store.put("harness.journal_blob/1", {"value": value}, producer).result_id
