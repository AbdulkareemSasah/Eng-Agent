"""The journal reading API and its views (spec 0001 section 4.4.5).

Purpose: a read-only, chain-verifying fold of a run's events for the progress display, the approval page and the
report. Units: times are contract timestamps, durations milliseconds. Errors: `JournalIntegrityError`.
"""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from urllib.parse import quote

from eng_contract.errors import ErrorDetail
from pydantic import BaseModel, JsonValue

from eng_harness._runlock import is_locked
from eng_harness.errors import JournalIntegrityError
from eng_harness.journal._events import (
    ApprovalRequested,
    DecisionMade,
    Event,
    EventType,
    HarnessError,
    InputRequested,
    ModelSaved,
    RunEscalated,
    RunHeader,
    StepCompleted,
    StepFailed,
    StepReconciled,
    StepStarted,
)  # fmt: skip
from eng_harness.journal._schema import iter_events

RunStatus = Literal["RUNNING", "INTERRUPTED", "PAUSED", "NEEDS_ENGINEER", "COMPLETED", "FAILED"]
StepStatus = Literal["running", "completed", "failed", "reconciled", "rerun"]
_Json = Mapping[str, JsonValue]
_T = EventType


@dataclass(frozen=True)
class RunView:
    """The state of a run; `draft` is None until it completes, `escalation` is the open `run_escalated`."""

    run_id: str
    workflow: str
    mode: str
    status: RunStatus
    started_at: str
    ended_at: str | None
    draft: bool | None
    pending: tuple[str, ...]
    escalation: RunEscalated | None
    run_class: str
    unreleased_tools: _Json
    decision_runtime: _Json


@dataclass(frozen=True)
class StepView:
    """One step attempt; `inserted` marks engine-inserted (`~`) and housekeeping (`@`) paths."""

    path: str
    attempt: int
    kind: str
    name: str
    status: StepStatus
    started_at: str
    ended_at: str | None
    duration_ms: int | None
    result_ref: str | None
    error: ErrorDetail | HarnessError | None
    inserted: bool


@dataclass(frozen=True)
class RequestView:
    """An approval or input request; `resolution` is the first event that answers it, or None."""

    request_id: str
    kind: str
    title: str
    requested_at: str
    resolution: BaseModel | None
    resolved_at: str | None


@dataclass(frozen=True)
class ModelSavedView:
    """One `model_saved` event; the history of a model is the views with its `model_key`, in order."""

    seq: int
    at: str
    saved: ModelSaved


@dataclass(frozen=True)
class DecisionView:
    """One `decision_made` event."""

    seq: int
    at: str
    path: str | None
    decision: DecisionMade


class JournalReader:
    """Read-only access to `<run_dir>/journal.sqlite`; every call re-reads and re-verifies the chain."""

    def __init__(self, run_dir: Path) -> None:
        """Open read-only and verify the chain.

        Raises:
            JournalIntegrityError: the journal is missing, unreadable or fails verification.
        """
        self._run_dir = run_dir
        uri = f"file:{quote((run_dir / 'journal.sqlite').as_posix())}?mode=ro"
        try:
            self._conn = sqlite3.connect(uri, uri=True, isolation_level=None)
        except sqlite3.Error as exc:
            raise JournalIntegrityError(f"journal cannot be opened: {exc}") from exc
        try:
            self.events()
        except JournalIntegrityError:
            self._conn.close()
            raise

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()

    def events(self, after_seq: int = 0) -> list[Event]:
        """Events with `seq` above `after_seq`, in order."""
        return [e for e in iter_events(self._conn) if e.seq > after_seq]

    def follow(self, after_seq: int) -> list[Event]:
        """Same as `events`, for polling by the progress display."""
        return self.events(after_seq)

    def header(self) -> RunHeader:
        """The `run_started` payload."""
        return self._head(self.events())[1]

    @staticmethod
    def _head(events: list[Event]) -> tuple[Event, RunHeader]:
        for e in events:
            if isinstance(e.payload, RunHeader):
                return e, e.payload
        raise JournalIntegrityError("journal has no run_started event")

    def requests(self) -> list[RequestView]:
        """Approvals and inputs with their resolution (a `decision_made` names its request by `request_id`)."""
        return self._requests(self.events())

    @staticmethod
    def _requests(events: list[Event]) -> list[RequestView]:
        answers: dict[str, Event] = {}
        for e in events:
            rid = getattr(e.payload, "request_id", None)
            if rid is not None and e.type in (_T.APPROVAL_RESOLVED, _T.INPUT_PROVIDED, _T.DECISION_MADE):
                answers.setdefault(rid, e)
        views = []
        for e in events:
            p = e.payload
            if isinstance(p, ApprovalRequested | InputRequested):
                done = answers.get(p.request_id)
                views.append(
                    RequestView(p.request_id, p.kind, p.title, e.at, done.payload if done else None,
                                done.at if done else None)
                )  # fmt: skip
        return views

    def models(self) -> list[ModelSavedView]:
        """`model_saved` events in order."""
        return [ModelSavedView(e.seq, e.at, e.payload) for e in self.events() if isinstance(e.payload, ModelSaved)]

    def decisions(self) -> list[DecisionView]:
        """`decision_made` events in order."""
        return [
            DecisionView(e.seq, e.at, e.path, e.payload) for e in self.events() if isinstance(e.payload, DecisionMade)
        ]

    def steps(self) -> list[StepView]:
        """One view per path and attempt, in order of first start.

        Raises:
            JournalIntegrityError: a step event has no matching `step_started`.
        """
        views: dict[tuple[str, int], StepView] = {}
        for e in self.events():
            if e.path is None or e.attempt is None or not e.type.value.startswith("step_"):
                continue
            key, p = (e.path, e.attempt), e.payload
            if isinstance(p, StepStarted):
                inserted = "~" in e.path or e.path.startswith("@")
                views[key] = StepView(*key, p.kind, p.name, "running", e.at, None, None, None, None, inserted)
                continue
            if key not in views:
                raise JournalIntegrityError(f"step event seq {e.seq} has no step_started", evidence=[f"seq:{e.seq}"])
            old = views[key]
            if isinstance(p, StepCompleted):
                views[key] = _closed(old, "completed", e.at, p.duration_ms, p.result.ref if p.result else p.output_ref)
            elif isinstance(p, StepFailed):
                views[key] = _closed(old, "failed", e.at, p.duration_ms, error=p.error)
            elif isinstance(p, StepReconciled):
                views[key] = _closed(old, "reconciled", e.at, result_ref=p.result.ref if p.result else None)
            else:
                views[key] = _closed(old, "rerun", e.at)
        return list(views.values())

    def run(self) -> RunView:
        """The folded state of the run (status rules: spec 0001 section 4.4.5)."""
        events = self.events()
        head, h = self._head(events)
        tools, runtime = dict(h.unreleased_tools), dict(h.decision_runtime)
        escalation: RunEscalated | None = None
        ended: Event | None = None
        last_state = head
        for e in events:
            p = e.payload
            if ended is None and e.type in (_T.RUN_COMPLETED, _T.RUN_FAILED):
                ended = e
            if e.type is _T.RUN_RESUMED:
                tools.update(getattr(p, "unreleased_tools", None) or {})
                runtime = getattr(p, "decision_runtime", None) or runtime
                escalation = None
            if isinstance(p, RunEscalated):
                escalation = p
            if e.type in (_T.RUN_PAUSED, _T.RUN_RESUMED, _T.RUN_ESCALATED):
                last_state = e
        requests = self._requests(events)
        open_ = [r for r in requests if r.resolution is None]
        status: RunStatus
        if ended is not None:
            status = "COMPLETED" if ended.type is _T.RUN_COMPLETED else "FAILED"
        elif escalation is not None:
            status = "NEEDS_ENGINEER"
        elif last_state.type is _T.RUN_PAUSED:
            status = "PAUSED"
        else:
            status = "RUNNING" if is_locked(self._run_dir) else "INTERRUPTED"
        draft = getattr(ended.payload, "draft", None) if ended else None
        return RunView(
            h.run_id, h.workflow, h.mode, status, head.at, ended.at if ended else None, draft,
            tuple(r.request_id for r in open_), escalation, h.run_class, MappingProxyType(tools),
            MappingProxyType(runtime),
        )  # fmt: skip


def _closed(
    old: StepView, status: StepStatus, at: str, duration: int | None = None, result_ref: str | None = None,
    error: ErrorDetail | HarnessError | None = None,
) -> StepView:  # fmt: skip
    """A copy of `old` with the outcome fields of the closing event."""
    return StepView(
        old.path, old.attempt, old.kind, old.name, status, old.started_at, at, duration, result_ref or old.result_ref,
        error, old.inserted,
    )  # fmt: skip
