"""Report model: the journal and the store folded into the facts the report shows (spec 0006 4.6.1, sections 5 to 7).

Purpose: one frozen `ReportModel` per run, built from a `JournalReader` and the `ResultStore` only; the renderers (plan
0006 T12, T13) read it and never recompute an engineering value. `results` carries one entry per stored result the
journal references, which the renderers link to.
Units: milliseconds for durations and waiting; timestamps are contract `Timestamp` text.
Errors: `ReportError` when the journal's times are not in order; `ContractError` (`REF_NOT_FOUND`) when a referenced
result is not in the store.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from eng_contract.canonical import payload_sha256
from eng_contract.refs import parse_ref
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness.journal import Event, EventType, JournalReader, RunView
from eng_harness.journal import _events as ev
from eng_harness.journal._schema import ZERO_CHAIN, chain_hash
from eng_harness.report._lineage import ReportError

_MS = timedelta(milliseconds=1)
_ANSWERS = (EventType.APPROVAL_RESOLVED, EventType.INPUT_PROVIDED, EventType.DECISION_MADE)
_REF_FIELDS = ("input_ref", "basis_ref", "preview_ref", "answer_ref", "output_ref")


@dataclass(frozen=True)
class StepTiming:
    """One step attempt: start time and the duration the journal recorded (None while running)."""

    path: str
    attempt: int
    name: str
    status: str
    started_at: str
    duration_ms: int | None


@dataclass(frozen=True)
class Timings:
    """Per-step times, the engineer's waiting time, the machine time and the number of resumes (AC56)."""

    steps: tuple[StepTiming, ...]
    waiting_ms: int
    machine_ms: int
    resumes: int


@dataclass(frozen=True)
class ResumeEntry:
    """One `run_resumed` event."""

    resume_no: int
    at: str
    code_hash_changed: bool


@dataclass(frozen=True)
class HostEntry:
    """One `host_started` event: a host instance the run started."""

    host_key: str
    instance_id: str
    pid: int
    program: str
    at: str
    open: bool
    """True while the run has no terminal event: the engine closes started instances only after it (spec 0001 4.6)."""


@dataclass(frozen=True)
class RequestEntry:
    """An approval or input request with its first answer; `wait_ms`, `outcome` and `by` are None while open."""

    request_id: str
    kind: str
    title: str
    requested_at: str
    answered_at: str | None
    outcome: str | None
    by: str | None
    reasons: tuple[str, ...]
    wait_ms: int | None


@dataclass(frozen=True)
class DecisionEntry:
    """One `decision_made` event."""

    at: str
    point: str
    options: list[JsonValue]
    choice: JsonValue
    decided_by: str
    confidence: float | None
    request_id: str | None


@dataclass(frozen=True)
class EscalationEntry:
    """One `run_escalated` event."""

    at: str
    reason: str
    detail: str
    request_id: str | None


@dataclass(frozen=True)
class ReconciliationEntry:
    """One `step_reconciled` event."""

    at: str
    path: str | None
    op_id: str
    outcome: str
    decided_by: str


@dataclass(frozen=True)
class ResultEntry:
    """A stored result the journal references: identity, producer and parents, as the sources table shows them."""

    result_id: str
    kind: str
    tool: str
    tool_version: str
    created_at: str
    parents: tuple[str, ...]


@dataclass(frozen=True)
class ReportModel:
    """The folded run; `event_count` and `chain_sha256` are the integrity line (spec 4.6.1, section 1)."""

    run: RunView
    timings: Timings
    resumes: tuple[ResumeEntry, ...]
    hosts: tuple[HostEntry, ...]
    requests: tuple[RequestEntry, ...]
    decisions: tuple[DecisionEntry, ...]
    escalations: tuple[EscalationEntry, ...]
    reconciliations: tuple[ReconciliationEntry, ...]
    results: tuple[ResultEntry, ...]
    open_requests: tuple[str, ...]
    event_count: int
    chain_sha256: str


def wait_time_ms(requested_at: str, resolved_at: str) -> int:
    """Milliseconds between a request and its answer.

    Raises:
        ValueError: the answer is earlier than the request, or a time is not a timestamp.
    """
    delta = datetime.fromisoformat(resolved_at) - datetime.fromisoformat(requested_at)
    if delta < timedelta(0):
        raise ValueError("answer is before its request")
    return delta // _MS


def chain_of(events: Iterable[Event]) -> str:
    """The `chain_sha256` of the last event, recomputed from the verified events (`ZERO_CHAIN` when empty)."""
    chain = ZERO_CHAIN
    for e in events:
        digest = payload_sha256(e.payload.model_dump(mode="json"))
        chain = chain_hash(chain, e.seq, e.type.value, e.path, e.attempt, e.at, digest)
    return chain


def _requests(events: list[Event]) -> tuple[RequestEntry, ...]:
    """Approvals and inputs with their first answer: an approval by `approval_resolved`, an input by `input_provided`
    and an `engine.decision` input by `decision_made`. Waiting time is the answer's time minus the request's.

    Raises:
        ReportError: an answer is dated before its request.
    """
    answered: dict[tuple[EventType, str], Event] = {}
    for e in events:
        rid = getattr(e.payload, "request_id", None)
        if rid is not None and e.type in _ANSWERS:
            answered.setdefault((e.type, rid), e)
    entries = []
    for e in events:
        p = e.payload
        if not isinstance(p, ev.ApprovalRequested | ev.InputRequested):
            continue
        if isinstance(p, ev.ApprovalRequested):
            kind = EventType.APPROVAL_RESOLVED
        else:
            kind = EventType.DECISION_MADE if p.kind == "engine.decision" else EventType.INPUT_PROVIDED
        a = answered.get((kind, p.request_id))
        outcome: str | None = None
        by: str | None = None
        reasons: tuple[str, ...] = ()
        wait: int | None = None
        if a is not None:
            q = a.payload
            try:
                wait = wait_time_ms(e.at, a.at)
            except ValueError as exc:
                raise ReportError(f"request {p.request_id}: {exc}") from exc
            if isinstance(q, ev.ApprovalResolved):
                outcome, by = q.decision, q.by
                reasons = tuple(([q.reason] if q.reason else []) + [f"{k}: {v}" for k, v in q.item_reasons.items()])
            elif isinstance(q, ev.InputProvided):
                outcome, by = "provided", q.by
            elif isinstance(q, ev.DecisionMade):
                outcome, by = "decision", q.decided_by
        entries.append(
            RequestEntry(p.request_id, p.kind, p.title, e.at, a.at if a else None, outcome, by, reasons, wait)
        )
    return tuple(entries)


def _result_ids(events: list[Event]) -> list[str]:
    """Result ids the events reference (step results, previews, answers, run input, basis, output), once each."""
    seen: dict[str, None] = {}
    for e in events:
        p = e.payload
        refs = [getattr(p, name, None) for name in _REF_FIELDS]
        refs.append(getattr(getattr(p, "result", None), "ref", None))
        refs.extend(getattr(p, "outputs", ()))
        for ref in refs:
            if ref:
                seen.setdefault(parse_ref(ref)[0])
    return list(seen)


def fold_report(reader: JournalReader, store: ResultStore) -> ReportModel:
    """Fold the journal and the store records it references into a `ReportModel`.

    Machine time is the sum of the durations of completed step attempts, as the spec states; a block step's
    duration includes its children, which are also steps. Waiting time is the sum over answered requests.

    Raises:
        JournalIntegrityError: the journal fails verification.
        ReportError: an answer is dated before its request.
        ContractError: `REF_NOT_FOUND`, a referenced result is not in the store.
    """
    events = reader.events()
    run = reader.run()
    steps = tuple(StepTiming(s.path, s.attempt, s.name, s.status, s.started_at, s.duration_ms) for s in reader.steps())
    requests = _requests(events)
    resumes = tuple(
        ResumeEntry(e.payload.resume_no, e.at, e.payload.code_hash_changed)
        for e in events
        if isinstance(e.payload, ev.RunResumed)
    )
    hosts = tuple(
        HostEntry(
            e.payload.host_key, e.payload.instance_id, e.payload.pid, e.payload.program, e.at, run.ended_at is None
        )
        for e in events
        if isinstance(e.payload, ev.HostStarted)
    )
    decisions = tuple(
        DecisionEntry(
            e.at, e.payload.point, e.payload.options, e.payload.choice, e.payload.decided_by, e.payload.confidence,
            e.payload.request_id,
        )
        for e in events
        if isinstance(e.payload, ev.DecisionMade)
    )  # fmt: skip
    escalations = tuple(
        EscalationEntry(e.at, e.payload.reason, e.payload.detail, e.payload.request_id)
        for e in events
        if isinstance(e.payload, ev.RunEscalated)
    )
    reconciliations = tuple(
        ReconciliationEntry(e.at, e.path, e.payload.op_id, e.payload.outcome, e.payload.decided_by)
        for e in events
        if isinstance(e.payload, ev.StepReconciled)
    )
    records = [store.get(rid) for rid in _result_ids(events)]
    results = tuple(
        ResultEntry(r.result_id, r.kind, r.producer.tool, r.producer.tool_version, r.created_at, tuple(r.parents))
        for r in records
    )
    machine = sum(s.duration_ms or 0 for s in steps if s.status == "completed")
    waiting = sum(r.wait_ms or 0 for r in requests)
    resume_count = len({entry.resume_no for entry in resumes})
    return ReportModel(
        run, Timings(steps, waiting, machine, resume_count), resumes, hosts, requests, decisions, escalations,
        reconciliations, results, tuple(r.request_id for r in requests if r.answered_at is None), len(events),
        chain_of(events),
    )  # fmt: skip
