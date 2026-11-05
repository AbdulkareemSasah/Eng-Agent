"""Read-only, chain-verifying journal reader and views (spec 0001 4.4.5). Times in ms; errors: JournalIntegrityError."""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal
from urllib.parse import quote

from eng_contract.errors import ErrorDetail
from pydantic import BaseModel, JsonValue

from eng_harness._runlock import is_locked
from eng_harness.errors import JournalIntegrityError
from eng_harness.journal import _events as ev
from eng_harness.journal._schema import iter_events

_T = ev.EventType
_Json = Mapping[str, JsonValue]


@dataclass(frozen=True)
class RunView:
    """The state of a run; `draft` is None until it completes, `escalation` is the open `run_escalated`."""

    run_id: str
    workflow: str
    mode: str
    status: str  # RUNNING, INTERRUPTED, PAUSED, NEEDS_ENGINEER, COMPLETED or FAILED
    started_at: str
    ended_at: str | None
    draft: bool | None
    pending: tuple[str, ...]
    escalation: ev.RunEscalated | None
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
    status: Literal["running", "completed", "failed", "reconciled", "rerun"]
    started_at: str
    ended_at: str | None
    duration_ms: int | None
    result_ref: str | None
    error: ErrorDetail | ev.HarnessError | None
    inserted: bool


@dataclass(frozen=True)
class RequestView:
    """An approval or input request; `resolution` is the first event that answers it, or None."""

    request_id: str
    kind: str
    title: str
    resolution: BaseModel | None


@dataclass(frozen=True)
class ModelSavedView:
    """One `model_saved` event; a model's history is the views with its `model_key`, in order."""

    seq: int
    saved: ev.ModelSaved


@dataclass(frozen=True)
class DecisionView:
    """One `decision_made` event."""

    seq: int
    path: str | None
    decision: ev.DecisionMade


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

    def events(self, after_seq: int = 0) -> list[ev.Event]:
        """Events with `seq` above `after_seq`, in order."""
        return [e for e in iter_events(self._conn) if e.seq > after_seq]

    def follow(self, after_seq: int) -> list[ev.Event]:
        """Same as `events`, for polling by the progress display."""
        return self.events(after_seq)

    def header(self) -> ev.RunHeader:
        """The `run_started` payload."""
        return self._head(self.events())[1]

    def models(self) -> list[ModelSavedView]:
        """`model_saved` events in order."""
        return [ModelSavedView(e.seq, e.payload) for e in self.events() if isinstance(e.payload, ev.ModelSaved)]

    def decisions(self) -> list[DecisionView]:
        """`decision_made` events in order."""
        return [DecisionView(e.seq, e.path, e.payload) for e in self.events() if isinstance(e.payload, ev.DecisionMade)]

    def requests(self) -> list[RequestView]:
        """Approvals and inputs with their resolution (a `decision_made` names its request by `request_id`)."""
        return self._requests(self.events())

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
            if isinstance(p, ev.StepStarted):
                inserted = "~" in e.path or e.path.startswith("@")
                views[key] = StepView(*key, p.kind, p.name, "running", e.at, None, None, None, None, inserted)
                continue
            if key not in views:
                raise JournalIntegrityError(f"step event seq {e.seq} has no step_started", evidence=[f"seq:{e.seq}"])
            end: dict[str, Any] = {"status": "rerun", "ended_at": e.at}
            if isinstance(p, ev.StepCompleted):
                ref = p.result.ref if p.result else p.output_ref
                end |= {"status": "completed", "duration_ms": p.duration_ms, "result_ref": ref}
            elif isinstance(p, ev.StepFailed):
                end |= {"status": "failed", "duration_ms": p.duration_ms, "error": p.error}
            elif isinstance(p, ev.StepReconciled):
                end |= {"status": "reconciled", "result_ref": p.result.ref if p.result else None}
            views[key] = replace(views[key], **end)
        return list(views.values())

    def run(self) -> RunView:
        """The folded state of the run (status rules: spec 0001 section 4.4.5)."""
        events = self.events()
        head, h = self._head(events)
        tools, runtime = dict(h.unreleased_tools), dict(h.decision_runtime)
        escalation: ev.RunEscalated | None = None
        ended: ev.Event | None = None
        paused = False
        for e in events:
            p = e.payload
            ended = ended or (e if e.type in (_T.RUN_COMPLETED, _T.RUN_FAILED) else None)
            if e.type in (_T.RUN_PAUSED, _T.RUN_RESUMED):
                paused = e.type is _T.RUN_PAUSED
            if e.type is _T.RUN_RESUMED:
                tools.update(getattr(p, "unreleased_tools", None) or {})
                runtime = getattr(p, "decision_runtime", None) or runtime
                escalation = None
            if isinstance(p, ev.RunEscalated):
                escalation = p
        pending = tuple(r.request_id for r in self._requests(events) if r.resolution is None)
        if ended is not None:
            status = "COMPLETED" if ended.type is _T.RUN_COMPLETED else "FAILED"
        elif escalation is not None:
            status = "NEEDS_ENGINEER"
        elif paused:
            status = "PAUSED"
        else:
            status = "RUNNING" if is_locked(self._run_dir) else "INTERRUPTED"
        return RunView(
            h.run_id, h.workflow, h.mode, status, head.at, ended.at if ended else None,
            getattr(ended.payload, "draft", None) if ended else None, pending, escalation, h.run_class,
            MappingProxyType(tools), MappingProxyType(runtime),
        )  # fmt: skip

    @staticmethod
    def _head(events: list[ev.Event]) -> tuple[ev.Event, ev.RunHeader]:
        for e in events:
            if isinstance(e.payload, ev.RunHeader):
                return e, e.payload
        raise JournalIntegrityError("journal has no run_started event")

    @staticmethod
    def _requests(events: list[ev.Event]) -> list[RequestView]:
        answers: dict[str, BaseModel] = {}
        for e in events:
            rid = getattr(e.payload, "request_id", None)
            if rid is not None and e.type in (_T.APPROVAL_RESOLVED, _T.INPUT_PROVIDED, _T.DECISION_MADE):
                answers.setdefault(rid, e.payload)
        return [
            RequestView(e.payload.request_id, e.payload.kind, e.payload.title, answers.get(e.payload.request_id))
            for e in events
            if isinstance(e.payload, ev.ApprovalRequested | ev.InputRequested)
        ]
