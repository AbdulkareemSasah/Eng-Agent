"""Steps in flight at a resume, and the request the engine puts to the engineer (spec 0001 4.5.1 step 7, 4.5.3).

Purpose: a write whose `step_started` has no result is reconciled before the block is called (`applied` and
`not_applied` become `step_reconciled`; anything else asks the engineer through `engine.in_flight`); a read, calc or
similar step in flight gets `step_rerun`. `Fold` reads the steps a resume needs from the journal, and `ResumeIndex`
replays a step marked for a rerun as one that runs again. Units: none. Errors: `Stopped` ends the resume with the
journaled stop (or the abandoned run), also for a write found applied whose result could not be read;
`JournalIntegrityError` for a write without an `op_id`; `ContractError` from a port call.
"""

import logging
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, TypedDict

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import FailureEnvelope, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError
from eng_contract.ids import Clock, IdSource
from eng_contract.store import ResultStore
from pydantic import JsonValue, TypeAdapter

from eng_harness import errors
from eng_harness.engine._ctx_impl import _stored
from eng_harness.engine._inputs import Evidence, Question, build_request, check_answer, choice_schema
from eng_harness.engine._replay import Recorded, ReplayIndex
from eng_harness.journal import Event, EventType, JournalReader, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import InputPort, Reconciliation, ToolPort

_LOG = logging.getLogger(__name__)
_ARGS = TypeAdapter(dict[str, JsonValue])


class _Entry(TypedDict):
    """One field of a stored engineer answer."""

    value: str


class _Stored(TypedDict):
    """The part of a stored `basis.engineer_input/1` answer that `Resume.ask` reads back."""

    fields: dict[str, _Entry]


_STORED = TypeAdapter(_Stored)
_Closing = ev.StepCompleted | ev.StepFailed | ev.StepReconciled
_RERUN = ("tool", "read", "calc")  # the kinds that run again when in flight; approvals and asks are presented again


class Stopped(errors.Escalation):
    """The resume ends before the block runs: `escalated` is the journaled stop, or None when the engineer abandoned."""

    def __init__(self, escalated: ev.RunEscalated | None) -> None:
        """Keep the journaled stop for the run outcome."""
        super().__init__("the run was abandoned" if escalated is None else escalated.detail)
        self.escalated = escalated


@dataclass
class Step:
    """The latest attempt of a step path; `rerun` is true once `step_rerun` marked it to run again as that attempt."""

    path: str
    seq: int
    attempt: int
    began: ev.StepStarted
    closing: _Closing | None = None
    rerun: bool = False


class Fold:
    """What a resume reads from the journal: the latest attempt of each step path."""

    def __init__(self, events: Sequence[Event]) -> None:
        """Fold `events`; housekeeping (`@`) and host (`~host.`) steps are audit records and are left out."""
        self.steps: dict[str, Step] = {}
        for e in events:
            p, path = e.payload, e.path
            if path is None or e.attempt is None or path.startswith("@") or "~host." in path:
                continue
            if isinstance(p, ev.StepStarted):
                self.steps[path] = Step(path, e.seq, e.attempt, p)
            elif (step := self.steps.get(path)) is not None:
                if isinstance(p, ev.StepRerun):
                    step.rerun = True
                elif isinstance(p, ev.StepCompleted | ev.StepFailed | ev.StepReconciled):
                    step.closing = p

    def pending(self) -> list[Step]:
        """The steps in flight: started, not closed, not marked for a rerun, in order of their start."""
        return sorted((s for s in self.steps.values() if s.closing is None and not s.rerun), key=lambda s: s.seq)


class ResumeIndex(ReplayIndex):
    """The replay index of a resume: a step marked for a rerun is recorded but runs again, as the same attempt."""

    def __init__(self, events: Sequence[Event]) -> None:
        """Index `events` and note the steps to run again."""
        super().__init__(events)
        self._again = {s.path: s for s in Fold(events).steps.values() if s.rerun}

    def lookup(
        self, path: str, kind: str, name: str, args_sha256: str, child: tuple[str, str] | None = None
    ) -> Recorded | None:
        """As `ReplayIndex.lookup` (same divergence checks), but a step to run again returns no outcome."""
        try:
            found = super().lookup(path, kind, name, args_sha256, child)
        except errors.NeedsReconciliation:
            if path not in self._again:
                raise
            found = None
        if (step := self._again.get(path)) is not None:
            return Recorded(step.attempt - 1, None)  # `Ctx` runs attempt `attempt + 1`
        return found


@dataclass
class Resume:
    """What the steps of a resume work with: ports, store, sources and the journal writer."""

    run_dir: Path
    run_id: str
    tool: ToolPort
    inputs: InputPort
    store: ResultStore
    clock: Clock
    ids: IdSource
    producer: Callable[[], Provenance]
    writer: JournalWriter

    def events(self) -> list[Event]:
        """The journal as it stands, read and verified."""
        with closing(JournalReader(self.run_dir)) as reader:
            return reader.events()

    def stop(self, detail: str, request_id: str | None) -> NoReturn:
        """Journal `run_escalated` and end the resume; the journal is otherwise as it was, so a later resume goes on."""
        escalated = ev.RunEscalated(reason="needs_reconciliation", detail=detail, evidence=[], request_id=request_id)
        self.writer.append(EventType.RUN_ESCALATED, escalated)
        raise Stopped(escalated)

    async def ask(self, rid: str, title: str, question: Question, why: str) -> tuple[str, str]:
        """Return the option chosen for the `engine.in_flight` request `rid` and who chose it.

        An answer an earlier resume journaled before it was cut short is read from the journal and is not asked or
        journaled again. Otherwise the request is presented: the run stops while there is no fitting answer (the
        request stays open and is presented again at each resume), and ends as `run_failed` on the choice `abandon`.
        """
        events = self.events()
        given = next(
            (e.payload for e in events if isinstance(e.payload, ev.InputProvided) and e.payload.request_id == rid), None
        )
        if given is None:
            choice, by = await self._answered(events, rid, title, question, why)
        else:
            stored = _STORED.validate_python(self.store.payload(given.answer_ref))
            choice, by = stored["fields"][question.name]["value"], given.by
        if choice == "abandon":
            self.writer.append(EventType.RUN_FAILED, {"reason": "abandoned", "by": by})
            raise Stopped(None)
        return choice, by

    async def _answered(
        self, events: Sequence[Event], rid: str, title: str, question: Question, why: str
    ) -> tuple[str, str]:
        """Present `rid` and journal the engineer's answer; stops the run while there is none that fits."""
        shown = [Evidence(name="why", label="What was found", text=why)]
        request = build_request(self.ids, rid, "engine.in_flight", title, choice_schema([question], shown))
        if not any(isinstance(e.payload, ev.InputRequested) and e.payload.request_id == rid for e in events):
            asked = {
                "request_id": rid,
                "kind": "engine.in_flight",
                "title": title,
                "fields_schema_sha256": request.fields_schema_sha256,
            }
            self.writer.append(EventType.INPUT_REQUESTED, asked)
        await self.inputs.present(request)
        answer = await self.inputs.answer(rid, wait=False)
        try:
            if answer is not None:
                check_answer(request, answer)
        except ContractError as refused:  # the request stays open, as for any answer that does not fit (4.9.1)
            _LOG.warning("the answer to %s is refused and the request stays open: %s", rid, refused)
            answer = None
        if answer is None:
            self.stop(why, rid)
        choice, by = (answer.choices or {})[question.name], "engineer:" + answer.by.removeprefix("engineer:")
        value: dict[str, JsonValue] = {
            "value": choice,
            "unit": None,
            "entered_by": answer.by,
            "entered_at": self.clock.now(),
        }
        stored = self.store.put(
            "basis.engineer_input/1", {"step": rid, "fields": {question.name: value}}, self.producer()
        )
        self.writer.append(EventType.INPUT_PROVIDED, {"request_id": rid, "answer_ref": stored.result_id, "by": by})
        return choice, by


async def reconcile(rt: Resume) -> None:
    """Step 7 of a resume (4.5.1): reconcile every write in flight, then mark the reads in flight for a rerun."""
    pending = Fold(rt.events()).pending()
    for step in (s for s in pending if s.began.effect == "write"):
        await _write(rt, step)
    for step in (s for s in pending if s.began.effect != "write" and s.began.kind in _RERUN):
        rt.writer.append(EventType.STEP_RERUN, {"reason": "read_in_flight"}, path=step.path, attempt=step.attempt)


async def _write(rt: Resume, step: Step) -> None:
    """Decide what became of the write in flight at `step` (4.5.3): the adapter, or else the engineer."""
    began = step.began
    if (op := began.op_id) is None:
        raise errors.JournalIntegrityError(f"the write at step {step.path} has no op_id")
    args = _ARGS.validate_python(
        began.args if began.args is not None else rt.store.payload(began.args_ref or "")["value"]
    )
    found, why = None, "the adapter has no reconciler for this tool"
    if rt.tool.supports_reconcile(began.name):
        try:
            found = await rt.tool.reconcile(began.name, args, op)
        except ContractError as exc:
            why = f"the reconciler failed: {exc.detail.message}"
        else:
            why = f"the adapter could not decide: {found.outcome}" + "".join(f", missing {m}" for m in found.missing)
    if found is not None and found.outcome in ("applied", "not_applied"):
        outcome, by, evidence = str(found.outcome), "adapter", [r.ref for r in found.evidence]
    else:
        question = Question(
            name="outcome", prompt="What happened to the write", options=("applied", "not_applied", "abandon")
        )
        rid = "inf_" + payload_sha256([rt.run_id, op])[:32]
        outcome, by = await rt.ask(rid, f"A write was cut off ({began.name})", question, why)
        evidence = []
    result = await _applied(rt, step, op, found, args) if outcome == "applied" else None
    payload = {"op_id": op, "outcome": outcome, "result": result and result.model_dump(mode="json"), "decided_by": by}
    rt.writer.append(EventType.STEP_RECONCILED, payload | {"evidence": evidence}, path=step.path, attempt=step.attempt)


async def _applied(
    rt: Resume, step: Step, op: str, found: Reconciliation | None, args: dict[str, JsonValue]
) -> ev.StepResult:
    """The result of a write found applied (4.5.3): the adapter's, else its read-back, else an empty summary.

    The empty summary is only for an adapter with no read-back (`None`). A failure, returned or raised, stops the
    resume with the step still in flight, so that the next resume reads it again.
    """
    name, error = step.began.name, None
    reply = found.result if found is not None and found.outcome == "applied" else None
    try:
        reply = reply if reply is not None else await rt.tool.read_back(name, args)
    except ContractError as exc:
        reply, error = None, exc.detail
    if isinstance(reply, FailureEnvelope):
        error = reply.error
    if error is not None:
        why = f"{error.code}: {error.message}"
        _LOG.warning("the result of the write at %s (%s) could not be read: %s", step.path, name, why)
        rt.stop(f"the write at step {step.path} was found applied, but its result could not be read: {why}", None)
    return _stored(reply) if isinstance(reply, SuccessEnvelope) else _nothing(rt, op)


def _nothing(rt: Resume, op: str) -> ev.StepResult:
    """The result of a write found applied that left no result: an empty summary, honestly marked incomplete."""
    ref = rt.store.put("harness.journal_blob/1", {"value": {"op_id": op}}, rt.producer()).result_id
    return ev.StepResult(ref=ref, summary={}, warnings=[], complete=False)
