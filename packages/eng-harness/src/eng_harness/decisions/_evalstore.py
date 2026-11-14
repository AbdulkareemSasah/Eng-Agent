"""Append-only evaluation store and release verification (spec 0009 section 4.10, AC41, AC42).

``<workspace>/decisions/evaluations.sqlite`` is ``STRICT`` and append-only (triggers forbid ``UPDATE`` and ``DELETE``).
``verify_releases`` only drops an owner's release that no longer matches what runs (12 section 6). Units:
``min_confidence`` is a ratio. Errors: ``StoreWriteError`` (``INTERNAL``) for a failed open, write or read.
"""

import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from eng_contract.canonical import payload_sha256
from eng_contract.ids import Clock, IdSource, Timestamp
from pydantic import BaseModel, ConfigDict

from eng_harness.decisions._labels import LabeledExample, StoreWriteError
from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings, ShadowRelease
from eng_harness.decisions.interfaces import ProviderInfo

if TYPE_CHECKING:
    from eng_harness.decisions.evaluation import EvalReport, EvalThresholds

__all__ = [
    "EvalStore",
    "ReleaseFinding",
    "ReleaseVerification",
    "StoredEvaluation",
    "labels_sha256",
    "provider_key",
    "verify_releases",
]

_SCHEMA_VERSION = "1"
_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE evaluations (
  evaluation_id TEXT PRIMARY KEY, point TEXT NOT NULL, point_version INTEGER NOT NULL, by_json TEXT NOT NULL,
  thresholds_json TEXT NOT NULL, min_confidence REAL NOT NULL, report_json TEXT NOT NULL,
  labels_sha256 TEXT NOT NULL, eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)), reasons_json TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('store', 'export')), created_at TEXT NOT NULL
) STRICT;
CREATE TRIGGER evaluations_no_update BEFORE UPDATE ON evaluations
  BEGIN SELECT RAISE(ABORT, 'evaluations are append-only'); END;
CREATE TRIGGER evaluations_no_delete BEFORE DELETE ON evaluations
  BEGIN SELECT RAISE(ABORT, 'evaluations are append-only'); END;
"""
_SELECT = (
    "SELECT evaluation_id, point, point_version, by_json, thresholds_json, min_confidence, report_json, "
    "labels_sha256, eligible, reasons_json, source, created_at FROM evaluations"
)
_INSERT = "INSERT INTO evaluations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
_ReleaseReason = Literal[
    "record_missing", "record_not_eligible", "provider_changed", "point_version_changed", "threshold_mismatch"
]


class StoredEvaluation(BaseModel):
    """One stored evaluation; ``report`` and ``thresholds`` are the JSON of ``EvalReport`` and ``EvalThresholds``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_id: str
    point: str
    point_version: int
    by: tuple[str, ...]
    thresholds: dict[str, object]
    min_confidence: float
    report: dict[str, object]
    labels_sha256: str
    eligible: bool
    reasons: tuple[str, ...]
    source: Literal["store", "export"]
    created_at: Timestamp


class ReleaseFinding(BaseModel):
    """A release that was dropped, and why (AC42); the point stays in shadow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    point: str
    reason: _ReleaseReason


class ReleaseVerification(BaseModel):
    """The releases that are still valid and the findings for the others (in point order)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    releases: Mapping[str, ShadowRelease]
    findings: tuple[ReleaseFinding, ...]


def provider_key(tier: Literal["model", "llm"], info: ProviderInfo) -> str:
    """The key ``by`` of a provider's suggestions: ``model:<provider>/<model>@<version>`` or ``llm:...``."""
    return f"{tier}:{info.provider}/{info.model}@{info.version}"


def labels_sha256(labels: Sequence[LabeledExample]) -> str:
    """``payload_sha256`` of the sorted label ids with their choices and suggestion choices (AC41)."""
    rows = sorted([x.label_id, x.label, [s.choice for s in x.suggestions]] for x in labels)
    return payload_sha256(rows)


class EvalStore:
    """The evaluation records of one workspace."""

    def __init__(self, root: Path, clock: Clock, ids: IdSource) -> None:
        """Open or create ``<root>/decisions/evaluations.sqlite``; ``root`` is the workspace root.

        Raises:
            StoreWriteError: the folder or the file cannot be created.
        """
        self._clock, self._ids = clock, ids
        path = root / "decisions" / "evaluations.sqlite"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(path), isolation_level=None)
            self._conn.execute("PRAGMA synchronous=FULL")
            if self._conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'meta'").fetchone() is None:
                self._conn.executescript(_SCHEMA)
                self._conn.execute("INSERT INTO meta VALUES ('schema_version', ?)", (_SCHEMA_VERSION,))
        except (OSError, sqlite3.Error) as exc:
            raise self._failure(f"evaluation store cannot be opened: {type(exc).__name__}") from exc

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()

    def _failure(self, message: str) -> StoreWriteError:
        return StoreWriteError(message, self._ids.new_ulid())

    def append(
        self,
        point: str,
        point_version: int,
        report: EvalReport,
        thresholds: EvalThresholds,
        labels_hash: str,
        source: Literal["store", "export"],
    ) -> str:
        """Append one evaluation and return its id (AC41).

        Raises:
            StoreWriteError: the write failed.
        """
        evaluation_id = f"ev_{self._ids.new_ulid()}"
        row = (
            evaluation_id, point, point_version, json.dumps(sorted(report.by)),
            thresholds.model_dump_json(), thresholds.min_confidence, report.model_dump_json(), labels_hash,
            int(report.eligible), json.dumps(list(report.reasons)), source, self._clock.now(),
        )  # fmt: skip
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(_INSERT, row)
                self._conn.execute("COMMIT")
            except sqlite3.Error:
                self._conn.execute("ROLLBACK")
                raise
        except sqlite3.Error as exc:
            raise self._failure(f"evaluation store write failed: {type(exc).__name__}") from exc
        return evaluation_id

    def _read(self, where: str, params: tuple[str, ...]) -> tuple[StoredEvaluation, ...]:
        try:
            rows = self._conn.execute(_SELECT + where + " ORDER BY rowid", params).fetchall()
        except sqlite3.Error as exc:
            raise self._failure(f"evaluation store read failed: {type(exc).__name__}") from exc
        return tuple(
            StoredEvaluation(
                evaluation_id=r[0], point=r[1], point_version=r[2], by=tuple(json.loads(r[3])),
                thresholds=json.loads(r[4]), min_confidence=r[5], report=json.loads(r[6]), labels_sha256=r[7],
                eligible=bool(r[8]), reasons=tuple(json.loads(r[9])), source=r[10], created_at=r[11],
            )
            for r in rows
        )  # fmt: skip

    def get(self, evaluation_id: str) -> StoredEvaluation | None:
        """Return the evaluation with this id, or ``None``."""
        return next(iter(self._read(" WHERE evaluation_id = ?", (evaluation_id,))), None)

    def records(self, point: str) -> tuple[StoredEvaluation, ...]:
        """Return the evaluations of ``point`` in append order."""
        return self._read(" WHERE point = ?", (point,))


def _drop_reason(
    point: str,
    release: ShadowRelease,
    store: EvalStore,
    keys: frozenset[str],
    policy: DecisionPolicy,
    current_version: int | None,
) -> _ReleaseReason | None:
    """The reason to drop one release, or ``None`` when it stays (AC42)."""
    ids = [i for i in re.split(r"[,\s]+", release.record) if i]
    if not ids:
        return "record_missing"
    if release.point_version != current_version:
        return "point_version_changed"
    if release.basis == "owner":
        return None
    evaluations = [e for e in map(store.get, ids) if e is not None and e.point == point]
    if len(evaluations) != len(ids):
        return "record_missing"
    if not all(e.eligible for e in evaluations):
        return "record_not_eligible"
    if any(e.point_version != current_version for e in evaluations):
        return "point_version_changed"
    if not all(keys <= set(e.by) for e in evaluations):
        return "provider_changed"
    if any(e.min_confidence > policy.min_confidence for e in evaluations):
        return "threshold_mismatch"
    return None


def verify_releases(
    settings: DecisionSettings,
    store: EvalStore,
    provider_infos: Mapping[Literal["model", "llm"], ProviderInfo],
    policies: Mapping[str, DecisionPolicy],
    *,
    point_versions: Mapping[str, int],
) -> ReleaseVerification:
    """Keep the releases of ``settings.shadow_released`` that are still valid; report the others (AC42).

    ``provider_infos`` holds the configured providers by tier, ``policies`` the policy of each point (a point with none
    uses the defaults of 12 section 3) and ``point_versions`` the current version of each point. A release with basis
    ``owner`` is kept when its record is not blank and its point version is current.
    """
    keys = frozenset(provider_key(tier, info) for tier, info in provider_infos.items())
    kept: dict[str, ShadowRelease] = {}
    findings: list[ReleaseFinding] = []
    for point, release in sorted(settings.shadow_released.items(), key=lambda item: item[0]):
        policy = policies.get(point, DecisionPolicy())
        if reason := _drop_reason(point, release, store, keys, policy, point_versions.get(point)):
            findings.append(ReleaseFinding(point=point, reason=reason))
        else:
            kept[point] = release
    return ReleaseVerification(releases=kept, findings=tuple(findings))
