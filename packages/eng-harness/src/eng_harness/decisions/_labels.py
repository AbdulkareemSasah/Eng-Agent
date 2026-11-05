"""Label store and pending store of the decision layer (spec 0005 section 4.11, AC35 to AC39, AC44).

One SQLite file ``<workspace>/decisions/decisions.sqlite`` with ``STRICT`` tables. ``labels`` is append-only (triggers
forbid ``UPDATE`` and ``DELETE``); ``pending`` rows are inserted and closed, and only ``closed_at`` may change, once.
Units: none. Errors: ``StoreWriteError`` (``ContractError`` ``INTERNAL``) for a failed write, ``ContractError``
``NOT_FOUND`` for an unknown request, ``INVALID_ARGUMENT`` for a disabled export or a choice that is no option.
"""

import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from eng_contract.canonical import canonical_json
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import Clock, IdSource, Timestamp
from pydantic import BaseModel, ConfigDict, JsonValue

from eng_harness.decisions._policy import DecisionSettings
from eng_harness.decisions._record import DecisionScreen, Suggestion
from eng_harness.decisions._redaction import RedactionFinding

__all__ = ["LabelStore", "LabeledExample", "OverriddenDecision", "PendingRecord", "StoreWriteError"]

_SCHEMA_VERSION = "1"
_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE labels (
  label_id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, point TEXT NOT NULL, point_version INTEGER NOT NULL,
  run_id TEXT NOT NULL, step_path TEXT NOT NULL, options_json TEXT NOT NULL, state_json TEXT,
  state_sha256 TEXT NOT NULL, label TEXT NOT NULL, engineer TEXT NOT NULL, suggestions_json TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('engineer_decision', 'engineer_override')), created_at TEXT NOT NULL
) STRICT;
CREATE TRIGGER labels_no_update BEFORE UPDATE ON labels BEGIN SELECT RAISE(ABORT, 'labels are append-only'); END;
CREATE TRIGGER labels_no_delete BEFORE DELETE ON labels BEGIN SELECT RAISE(ABORT, 'labels are append-only'); END;
CREATE TABLE pending (
  request_id TEXT PRIMARY KEY, batch_id TEXT, screen_json TEXT NOT NULL, outcomes_json TEXT NOT NULL,
  created_at TEXT NOT NULL, closed_at TEXT
) STRICT;
CREATE TRIGGER pending_no_delete BEFORE DELETE ON pending BEGIN SELECT RAISE(ABORT, 'pending rows are kept'); END;
CREATE TRIGGER pending_close_only BEFORE UPDATE ON pending
  WHEN OLD.closed_at IS NOT NULL OR NEW.request_id IS NOT OLD.request_id OR NEW.batch_id IS NOT OLD.batch_id
    OR NEW.screen_json IS NOT OLD.screen_json OR NEW.outcomes_json IS NOT OLD.outcomes_json
    OR NEW.created_at IS NOT OLD.created_at
  BEGIN SELECT RAISE(ABORT, 'only closed_at of an open pending row may change'); END;
"""
_SELECT = (
    "SELECT label_id, request_id, point, point_version, run_id, step_path, options_json, state_json, state_sha256, "
    "label, engineer, suggestions_json, source, created_at FROM labels"
)
_INSERT = (
    "INSERT INTO labels (label_id, request_id, point, point_version, run_id, step_path, options_json, state_json, "
    "state_sha256, label, engineer, suggestions_json, source, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(request_id) DO NOTHING"
)
_EXPORT_DROPPED = frozenset({"engineer", "run_id", "step_path", "request_id", "label_id"})


class StoreWriteError(ContractError):
    """A write to ``decisions.sqlite`` failed; the code is fixed to ``INTERNAL`` and the message carries no value."""

    def __init__(self, message: str, incident_id: str) -> None:
        """Build the ``INTERNAL`` error with its ``incident_id``."""
        super().__init__(ErrorCode.INTERNAL, message, incident_id=incident_id)


class LabeledExample(BaseModel):
    """One label row (spec AC35). ``state`` is null when it failed the redaction check; ``label`` is the choice."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label_id: str
    request_id: str
    point: str
    point_version: int
    run_id: str
    step_path: str
    options: tuple[str, ...]
    state: dict[str, JsonValue] | None
    state_sha256: str
    label: str
    engineer: str
    suggestions: tuple[Suggestion, ...] = ()
    source: Literal["engineer_decision", "engineer_override"]
    created_at: Timestamp


class OverriddenDecision(BaseModel):
    """Identity of a decision taken by a rule, model or LLM, read by the caller from its ``decision_made`` event.

    Gap Q14 of spec 0005: neither the store nor the journal keys such a decision by ``request_id``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    point: str
    point_version: int
    run_id: str
    step_path: str
    options: tuple[str, ...]
    state_sha256: str


class PendingRecord(BaseModel):
    """A stored pending request; ``outcomes`` maps request ids to the resolved outcomes of a batch's other calls."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    screen: DecisionScreen
    batch_id: str | None
    outcomes: dict[str, JsonValue]
    created_at: Timestamp
    closed_at: Timestamp | None


def _connect(path: str) -> sqlite3.Connection:
    return sqlite3.connect(path, isolation_level=None)


def _dump(value: BaseModel | Sequence[BaseModel]) -> str:
    """Canonical JSON text of a model or a sequence of models (serialized by alias, as the journal does)."""
    data = (
        value.model_dump(mode="json", by_alias=True)
        if isinstance(value, BaseModel)
        else [v.model_dump(mode="json", by_alias=True) for v in value]
    )
    return canonical_json(data).decode("utf-8")


class LabelStore:
    """The label and pending stores of one workspace."""

    def __init__(
        self,
        root: Path,
        settings: DecisionSettings,
        clock: Clock,
        ids: IdSource,
        *,
        connect: Callable[[str], sqlite3.Connection] = _connect,
    ) -> None:
        """Open or create ``<root>/decisions/decisions.sqlite``; ``root`` is the workspace root.

        Raises:
            StoreWriteError: the folder or the file cannot be created.
        """
        self._settings, self._clock, self._ids = settings, clock, ids
        path = root / "decisions" / "decisions.sqlite"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = connect(str(path))
            self._conn.execute("PRAGMA synchronous=FULL")
            has_meta = self._conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'meta'").fetchone()
            if has_meta is None:
                self._conn.executescript(_SCHEMA)
                self._conn.execute("INSERT INTO meta VALUES ('schema_version', ?)", (_SCHEMA_VERSION,))
        except (OSError, sqlite3.Error) as exc:
            raise self._failure(f"decision store cannot be opened: {type(exc).__name__}") from exc

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()

    def _failure(self, message: str) -> StoreWriteError:
        return StoreWriteError(message, self._ids.new_ulid())

    def _write(self, sql: str, params: tuple[Any, ...]) -> int:
        """Run one statement in its own transaction; return the row count. Errors: ``StoreWriteError``."""
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                count = self._conn.execute(sql, params).rowcount
                self._conn.execute("COMMIT")
            except sqlite3.Error:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise
        except sqlite3.Error as exc:
            raise self._failure(f"decision store write failed: {type(exc).__name__}") from exc
        return count

    def _insert(self, label: LabeledExample, state: dict[str, JsonValue] | None) -> None:
        self._write(
            _INSERT,
            (
                label.label_id, label.request_id, label.point, label.point_version, label.run_id, label.step_path,
                canonical_json(list(label.options)).decode("utf-8"),
                None if state is None else canonical_json(state).decode("utf-8"),
                label.state_sha256, label.label, label.engineer, _dump(label.suggestions), label.source,
                label.created_at,
            ),
        )  # fmt: skip

    def append(self, label: LabeledExample, findings: Sequence[RedactionFinding]) -> None:
        """Append ``label`` before the engineer's answer is returned (AC35); a second ``request_id`` is ignored.

        ``findings`` are those the cascade computed over the union of sensitive values (spec 4.5 step 1): when they are
        non-empty only ``state_sha256`` is kept and ``state`` is stored as null (AC36). The value check is not re-run.

        Raises:
            StoreWriteError: the write failed (AC37); the pending request stays presented.
        """
        self._insert(label, None if findings else label.state)

    def record_override(
        self, request_id: str, new_choice: str, by: str, *, overridden: OverriddenDecision | None = None
    ) -> None:
        """Append an ``engineer_override`` label for a decision of a rule, model or LLM (AC38); always hash-only.

        ``overridden`` carries the decision's identity (gap Q14 of spec 0005).

        Raises:
            ContractError: ``NOT_FOUND`` when ``overridden`` is absent (the request cannot be resolved);
                ``INVALID_ARGUMENT`` (field ``new_choice``) when ``new_choice`` is not one of its options.
            StoreWriteError: the write failed.
        """
        if overridden is None:
            raise ContractError(
                ErrorCode.NOT_FOUND, "the overridden decision cannot be resolved", hint=f"request_id {request_id}"
            )
        if new_choice not in overridden.options:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "new_choice is not an option", field="new_choice")
        self._insert(
            LabeledExample(
                label_id=f"lbl_{self._ids.new_ulid()}", request_id=request_id, point=overridden.point,
                point_version=overridden.point_version, run_id=overridden.run_id, step_path=overridden.step_path,
                options=overridden.options, state=None, state_sha256=overridden.state_sha256, label=new_choice,
                engineer=by, suggestions=(), source="engineer_override", created_at=self._clock.now(),
            ),
            None,
        )  # fmt: skip

    def read(self, point: str, point_version: int | None = None) -> tuple[LabeledExample, ...]:
        """Return the labels of ``point`` (of one version when given) in append order.

        Raises:
            ContractError: ``INTERNAL`` when the store cannot be read.
        """
        try:
            rows = self._conn.execute(
                _SELECT + " WHERE point = ? AND (? IS NULL OR point_version = ?) ORDER BY rowid",
                (point, point_version, point_version),
            ).fetchall()
        except sqlite3.Error as exc:
            raise self._failure(f"decision store read failed: {type(exc).__name__}") from exc
        return tuple(
            LabeledExample(
                label_id=r[0], request_id=r[1], point=r[2], point_version=r[3], run_id=r[4], step_path=r[5],
                options=tuple(json.loads(r[6])), state=None if r[7] is None else json.loads(r[7]), state_sha256=r[8],
                label=r[9], engineer=r[10], suggestions=tuple(Suggestion.model_validate(s) for s in json.loads(r[11])),
                source=r[12], created_at=r[13],
            )
            for r in rows
        )  # fmt: skip

    def export_labels(self, point: str, folder: Path) -> Path:
        """Write ``<folder>/<point>.jsonl``, one canonical-JSON line per label, and return its path (AC39).

        ``state`` is written only where the redaction check passed (the stored state is not null); ``engineer``,
        ``run_id``, ``step_path`` and the request and label ids are never written.

        Raises:
            ContractError: ``INVALID_ARGUMENT`` (field ``export_enabled``) unless ``DecisionSettings.export_enabled``.
        """
        if not self._settings.export_enabled:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, "label export is disabled", field="export_enabled",
                hint="set export_enabled in the decision settings",
            )  # fmt: skip
        lines = []
        for label in self.read(point):
            data = label.model_dump(mode="json", by_alias=True, exclude=set(_EXPORT_DROPPED))
            lines.append(canonical_json(data).decode("utf-8") + "\n")
        out = folder / f"{point}.jsonl"
        folder.mkdir(parents=True, exist_ok=True)
        temp = out.with_suffix(".jsonl.tmp")
        temp.write_text("".join(lines), encoding="utf-8")
        temp.replace(out)
        return out

    def open_pending(
        self, request_id: str, batch_id: str | None, screen: DecisionScreen, outcomes: Mapping[str, JsonValue]
    ) -> None:
        """Store a presented request (idempotent: a second call with the same ``request_id`` keeps the first row)."""
        self._write(
            "INSERT INTO pending (request_id, batch_id, screen_json, outcomes_json, created_at, closed_at) "
            "VALUES (?, ?, ?, ?, ?, NULL) ON CONFLICT(request_id) DO NOTHING",
            (request_id, batch_id, _dump(screen), canonical_json(dict(outcomes)).decode("utf-8"), self._clock.now()),
        )

    def get_pending(self, request_id: str) -> PendingRecord | None:
        """Return the stored pending request, or ``None`` when there is none."""
        try:
            row = self._conn.execute(
                "SELECT screen_json, batch_id, outcomes_json, created_at, closed_at FROM pending WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise self._failure(f"decision store read failed: {type(exc).__name__}") from exc
        if row is None:
            return None
        return PendingRecord(
            screen=DecisionScreen.model_validate_json(row[0]), batch_id=row[1], outcomes=json.loads(row[2]),
            created_at=row[3], closed_at=row[4],
        )  # fmt: skip

    def close_pending(self, request_id: str, closed_at: Timestamp) -> None:
        """Set ``closed_at`` of a pending row; a row already closed keeps its first value.

        Raises:
            ContractError: ``NOT_FOUND`` for an unknown ``request_id``.
        """
        if self.get_pending(request_id) is None:
            raise ContractError(ErrorCode.NOT_FOUND, "no pending request", hint=f"request_id {request_id}")
        self._write(
            "UPDATE pending SET closed_at = ? WHERE request_id = ? AND closed_at IS NULL", (closed_at, request_id)
        )
