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
from typing import Literal, NoReturn, TypedDict

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import FailureEnvelope, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError
from eng_contract.ids import Clock, IdSource
from eng_contract.store import ResultStore
from pydantic import JsonValue, TypeAdapter

from eng_harness import errors
from eng_harness.ctx import ModelHandle
from eng_harness.engine._ctx_impl import _stored
from eng_harness.engine._inputs import Evidence, Kind, Question, build_request, check_answer, choice_schema
from eng_harness.engine._replay import Recorded, ReplayIndex
from eng_harness.engine._steps import resume_path
from eng_harness.journal import Event, EventType, JournalReader, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import HostPort, InputPort, Reconciliation, ToolPort

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
_Reason = Literal["needs_reconciliation", "units_mismatch", "host_state_mismatch"]
_RERUN = ("tool", "read", "calc", "decide", "decide_many", "approve", "ask")  # an approval or ask is presented again


class Stopped(errors.Escalation):
    """The resume ends before the block runs: `escalated` is the journaled stop, or None when the engineer abandoned."""

    def __init__(self, escalated: ev.RunEscalated | None) -> None:
        """Keep the journaled stop for the run outcome."""
        super().__init__("the run was abandoned" if escalated is None else escalated.detail)
        self.escalated = escalated


@dataclass
class Step:
    """The latest attempt of a step path; `rerun` is 0 to run again as that attempt, 1 as the next, else None."""

    path: str
    seq: int
    attempt: int
    began: ev.StepStarted
    closing: _Closing | None = None
    closed_at: int = 0
    rerun: int | None = None


class Fold:
    """What a resume reads from the journal: step paths, each model's binding and last save, restored cuts (4.5.4)."""

    def __init__(self, events: Sequence[Event]) -> None:
        """Fold `events`; housekeeping (`@`) and host (`~host.`) steps are audit records and are left out."""
        # a restore's cut (a, b): the saves and steps between sequence a and its second `run_resumed` b are undone
        cuts = [(r.restored_to_seq or e.seq, e.seq) for e in events if isinstance(r := e.payload, ev.RunResumed)]
        self.steps: dict[str, Step] = {}
        self.bound: dict[str, ev.ModelBound] = {}
        self.bound_at: dict[str, int] = {}
        self.saved: dict[str, tuple[int, ev.ModelSaved]] = {}
        for e in events:
            p, path = e.payload, e.path
            if isinstance(p, ev.ModelBound):
                self.bound[p.model_key], self.bound_at[p.model_key] = p, e.seq
            elif isinstance(p, ev.ModelSaved) and not any(a < e.seq < b for a, b in cuts):
                self.saved[p.model_key] = (e.seq, p)
            if path is None or e.attempt is None or path.startswith("@") or "~host." in path:
                continue
            if isinstance(p, ev.StepStarted):
                self.steps[path] = Step(path, e.seq, e.attempt, p)
            elif (step := self.steps.get(path)) is not None:
                if isinstance(p, ev.StepRerun):
                    step.rerun = int(p.reason == "restored")
                elif isinstance(p, ev.StepCompleted | ev.StepFailed | ev.StepReconciled):
                    step.closing, step.closed_at = p, e.seq
        for step in self.steps.values():
            if step.rerun is None and step.began.kind != "block" and any(a < step.seq < b for a, b in cuts):
                step.rerun = 1

    def pending(self) -> list[Step]:
        """The steps in flight: started, not closed, not marked for a rerun, in order of their start."""
        return sorted((s for s in self.steps.values() if s.closing is None and s.rerun is None), key=lambda s: s.seq)

    def writes(self, key: str | None = None, *, live: bool = True) -> list[Step]:
        """The write steps on a model (`key`, or any); `live`: only those a restore did not cut."""
        return [
            s for s in self.steps.values()
            if s.began.effect == "write" and s.began.model_key and key in (None, s.began.model_key)
            and (s.rerun != 1 or not live)
        ]  # fmt: skip

    def written(self) -> list[str]:
        """The keys of the models the run wrote to, sorted (a restore does not make a model unwritten)."""
        return sorted({s.began.model_key for s in self.writes(live=False) if s.began.model_key})

    def lacking(self, key: str) -> list[Step]:
        """The writes a reopened model lacks: made after its last save, before it was bound again (4.5.4)."""
        if key not in self.bound or self.bound[key].reason != "reopened":
            return []
        after = self.saved[key][0] if key in self.saved else 0
        return [s for s in self.writes(key) if after < s.seq < self.bound_at[key]]


class ResumeIndex(ReplayIndex):
    """The replay index of a resume: a step marked for a rerun is recorded but runs again, as the same attempt."""

    def __init__(self, events: Sequence[Event]) -> None:
        """Index `events` and note the steps to run again."""
        super().__init__(events)
        self._again = {s.path: s for s in Fold(events).steps.values() if s.rerun is not None}

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
            return Recorded(step.attempt - 1 + (step.rerun or 0), None)  # `Ctx` runs attempt `attempt + 1`
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
    number: int  # this resume's number: `@resume<number>` names its housekeeping steps
    host: HostPort

    def events(self) -> list[Event]:
        """The journal as it stands, read and verified."""
        with closing(JournalReader(self.run_dir)) as reader:
            return reader.events()

    def note(self, kind: str, key: str, summary: dict[str, JsonValue]) -> None:
        """Journal the housekeeping read `@resume<n>.<kind>.<key>` of a model with its `summary` (never replayed)."""
        path, args = resume_path(self.number, kind, key), {"model_key": key}
        began = {"kind": "read", "name": kind, "args": args, "args_sha256": payload_sha256(args), "effect": "read"}
        self.writer.append(EventType.STEP_STARTED, began | {"model_key": key}, path=path, attempt=1)
        ref = self.store.put("harness.journal_blob/1", {"value": summary}, self.producer()).result_id
        result = ev.StepResult(ref=ref, summary=summary, warnings=[], complete=True)
        self.writer.append(EventType.STEP_COMPLETED, {"result": result.model_dump(mode="json"), "duration_ms": 0},
                           path=path, attempt=1)  # fmt: skip

    def stop(self, detail: str, request_id: str | None = None, reason: _Reason = "needs_reconciliation") -> NoReturn:
        """Journal `run_escalated` and end the resume; the journal is otherwise as it was, so a later resume goes on."""
        escalated = ev.RunEscalated(reason=reason, detail=detail, evidence=[], request_id=request_id)
        self.writer.append(EventType.RUN_ESCALATED, escalated)
        raise Stopped(escalated)

    async def ask(
        self, rid: str, title: str, question: Question, why: str, kind: Kind = "engine.in_flight"
    ) -> tuple[str, str]:
        """Return the option chosen for the choice request `rid` of `kind` and who chose it.

        An answer an earlier resume journaled before it was cut short is read from the journal and is not asked or
        journaled again. Otherwise the request is presented: the run stops while there is no fitting answer (the
        request stays open and is presented again at each resume), and ends as `run_failed` on the choice `abandon`.
        """
        events = self.events()
        given = next(
            (e.payload for e in events if isinstance(e.payload, ev.InputProvided) and e.payload.request_id == rid), None
        )
        if given is None:
            choice, by = await self._answered(events, rid, title, question, why, kind)
        else:
            stored = _STORED.validate_python(self.store.payload(given.answer_ref))
            choice, by = stored["fields"][question.name]["value"], given.by
        if choice == "abandon":
            self.writer.append(EventType.RUN_FAILED, {"reason": "abandoned", "by": by})
            raise Stopped(None)
        return choice, by

    async def _answered(
        self, events: Sequence[Event], rid: str, title: str, question: Question, why: str, kind: Kind
    ) -> tuple[str, str]:
        """Present `rid` and journal the engineer's answer; stops the run while there is none that fits."""
        shown = [Evidence(name="why", label="What was found", text=why)]
        request = build_request(self.ids, rid, kind, title, choice_schema([question], shown))
        if not any(isinstance(e.payload, ev.InputRequested) and e.payload.request_id == rid for e in events):
            asked = {
                "request_id": rid,
                "kind": kind,
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
            self.stop(why, rid, "needs_reconciliation" if kind == "engine.in_flight" else "host_state_mismatch")
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


async def reconcile(rt: Resume, skip: set[str]) -> None:
    """Step 7 of a resume (4.5.1): reconcile every write in flight except on the models in `skip`, then rerun reads."""
    pending = Fold(rt.events()).pending()
    for step in (s for s in pending if s.began.effect == "write" and s.began.model_key not in skip):
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
    if began.kind == "promote":  # never sent to the tool port (spec 11 Q40)
        why = "a file copy has no reconciler"
    elif rt.tool.supports_reconcile(began.name):
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
    if step.began.kind == "promote":
        return await _promoted(rt, step, args)
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


async def _promoted(rt: Resume, step: Step, args: dict[str, JsonValue]) -> ev.StepResult:
    """The result of a promotion found applied (spec 11 Q40): the handle of the working copy's state, no read-back."""
    copy = str(args["copy"])
    instance = await rt.host.locate(copy)
    state = None if instance is None else await rt.host.model_state(copy, instance.instance_id)
    if state is None or not state.loaded:
        rt.stop(f"the promotion at step {step.path} was found applied, but the working copy {copy} is not open")
    handle = ModelHandle(model_key=str(args["model"]), model_id=state.model_id or "", revision=state.revision or 0)
    summary = handle.model_dump(mode="json")
    ref = rt.store.put("harness.journal_blob/1", {"value": summary}, rt.producer()).result_id
    return ev.StepResult(ref=ref, summary=summary, warnings=[], complete=True)


def _nothing(rt: Resume, op: str) -> ev.StepResult:
    """The result of a write found applied that left no result: an empty summary, honestly marked incomplete."""
    ref = rt.store.put("harness.journal_blob/1", {"value": {"op_id": op}}, rt.producer()).result_id
    return ev.StepResult(ref=ref, summary={}, warnings=[], complete=False)
