"""The ctx of a running block: tool, read, calc, decide, block, parallel, attempts, escalate (spec 0001 4.3.2, 4.3.3).

Purpose: each call is a step with a path, matched with the replay index and journaled around its work; a recorded step
returns its recorded result, or raises its recorded failure again, with no port call. Units: none. Errors: `ToolFailed`
(a failure envelope or a `REF_*` error), `CalcRefused`, `DecisionInvalid`, `BlockRuleViolation`, `Escalation`;
`ContractError` if unknown.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Any, NoReturn, cast

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Envelope, FailureEnvelope, Provenance, SuccessEnvelope
from eng_contract.errors import RETRY_RULES, ContractError, ContractWarning, ErrorCode, ErrorDetail, RetryRule
from eng_contract.ids import Clock
from eng_contract.refs import Ref, RefRule, resolve_ref
from eng_contract.store import ResultStore
from pydantic import BaseModel, JsonValue

from eng_harness import errors
from eng_harness.block import BlockDef
from eng_harness.calc import CalcStatus
from eng_harness.ctx import (
    Answered,
    ArgValue,
    Attempt,
    BasisCount,
    CalcResult,
    Decision,
    DecisionRequest,
    ReadResult,
    ToolResult,
)  # fmt: skip
from eng_harness.engine import _decide, _steps
from eng_harness.engine._codec import decode, decode_summary
from eng_harness.engine._invariants import Guard, SiblingBoard
from eng_harness.engine._replay import Recorded, ReplayIndex
from eng_harness.journal import Event, EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import CalcPort, HostPort, ToolPort

if TYPE_CHECKING:
    from eng_harness.engine._hostsafety import Leases, Pending
    from eng_harness.engine._runner import EngineSettings

_LOG = logging.getLogger(__name__)
_RETRIED = (RetryRule.always, RetryRule.depends)  # `after_wedge_clears` and `reconcile_first` go through 4.5.3
_DRAFT = (CalcStatus.DRAFT, CalcStatus.VERIFIED)
_REFUSALS = (errors.HarnessCode.CALC_NOT_APPROVED, errors.HarnessCode.CALC_WITHDRAWN)
_UNKNOWN = (ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, ErrorCode.HOST_WEDGED)  # a write's outcome is unknown (spec 4.6 #6)
_TIMEOUTS = (ErrorCode.TIMEOUT_NO_EFFECT, *_UNKNOWN)  # the timeouts after which the units are read again (spec 4.6 #9)
_Obj = dict[str, JsonValue]
_Pair = tuple[str, str]


class AttemptsExhausted(errors.Escalation):
    """Every iteration of a `ctx.attempts` loop ran without `break` (journaled as `attempts_exhausted`)."""


def _json(value: object) -> JsonValue:
    """The JSON form of an argument: a result or reference is sent as its `$ref` object, an enum as its value."""
    if isinstance(value, Ref):
        return {"$ref": value.ref}
    if isinstance(value, ToolResult | CalcResult | ReadResult):
        return {"$ref": value.ref.ref}
    if isinstance(value, StrEnum):
        return str(value.value)
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_json(item) for item in value]
    if value is None or isinstance(value, str | bool | int | float):
        return value
    raise errors.BlockRuleViolation(f"an argument of type {type(value).__name__} is not an ArgValue")


def _stored(e: SuccessEnvelope) -> ev.StepResult:
    warned = [w.model_dump(mode="json") for w in e.warnings]
    return ev.StepResult(ref=e.result_id, summary=e.summary, warnings=warned, complete=e.complete)


def _result(name: str, done: ev.StepResult) -> ToolResult:
    """The block's view of a journaled result; a live and a replayed result are built alike (AC11)."""
    return ToolResult(
        tool=name, ref=Ref.model_validate({"$ref": done.ref}), summary=decode_summary(done.summary),
        warnings=tuple(ContractWarning.model_validate(w) for w in done.warnings), complete=done.complete, model=None,
    )  # fmt: skip


class _Attempts(_steps.AttemptIterator):
    """The iterator of `ctx.attempts`: the end of the loop without `break` escalates instead of ending quietly."""

    async def __anext__(self) -> Attempt:
        try:
            return await super().__anext__()
        except StopAsyncIteration:
            raise AttemptsExhausted(f"the attempts at step {self.path} are exhausted") from None


class Ctx:
    """The ctx one run hands to its blocks; `draft` turns true when a draft or verified calc ran (AC13)."""

    def __init__(
        self, tools: ToolPort, calc: CalcPort, host: HostPort, store: ResultStore, settings: EngineSettings,
        clock: Clock, producer: Callable[[], Provenance], run_id: str, writer: JournalWriter, events: Sequence[Event],
        pending: Pending, leases: Leases, decider: _decide.Decider,
    ) -> None:  # fmt: skip
        """Serve one run: its ports, store, settings, clock, run id, journal writer, events to replay, pending hosts,
        host leases and decisions."""
        self._tools, self._calc, self._store, self._settings, self._clock = tools, calc, store, settings, clock
        self._pending, self._leases, self._decider = pending, leases, decider
        self._producer, self._run_id, self._writer, self.index = producer, run_id, writer, ReplayIndex(events)
        self._guard = Guard(host, store, writer, producer)
        self._guard.install()
        self._started = {e.path: e.payload for e in events if isinstance(e.payload, ev.StepStarted) and e.path}
        done = [(e.path, e.payload.calc) for e in events if isinstance(e.payload, ev.StepCompleted) and e.payload.calc]
        self._calcs, self.draft = dict(done), False  # the calc of each completed calc step, for its replay

    def _begin(self, path: str, attempt: int, kind: str, name: str, args: _Obj, **fields: object) -> int:
        started = {"kind": kind, "name": name, "args": args, "args_sha256": payload_sha256(args), "effect": "none"}
        self._writer.append(EventType.STEP_STARTED, started | fields, path=path, attempt=attempt)
        return self._clock.now_ms()

    def _end(self, path: str, attempt: int, began: int, kind: EventType, **fields: object) -> None:
        payload = {"duration_ms": self._clock.now_ms() - began, **fields}
        self._writer.append(kind, payload, path=path, attempt=attempt)

    def _done(self, path: str, attempt: int, began: int, done: ev.StepResult, **fields: object) -> None:
        self._end(path, attempt, began, EventType.STEP_COMPLETED, result=done.model_dump(mode="json"), **fields)

    def _fail(self, path: str, attempt: int, began: int, error: ErrorDetail | ev.HarnessError, retry: bool) -> None:
        self._end(path, attempt, began, EventType.STEP_FAILED, error=error.model_dump(mode="json"), retryable=retry)

    @staticmethod
    def _replayed(recorded: Recorded, *, calc: bool = False) -> ev.StepResult | None:
        """The recorded result of a finished step; a recorded failure is raised again; None: the step runs again."""
        done = recorded.outcome
        if isinstance(done, ErrorDetail):
            raise errors.ToolFailed(done)
        if isinstance(done, ev.HarnessError):
            if calc and done.harness_code in _REFUSALS:
                raise errors.CalcRefused(done.harness_code, done.message)
            if done.harness_code is errors.HarnessCode.MODEL_INTEGRITY:
                raise errors.ModelIntegrityError(done.message)
            if done.harness_code is errors.HarnessCode.DECISION_INVALID:
                raise errors.DecisionInvalid(done.message)
            raise errors.ReplayDivergence(f"a step recorded the harness code {done.harness_code}")
        return done

    async def tool(self, name: str, args: Mapping[str, ArgValue] | None = None) -> ToolResult:
        """Call the host tool `name` as one step, or return what the journal recorded for it (spec 4.3.2, 4.3.3).

        A read that fails with a retryable code is called again as the next attempt, at most `step_retry_limit`
        times. A write whose call raises, returns `TIMEOUT_UNKNOWN_OUTCOME` or returns `HOST_WEDGED` is reconciled at
        once, before any further step on its host (spec 4.5.3, 4.6 #6): `applied` returns its result, `not_applied`
        runs it again as the next attempt; no other write failure is retried in the run.

        Raises:
            ToolFailed: a failure envelope. `ContractError`: a tool outside the allowlist.
            BlockRuleViolation: an argument that is no `ArgValue`. ReplayDivergence, NeedsReconciliation: see
                `ReplayIndex.lookup`. A read whose port raises leaves the step in flight (task T11b). Stopped: the
                engineer must decide a write of unknown outcome, or abandoned the run.
        """
        raw = dict(args or {})
        return await _steps.step(lambda path: self._tool(path, name, raw))

    async def _tool(self, path: str, name: str, raw: Mapping[str, ArgValue]) -> ToolResult:
        try:
            args = cast(_Obj, _json(raw))
        except errors.BlockRuleViolation:
            info = await self._tools.describe(name)  # a Quantity is not JSON; refuse it before the port call
            self._guard.literals(raw, info.engineering_params)
            args = cast(_Obj, _json(raw))
        return await self._tool_json(path, name, raw, args)

    async def _tool_json(self, path: str, name: str, raw: Mapping[str, ArgValue], args: _Obj) -> ToolResult:
        recorded = self._look(path, "tool", name, args)
        prior = self._started.get(path)
        if prior is not None:  # a recorded step: replay its inserted steps, and do not call describe
            self._pending.replay(self, path, prior.model_key)
            await self._guard.touch(prior.model_key, prior.effect == "write")
            await self._guard.prepare(self, path, prior.model_key, prior.effect, prior.action)
            if recorded is not None and (done := self._replayed(recorded)) is not None:
                if prior.effect == "write":
                    self._guard.mark(prior.model_key)
                    self._guard.note_stored(done.ref)
                return _result(name, done)
        attempt = 1 if recorded is None else recorded.attempt + 1  # a retryable failure runs again as the next attempt
        info = await self._tools.describe(name)
        await self._leases.acquire(info.host_key)  # one driver per host: leased before the first step on it (4.6 #10)
        model = args.get(info.model_param) if info.model_param else None
        key = model if isinstance(model, str) else None
        if prior is None:  # the first live attempt; a retry already prepared above
            self._guard.literals(raw, info.engineering_params)
            await self._guard.touch(key, info.effect == "write")
            await self._pending.bind(
                self, path, key, info
            )  # the model is bound and its units read before its first step
            await self._guard.prepare(self, path, key, info.effect, info.action)
        last = attempt + (self._settings.step_retry_limit if info.effect == "read" else 0)
        while True:
            await self._pending.reconnected(self, path, attempt, info.host_key)  # units after a new session (4.6 #9)
            await self._pending.settle(info.host_key)  # a write of unknown outcome on this host is reconciled first
            op = _steps.op_id(self._run_id, path, attempt)
            fields = {
                "effect": info.effect, "op_id": op if info.effect == "write" else None, "host_key": info.host_key,
                "action": info.action,
            }  # fmt: skip
            began = self._begin(path, attempt, "tool", name, args, model_key=key, **fields)
            try:
                envelope: Envelope | None = await self._tools.call(name, args, op_id=op, model=key)
            except Exception as exc:  # a write that raised is in flight (spec 4.5.3); a read leaves the step as it is
                if info.effect != "write":
                    await self._leases.started(info.host_key)  # the raised read may have started an instance (4.6 #10)
                    raise
                _LOG.warning("the write at step %s raised, so its outcome is unknown: %r", path, exc)
                envelope = None
            await self._leases.started(info.host_key)  # an instance the call started is journaled before the next step
            if isinstance(envelope, SuccessEnvelope):
                self._done(path, attempt, began, done := _stored(envelope))
                self._guard.note(envelope.provenance.host)
                if info.effect == "write":
                    self._guard.mark(key)
                await self._pending.bind(self, path, key, info, after=True)  # an `open` tool binds its model after it
                return _result(name, done)
            if envelope is None or envelope.error.code in _TIMEOUTS:
                self._pending.timed_out(info.host_key)  # read or write: the units are read before the next step
            if envelope is None or (info.effect == "write" and envelope.error.code in _UNKNOWN):
                await self._pending.reconnected(self, path, attempt, info.host_key)  # before 4.5.3 runs
                found = await self._pending.resolve(info.host_key, path, attempt)
                if found.result is not None:  # applied: the block gets the reconciled result, and it is not sent again
                    self._guard.mark(key)
                    self._guard.note_stored(found.result.ref)
                    return _result(name, found.result)
                attempt += 1  # not applied: the step runs again as the next attempt, with a new op_id (ADR-0030)
                continue
            error = envelope.error
            self._fail(path, attempt, began, error, error.retryable)
            if attempt >= last or not error.retryable or RETRY_RULES[error.code] not in _RETRIED:
                raise errors.ToolFailed(error)
            attempt += 1

    def _look(self, path: str, kind: str, name: str, args: _Obj, child: _Pair | None = None) -> Recorded | None:
        return self.index.lookup(path, kind, name, payload_sha256(args), child)

    async def read(self, ref: Ref | ToolResult | CalcResult, pointer: str = "") -> ReadResult:
        """Read the value at `pointer` (added to the one in `ref`) of a stored result as one step.

        The journal records the kind, not the value: a replay reads the immutable result again.

        Raises:
            ToolFailed: the contract `REF_*` code of a malformed or unknown reference or pointer.
        """
        base = (ref if isinstance(ref, Ref) else ref.ref).ref
        target = base + (pointer if "#" in base or not pointer else "#" + pointer)
        return await _steps.step(lambda path: self._read(path, target))

    def _resolve(self, target: str) -> ReadResult:
        found = resolve_ref(target, RefRule(), self._store, lambda _model: None)
        return ReadResult(ref=Ref.model_validate({"$ref": target}), kind=found.record_kind, value=decode(found.value))

    async def _read(self, path: str, target: str) -> ReadResult:
        args: _Obj = {"ref": target}
        recorded = self._look(path, "read", "read", args)
        if recorded is not None and self._replayed(recorded) is not None:
            return self._resolve(target)
        began = self._begin(path, 1, "read", "read", args)
        try:
            read = self._resolve(target)
        except ContractError as exc:
            self._fail(path, 1, began, exc.detail, exc.detail.retryable)
            raise errors.ToolFailed(exc.detail) from exc
        self._done(path, 1, began, ev.StepResult(ref=target, summary={"kind": read.kind}, warnings=[], complete=True))
        return read

    async def calc(self, calc_id: str, args: Mapping[str, ArgValue] | None = None) -> CalcResult:
        """Run the calc `calc_id` as one step; a draft or verified calc marks the run's outputs DRAFT (AC13).

        Raises:
            CalcRefused: `CALC_NOT_APPROVED` or `CALC_WITHDRAWN`. ToolFailed: a failure envelope.
            ContractError: an unknown calc.
        """
        raw = dict(args or {})
        return await _steps.step(lambda path: self._calc_step(path, calc_id, raw, cast(_Obj, _json(raw))))

    async def _calc_step(self, path: str, calc_id: str, raw: Mapping[str, ArgValue], args: _Obj) -> CalcResult:
        recorded = self._look(path, "calc", calc_id, args)
        await self._guard.sweep(self, path, "pre")  # any calc waits for the dirty models to be checked (spec 4.6 #1)
        if recorded is not None and (done := self._replayed(recorded, calc=True)) is not None:
            return self._calc_result(calc_id, self._calcs.get(path), done)
        attempt = 1 if recorded is None else recorded.attempt + 1
        info = self._calc.describe(calc_id)
        self._guard.literals(raw, info.engineering_params)
        self._guard.refs(raw, info.ref_rules)
        began = self._begin(path, attempt, "calc", calc_id, args)
        try:
            envelope = self._calc.run(calc_id, args)
        except errors.CalcRefused as refused:
            refusal = ev.HarnessError(harness_code=errors.HarnessCode(refused.code), message=refused.message)
            self._fail(path, attempt, began, refusal, False)
            raise
        if isinstance(envelope, FailureEnvelope):
            self._fail(path, attempt, began, envelope.error, envelope.error.retryable)
            raise errors.ToolFailed(envelope.error)
        ref = ev.CalcRef(id=info.id, version=str(info.version), content_sha256=info.content_sha256, status=info.status)
        self._done(path, attempt, began, done := _stored(envelope), calc=ref.model_dump(mode="json"))
        return self._calc_result(calc_id, ref, done)

    def _calc_result(self, calc_id: str, ref: ev.CalcRef | None, done: ev.StepResult) -> CalcResult:
        if ref is None:
            raise errors.JournalIntegrityError(f"the calc step of {calc_id} has no calc record")
        status, stored = CalcStatus(ref.status), _result(calc_id, done)
        self.draft = self.draft or status in _DRAFT
        return CalcResult(
            calc_id=calc_id, calc_version=int(ref.version), status=status, ref=stored.ref, summary=stored.summary,
            draft=status in _DRAFT,
        )  # fmt: skip

    async def decide(
        self, question: str, options: object, state: BaseModel, rules: Sequence[object], policy: object
    ) -> Decision[Any]:
        """Decide `question` over the DecisionPort as one step: rules, providers, then the engineer (AC40, AC66).

        The block gets a member or a reference, never a number; when the engineer must choose, the run pauses.

        Raises:
            BlockRuleViolation: bad options, state, rules, policy or point. DecisionInvalid: the answer is none of the
                options. ContractError: a stale reference, or no port.
        """
        request = DecisionRequest(question, options, state, rules, policy)
        return (await _steps.step(lambda path: self._decided(path, "decide", question, [request])))[0]

    async def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision[Any]]:
        """Decide the requests as one step; the calls the engineer must choose are one input request (AC66)."""
        return await _steps.step(lambda path: self._decided(path, "decide_many", "decide_many", list(requests)))

    async def _decided(self, path: str, kind: str, name: str, requests: list[DecisionRequest]) -> list[Decision[Any]]:
        items = [_decide.check(r) for r in requests]
        args = _decide.arguments(items)
        recorded = self._look(path, kind, name, args)
        await self._guard.sweep(self, path, "pre")  # a decision waits for the dirty models to be checked (spec 4.6 #1)
        if recorded is not None and (done := self._replayed(recorded)) is not None:
            return _decide.decisions(items, cast(list[_Obj], done.summary["decisions"]))
        self._guard.refs(_decide.held(items), {})  # invariant 3: the default rule for every reference
        began = self._clock.now_ms()
        try:
            settled = await self._decider.settle(path, items, many=kind == "decide_many")
            value: list[JsonValue] = [
                {"choice": a.choice, "decided_by": a.decided_by, "confidence": a.confidence} for _, a, _ in settled
            ]
            out = _decide.decisions(items, cast(list[_Obj], value))
        except errors.DecisionInvalid as invalid:
            self._begin(path, 1, kind, name, args)
            self._fail(
                path,
                1,
                began,
                ev.HarnessError(harness_code=errors.HarnessCode.DECISION_INVALID, message=invalid.message),
                False,
            )
            raise
        self._begin(path, 1, kind, name, args)
        for call, answer, request_id in settled:
            self._writer.append(EventType.DECISION_MADE, _decide.made(call, answer, request_id), path=path, attempt=1)
        stored = self._store.put("harness.journal_blob/1", {"value": value}, self._producer())
        result = ev.StepResult(ref=stored.result_id, summary={"decisions": value}, warnings=[], complete=True)
        self._done(path, 1, began, result)
        return out

    async def ask[M: BaseModel](self, fields: type[M], *, title: str) -> Answered[M]:
        """Ask the engineer for the values of `fields` as one step; the run pauses until a valid answer is given.

        The answer is stored as a `basis.engineer_input/1` result (AC61) and replayed from the journal.

        Raises:
            BlockRuleViolation: `fields` is not a Pydantic model. AwaitingInput: no answer fits `fields` yet.
        """
        if not (isinstance(fields, type) and issubclass(fields, BaseModel)):
            raise errors.BlockRuleViolation("the fields of ctx.ask must be a Pydantic model")
        return await _steps.step(lambda path: self._asked(path, fields, title))

    async def _asked[M: BaseModel](self, path: str, fields: type[M], title: str) -> Answered[M]:
        args: _Obj = {"title": title, "fields": fields.model_json_schema()}
        recorded = self._look(path, "ask", fields.__name__, args)
        await self._guard.sweep(self, path, "pre")  # like a decision, an ask waits for the dirty models to be checked
        if recorded is not None and (done := self._replayed(recorded)) is not None:
            kept = cast("dict[str, Any]", self._store.payload(done.ref))
            value = fields.model_validate({name: item["value"] for name, item in kept["fields"].items()})
            return Answered(value=value, ref=Ref.model_validate({"$ref": done.ref}))
        answer, given = await self._decider.asked(path, title, fields)
        who = answer.by.removeprefix("engineer:")
        entered = {"unit": None, "entered_by": who, "entered_at": self._clock.now()}
        held: _Obj = {name: {"value": item, **entered} for name, item in given.model_dump(mode="json").items()}
        stored = self._store.put(
            "basis.engineer_input/1", {"step": path, "fields": held}, self._producer()
        )
        by = "engineer:" + who
        self._writer.append(
            EventType.INPUT_PROVIDED, {"request_id": answer.request_id, "answer_ref": stored.result_id, "by": by}
        )
        began = self._begin(path, 1, "ask", fields.__name__, args)
        self._done(path, 1, began, ev.StepResult(ref=stored.result_id, summary={}, warnings=[], complete=True))
        return Answered(value=cast(M, given), ref=Ref.model_validate({"$ref": stored.result_id}))

    async def block[I: BaseModel, O: BaseModel](self, child: BlockDef[I, O], inp: I) -> O:
        """Run `child` as a scope: its steps are `<path>/0`, `<path>/1`; input and output are checked (AC15).

        Raises:
            BlockRuleViolation: `inp` is no instance of the child's input model, or the child returned no instance of
                its output model.
        """
        if not isinstance(inp, child.input_model):
            raise errors.BlockRuleViolation(f"{child.name} takes a {child.input_model.__name__}")
        return await _steps.block_step(lambda path: self._block(path, child, inp))

    async def _block[I: BaseModel, O: BaseModel](self, path: str, child: BlockDef[I, O], inp: I) -> O:
        args: _Obj = inp.model_dump(mode="json")
        ref = ev.BlockRef(name=child.name, version=str(child.version), code_sha256=child.code_sha256)
        begun = done = False
        try:  # a scope: its children replay one by one, so only the record of the step itself is matched
            done = begun = self._look(path, "block", child.name, args, (ref.name, ref.version)) is not None
        except errors.NeedsReconciliation:  # entered, not completed
            begun = True
        began = self._clock.now_ms() if begun else self._begin(path, 1, "block", ref.name, args, child=ref.model_dump())
        out = await child.fn(self, inp)
        await self._guard.sweep(self, path, "end")  # the child block's return checks the models it left dirty
        if not isinstance(out, child.output_model):
            raise errors.BlockRuleViolation(f"{child.name} did not return a {child.output_model.__name__}")
        if not done:
            stored = self._store.put("harness.run_output/1", {"value": out.model_dump(mode="json")}, self._producer())
            result = ev.StepResult(ref=stored.result_id, summary={}, warnings=[], complete=True)
            self._done(path, 1, began, result, output_ref=stored.result_id)
        return out

    async def parallel[T](self, *steps: Awaitable[T]) -> list[T]:
        """Run the steps concurrently, child `i` in scope `<path>/i`; results come in argument order (AC5, AC8)."""
        board = SiblingBoard()

        async def before(path: str) -> None:
            await self._guard.sweep(self, path, "pre")  # children read no model the parent left dirty (spec 4.3.1)

        async def after(path: str, models: Sequence[str]) -> None:
            for model in models:
                await self._guard.check(self, path, "post", model)

        return await _steps.parallel(
            steps, before=before, after=after, enter=lambda index: self._guard.enter(board, index),
            leave=self._guard.dirty_models,
        )  # fmt: skip

    async def finish(self) -> None:
        """`~end` checks after the root returns; an early end diverges before a live check (spec 4.5.2, 4.6 #1)."""
        await self._guard.sweep(self, "", "end", live=False)
        try:
            self.index.finish()
        except errors.ReplayDivergence:
            return
        await self._guard.sweep(self, "", "end")

    def attempts(self, limit: BasisCount) -> _Attempts:
        """Iterate at most `limit` times, iteration `i` in scope `<path>/i`; use `async for` and `break` on success.

        Raises:
            BlockRuleViolation: `limit` is no `BasisCount`, is zero or exceeds `max_attempts_cap` (AC9).
            Escalation: raised by the loop when every iteration ran without `break`.
        """
        if not isinstance(limit, BasisCount) or not 1 <= limit <= self._settings.max_attempts_cap:
            raise errors.BlockRuleViolation(f"attempts takes a BasisCount from 1 to {self._settings.max_attempts_cap}")
        return _Attempts(limit)

    async def escalate(self, reason: str, evidence: Sequence[Ref]) -> NoReturn:
        """Stop the block: the run needs an engineer (`run_escalated`, reason `block_escalation`, AC14)."""
        raise errors.Escalation(reason, evidence=[ref.ref for ref in evidence])
