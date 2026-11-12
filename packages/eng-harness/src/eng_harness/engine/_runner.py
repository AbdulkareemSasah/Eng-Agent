"""The run engine: `Engine.start` and `Engine.resume` (spec 0001 4.4.4, 4.5.1, 4.5.2; plan 0001 T9, T9b).

Purpose: validate a request, hold the run lock, journal the run header, run the root block and return how it ended.
Resume runs steps 1 to 9 of spec 4.5.1; each host is leased until the engine returns and the host instances the run
started are closed when the run ends (invariant 10); the ctx calls are in `_ctx_impl.py`.
Units: none; durations in ms. Errors: `ContractError`, `RunRefused`, `RunLocked`, `JournalIntegrityError`; a stop of the
block ends the run as `NEEDS_ENGINEER` or `PAUSED` and is not raised.
"""

import re
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from eng_contract import CONTRACT_VERSION
from eng_contract.canonical import canonical_json, payload_sha256
from eng_contract.envelope import Provenance
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import Clock, IdSource
from eng_contract.refs import RefString
from eng_contract.store import ResultStore, Workspace
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from eng_harness import __version__, errors
from eng_harness._runlock import RunLock
from eng_harness.block import Registry, WorkflowDef
from eng_harness.ctx import BasisView
from eng_harness.engine import _decide, _hostsafety, _hoststate, _inflight
from eng_harness.engine._ctx_impl import AttemptsExhausted, Ctx
from eng_harness.engine._steps import root_scope
from eng_harness.journal import Event, EventType, JournalReader, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalPort, BasisPort, CalcPort, DecisionPort, HostPort, InputPort, RunClass, ToolPort

_RUN_ID = re.compile(r"^run_[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_TERMINAL = (EventType.RUN_COMPLETED, EventType.RUN_FAILED)
_Count = Annotated[int, Field(ge=1)]


class PermissionMode(StrEnum):
    """How writes are permitted, chosen per run (spec 4.7); the modes themselves follow in task T16."""

    WORK_ON_COPY = "work_on_copy"
    APPROVE_EACH_WRITE = "approve_each_write"
    AUTONOMOUS_LOGGED = "autonomous_logged"


class RunStatus(StrEnum):
    """How a run ended or where it stands (spec 5)."""

    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    NEEDS_ENGINEER = "NEEDS_ENGINEER"
    FAILED = "FAILED"


class EngineSettings(BaseModel):
    """Software limits of the engine (spec 4.10), not engineering values; each is a count of at least 1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_parallel_children: _Count = 8
    max_concurrent_hosts: _Count = 1
    max_concurrent_decisions: _Count = 4
    max_attempts_cap: _Count = 10
    step_retry_limit: _Count = 2


class RunRequest(BaseModel):
    """A request to start a run (spec 5): `input` is the workflow's input as JSON, `basis_ref` its design basis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow: str
    input: dict[str, JsonValue]
    basis_ref: RefString
    mode: PermissionMode = PermissionMode.WORK_ON_COPY
    run_class: RunClass = RunClass.PRODUCTION


@dataclass(frozen=True)
class RunOutcome:
    """How a run ended: its output when completed, its open request ids when paused, its escalation when stopped."""

    run_id: str
    status: RunStatus
    output: BaseModel | None = None
    pending: tuple[str, ...] = ()
    escalation: ev.RunEscalated | None = None


@dataclass(frozen=True)
class EnginePorts:
    """The ports an engine works through (spec 4.8); the progress and run-control ports follow.

    `decision` is `None` when no cascade is wired: a `decide` or `decide_many` call is then an internal error.
    """

    tool: ToolPort
    host: HostPort
    calc: CalcPort
    basis: BasisPort
    approvals: ApprovalPort
    inputs: InputPort
    decision: DecisionPort | None = None


@contextmanager
def _locked(run_dir: Path) -> Iterator[None]:
    """Hold the run lock of `run_dir` for the body (`RunLocked` when another engine holds it)."""
    lock = RunLock(run_dir)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def _parse[M: BaseModel](model: type[M], value: object, what: str) -> M:
    """Validate the JSON `value` strictly as `model`; `ContractError` `INVALID_ARGUMENT` names the first problem."""
    try:
        return model.model_validate_json(canonical_json(value), strict=True)
    except ValidationError as exc:
        first = exc.errors()[0]
        hint = f"{'.'.join(map(str, first['loc']))}: {first['msg']}"[:2000]
        raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{what} is not a valid {model.__name__}", hint=hint) from exc


class Engine:
    """Starts runs and resumes them by replay; an engine holds the lock of one run at a time (spec 4.4.4)."""

    def __init__(
        self, workspace: Workspace, registry: Registry, ports: EnginePorts, store: ResultStore,
        settings: EngineSettings, clock: Clock, ids: IdSource,
    ) -> None:  # fmt: skip
        """Bind the workspace (runs live in `<root>/runs`), the registered workflows, the ports and the sources."""
        self._runs, self._settings = workspace.root / "runs", settings
        self._registry, self._ports, self._store, self._clock, self._ids = registry, ports, store, clock, ids
        self._settings_sha256 = payload_sha256(settings.model_dump(mode="json"))

    def _find(self, name: str) -> WorkflowDef[Any, Any] | None:
        return next((b for b in self._registry.blocks if isinstance(b, WorkflowDef) and b.name == name), None)

    def _check_class(self, recorded: str) -> None:
        if (actual := self._ports.calc.run_class.value) != recorded:  # AC65
            message = f"the calc port is {actual}, the run {recorded}"
            raise errors.RunRefused(errors.HarnessCode.RUN_CLASS_MISMATCH, message)

    def _producer(self) -> Provenance:
        return Provenance(
            tool="harness", tool_version=__version__, inputs={}, started_at=self._clock.now(), duration_ms=0
        )

    async def start(self, request: RunRequest) -> RunOutcome:
        """Validate `request`, create the run, journal its header and run the workflow (spec 4.5.1).

        Raises:
            ContractError: `INVALID_ARGUMENT` for an unregistered workflow or an input that fails its model.
            RunRefused: `RUN_CLASS_MISMATCH` when the calc port's class is not the request's, `BASIS_INCOMPLETE` when
                the design basis lacks a required field, `SERVER_CHECK_FAILED` when a server check fails (spec 4.6 #5,
                #8). None of them creates a run folder.
            RunLocked: another engine holds the new run's lock.
            ContractError: `HOST_LOCKED` when another driver holds a host the run needs (spec 4.6 #10).
        """
        workflow = self._find(request.workflow)
        if workflow is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"workflow {request.workflow!r} is not registered")
        inp = _parse(workflow.input_model, request.input, "the run input")
        self._check_class(request.run_class.value)
        _hostsafety.check_basis(self._ports.basis, request.basis_ref, workflow.required_basis)
        checks = await _hostsafety.check_servers(self._ports.host, workflow.min_server_builds)
        run_id = f"run_{self._ids.new_ulid()}"
        run_dir = self._runs / run_id
        run_dir.mkdir(parents=True)
        with _locked(run_dir):
            stored = self._store.put("harness.run_input/1", {"value": request.input}, self._producer())
            block = {"name": workflow.name, "version": str(workflow.version), "code_sha256": workflow.code_sha256}
            header = {
                "run_id": run_id, "workflow": workflow.name, "block": block, "mode": request.mode.value,
                "input_ref": stored.result_id, "input_sha256": payload_sha256(request.input),
                "basis_ref": request.basis_ref, "run_class": request.run_class.value, "engine_version": __version__,
                "contract_version": CONTRACT_VERSION, "settings_sha256": self._settings_sha256,
                "servers": [c.model_dump(mode="json") for c in checks],
                "always_ask": list(workflow.always_ask), "unreleased_tools": dict(self._ports.tool.unreleased_tools()),
            }  # fmt: skip
            with closing(JournalWriter(run_dir, self._store, self._clock, self._ids)) as writer:
                writer.append(EventType.RUN_STARTED, header)
                rt, leases = self._hosts(run_id, writer, 0)
                try:
                    return await self._closed(rt, await self._drive(workflow, inp, rt, leases, [], request.basis_ref))
                finally:
                    await leases.release()

    async def resume(self, run_id: str) -> RunOutcome:
        """Resume the run (the nine steps of spec 4.5.1); an ended run returns its recorded outcome (AC35).

        The servers are checked and the hosts leased before anything else is asked of them (steps 4 and 5). A write in
        flight is reconciled, a read in flight gets `step_rerun` and the host state of each written model is checked
        before the block runs; a stop for the engineer returns `NEEDS_ENGINEER`, an abandoned run `FAILED`.

        Raises:
            ContractError: `INVALID_ARGUMENT` for a run id that names no run, or a workflow that is not registered;
                `HOST_LOCKED` when another driver holds a host.
            RunLocked, RunRefused (`RUN_CLASS_MISMATCH`): the journal is left as it was.
            RunRefused (`SERVER_CHECK_FAILED`): like `HOST_LOCKED`, it comes after `run_resumed` (step 3), so a write in
                flight stays in flight and `run_resumed` is the only event added.
            JournalIntegrityError.
        """
        run_dir = self._runs / run_id
        if not _RUN_ID.fullmatch(run_id) or not run_dir.is_dir():
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"no run {run_id!r}", received=run_id)
        with _locked(run_dir):  # step 1
            with closing(JournalReader(run_dir)) as reader:  # step 2
                events = reader.events()
            head = events[0].payload if events else None
            if not isinstance(head, ev.RunHeader):
                raise errors.JournalIntegrityError("journal has no run_started event")
            if (ended := next((e for e in events if e.type in _TERMINAL), None)) is not None:
                return await self._ended(run_id, head, events, ended.payload)
            self._check_class(head.run_class)  # step 3
            with closing(JournalWriter(run_dir, self._store, self._clock, self._ids)) as writer:
                try:
                    workflow, inp = self._admit(head)
                except errors.ReplayDivergence as stop:
                    return self._escalate(run_id, writer, "replay_divergence", stop)
                resumed = self._resumed(workflow, head, events)
                writer.append(EventType.RUN_RESUMED, resumed)
                rt, leases = self._hosts(run_id, writer, resumed.resume_no)
                try:
                    try:  # step 6 only for the models the run wrote; 7 and 8: spec 4.5.3, 4.5.4
                        await _hostsafety.check_servers(rt.host, workflow.min_server_builds, always=True)  # step 4
                        await leases.resume()  # step 5
                        await _inflight.reconcile(rt, await _hoststate.locate_models(rt))
                        await _hoststate.check(rt)
                    except _inflight.Stopped as stop:  # an escalation is journaled; an abandoned run has ended
                        status = RunStatus.NEEDS_ENGINEER if stop.escalated else RunStatus.FAILED
                        return await self._closed(rt, RunOutcome(run_id, status, escalation=stop.escalated))
                    return await self._closed(
                        rt, await self._drive(workflow, inp, rt, leases, rt.events(), head.basis_ref)
                    )  # step 9
                finally:
                    await leases.release()

    def _admit(self, head: ev.RunHeader) -> tuple[WorkflowDef[Any, Any], BaseModel]:
        """The header against the registry (version rule) and the stored input against its model (4.2, 4.5.1 step 3)."""
        workflow = self._find(head.block.name)
        if workflow is None or str(workflow.version) != head.block.version:
            raise errors.ReplayDivergence(
                f"the registry has no block {head.block.name!r} at version {head.block.version}"
            )
        value = self._store.payload(head.input_ref)["value"]
        if payload_sha256(value) != head.input_sha256:
            raise errors.ReplayDivergence("the stored run input differs from the hash in the run header")
        try:
            return workflow, _parse(workflow.input_model, value, "the stored run input")
        except ContractError as exc:
            raise errors.ReplayDivergence("the stored run input no longer fits the input model") from exc

    def _resumed(self, workflow: WorkflowDef[Any, Any], head: ev.RunHeader, events: list[Event]) -> ev.RunResumed:
        """The `run_resumed` payload; `unreleased_tools` only when it differs from the last recorded mapping (AC68)."""
        seen = [e.payload for e in events if isinstance(e.payload, ev.RunResumed)]
        last = [head.unreleased_tools, *(p.unreleased_tools for p in seen if p.unreleased_tools is not None)][-1]
        changed = workflow.code_sha256 != head.block.code_sha256  # a warning, not a divergence (AC29)
        number = max((p.resume_no for p in seen), default=0) + 1  # a restore adds a second event with the same number
        now: dict[str, JsonValue] = dict(self._ports.tool.unreleased_tools())
        return ev.RunResumed(
            resume_no=number, code_hash_changed=changed, servers=[], unreleased_tools=now if now != last else None
        )

    async def _ended(self, run_id: str, head: ev.RunHeader, events: list[Event], last: object) -> RunOutcome:
        """The recorded outcome of an ended run, after `close_started` for its journaled host instances (AC35)."""
        outcome = RunOutcome(run_id, RunStatus.FAILED)
        if isinstance(last, ev.RunCompleted):
            if (workflow := self._find(head.block.name)) is None:
                raise ContractError(ErrorCode.INVALID_ARGUMENT, f"workflow {head.block.name!r} is not registered")
            value = self._store.payload(last.output_ref)["value"]
            output = _parse(workflow.output_model, value, "the recorded output")
            outcome = RunOutcome(run_id, RunStatus.COMPLETED, output)
        await _hostsafety.close_started(self._ports.host, events)
        return outcome

    def _hosts(self, run_id: str, writer: JournalWriter, number: int) -> tuple[_inflight.Resume, _hostsafety.Leases]:
        """The resume state of a run (its `@resume<number>` steps) and the host leases it will hold (spec 4.6 #10)."""
        ports = self._ports
        rt = _inflight.Resume(
            self._runs / run_id, run_id, ports.tool, ports.inputs, self._store, self._clock, self._ids, self._producer,
            writer, number, ports.host,
        )  # fmt: skip
        return rt, _hostsafety.Leases(rt)

    @staticmethod
    async def _closed(rt: _inflight.Resume, outcome: RunOutcome) -> RunOutcome:
        """Pass the journaled host instances to `close_started` once the run has ended: `run_completed` or
        `run_failed` is appended, which only `COMPLETED` and `FAILED` outcomes follow; never after a pause, an
        escalation, a divergence or a refusal (spec 4.6 #10)."""
        if outcome.status in (RunStatus.COMPLETED, RunStatus.FAILED):
            await _hostsafety.close_started(rt.host, rt.events())
        return outcome

    async def _drive(
        self, workflow: WorkflowDef[Any, Any], inp: BaseModel, rt: _inflight.Resume, leases: _hostsafety.Leases,
        events: list[Event], basis_ref: str,
    ) -> RunOutcome:  # fmt: skip
        """Run the root block and journal how it ends: `run_completed`, `run_paused` or `run_escalated`."""
        ports, run_id, writer = self._ports, rt.run_id, rt.writer

        def view() -> BasisView:  # loaded when the first decision needs it
            loaded = ports.basis.load(basis_ref)
            return BasisView(loaded.result_id, loaded.basis, workflow.required_basis)

        decider = _decide.Decider(
            ports.decision, ports.inputs, view, rt.events, writer, self._clock, self._ids, run_id, events
        )
        ctx = Ctx(
            ports.tool, ports.calc, ports.host, self._store, self._settings, self._clock, self._producer, run_id,
            writer, events, _hostsafety.Pending(rt), leases, decider,
        )  # fmt: skip
        ctx.index = _inflight.ResumeIndex(events)
        try:
            with root_scope():
                out = await workflow.fn(ctx, inp)
                await ctx.finish()  # ~end checks for models the root block left dirty (spec 4.6 #1)
            if not isinstance(out, workflow.output_model):
                wanted = workflow.output_model.__name__
                raise errors.BlockRuleViolation(f"{workflow.name} returned a {type(out).__name__}, not a {wanted}")
            ctx.index.finish()
        except errors.Pause as pause:  # the request ids are the evidence
            reason = "awaiting_input" if isinstance(pause, _decide.AwaitingInput) else "awaiting_approval"
            writer.append(EventType.RUN_PAUSED, {"reason": reason, "request_ids": list(pause.evidence)})
            return RunOutcome(run_id, RunStatus.PAUSED, pending=pause.evidence)
        except _inflight.Stopped as stop:  # a write of unknown outcome: escalated for the engineer, or abandoned
            status = RunStatus.NEEDS_ENGINEER if stop.escalated else RunStatus.FAILED
            return RunOutcome(run_id, status, escalation=stop.escalated)
        except errors.Escalation as stop:
            reason = "attempts_exhausted" if isinstance(stop, AttemptsExhausted) else "block_escalation"
            return self._escalate(run_id, writer, reason, stop)
        except (errors.ReplayDivergence, errors.NeedsReconciliation) as stop:  # the reason is the lowercase code
            return self._escalate(run_id, writer, stop.code.value.lower(), stop)
        except errors.BlockRuleViolation as stop:
            return self._escalate(run_id, writer, "block_rule_violation", stop)
        except errors.StepError as stop:  # a failure that left the root block
            return self._escalate(run_id, writer, "unhandled_error", stop)
        value = out.model_dump(mode="json")
        stored = self._store.put("harness.run_output/1", {"value": value}, self._producer())
        done = {"output_ref": stored.result_id, "output_sha256": payload_sha256(value), "draft": ctx.draft}
        writer.append(EventType.RUN_COMPLETED, done)
        return RunOutcome(run_id, RunStatus.COMPLETED, out)

    @staticmethod
    def _escalate(
        run_id: str, writer: JournalWriter, reason: str, stop: errors.EngineStop | errors.StepError
    ) -> RunOutcome:
        """Journal `run_escalated` for `stop`; the run has not ended, and a resume replays it."""
        payload = {"reason": reason, "detail": stop.message, "evidence": list(stop.evidence)}
        escalated = ev.RunEscalated.model_validate(payload)
        writer.append(EventType.RUN_ESCALATED, escalated)
        return RunOutcome(run_id, RunStatus.NEEDS_ENGINEER, escalation=escalated)
