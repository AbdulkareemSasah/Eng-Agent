"""Report model: the journal folded into the facts the report shows (spec 0006 section 4.6.1, sections 5 to 7).

Purpose: one frozen `ReportModel` per run, built from `JournalReader` views and events only; the renderers (plan 0006
T12, T13) read it and never recompute an engineering value. Results from the store are shown by those renderers
through the references this model carries.
Units: milliseconds for durations and waiting; timestamps are contract `Timestamp` text.
Errors: `ReportError` when the journal's times are not in order.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from eng_contract.canonical import payload_sha256

from eng_harness.journal import Event, EventType, JournalReader, RunView
from eng_harness.journal._events import ApprovalRequested, HostStarted, InputRequested, RunResumed
from eng_harness.journal._schema import ZERO_CHAIN, chain_hash
from eng_harness.report._lineage import ReportError

_MS = timedelta(milliseconds=1)
_RESOLVING = {
    EventType.APPROVAL_REQUESTED: EventType.APPROVAL_RESOLVED,
    EventType.INPUT_REQUESTED: EventType.INPUT_PROVIDED,
}


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


@dataclass(frozen=True)
class ReportModel:
    """The folded run; `event_count` and `chain_sha256` are the integrity line (spec 4.6.1, section 1)."""

    run: RunView
    timings: Timings
    resumes: tuple[ResumeEntry, ...]
    hosts: tuple[HostEntry, ...]
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


def _waiting(events: list[Event]) -> tuple[int, tuple[str, ...]]:
    """Total waiting time over answered requests, and the ids of requests still unanswered.

    An approval is answered by `approval_resolved`, an input by `input_provided`, and an `engine.decision` input by
    `decision_made`; the first answer of a request counts.
    """
    answered: dict[tuple[EventType, str], str] = {}
    for e in events:
        rid = getattr(e.payload, "request_id", None)
        if rid is not None and e.type in (
            EventType.APPROVAL_RESOLVED,
            EventType.INPUT_PROVIDED,
            EventType.DECISION_MADE,
        ):
            answered.setdefault((e.type, rid), e.at)
    total, open_ids = 0, []
    for e in events:
        p = e.payload
        if not isinstance(p, ApprovalRequested | InputRequested):
            continue
        answer = EventType.DECISION_MADE if getattr(p, "kind", "") == "engine.decision" else _RESOLVING[e.type]
        at = answered.get((answer, p.request_id))
        if at is None:
            open_ids.append(p.request_id)
            continue
        try:
            total += wait_time_ms(e.at, at)
        except ValueError as exc:
            raise ReportError(f"request {p.request_id}: {exc}") from exc
    return total, tuple(open_ids)


def fold_report(reader: JournalReader) -> ReportModel:
    """Fold the journal into a `ReportModel`.

    Machine time is the sum of the durations of completed step attempts, as the spec states; a block step's
    duration includes its children, which are also steps.

    Raises:
        JournalIntegrityError: the journal fails verification.
        ReportError: an answer is dated before its request.
    """
    events = reader.events()
    steps = tuple(StepTiming(s.path, s.attempt, s.name, s.status, s.started_at, s.duration_ms) for s in reader.steps())
    waiting, open_ids = _waiting(events)
    resumes = tuple(
        ResumeEntry(e.payload.resume_no, e.at, e.payload.code_hash_changed)
        for e in events
        if isinstance(e.payload, RunResumed)
    )
    hosts = tuple(
        HostEntry(e.payload.host_key, e.payload.instance_id, e.payload.pid, e.payload.program, e.at)
        for e in events
        if isinstance(e.payload, HostStarted)
    )
    machine = sum(s.duration_ms or 0 for s in steps if s.status == "completed")
    return ReportModel(
        reader.run(), Timings(steps, waiting, machine, len(resumes)), resumes, hosts, open_ids, len(events),
        chain_of(events),
    )  # fmt: skip
