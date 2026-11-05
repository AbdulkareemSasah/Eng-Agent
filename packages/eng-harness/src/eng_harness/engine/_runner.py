"""The run engine: `Engine.start` and `Engine.resume` (spec 0001 4.4.4, 4.5.1; plan 0001 T9).

Purpose: validate a request, hold the run lock, journal the run header, run the root block (against the replay index at
a resume) and return how it ended. Task T9 builds resume steps 1 to 3 and 9 of spec 4.5.1 and a minimal `ctx.tool`;
steps 4 to 8 (tasks T11b, T13) and the other ctx calls (T10) follow, so the header records no server check yet.
Units: none; durations in ms. Errors: `ContractError`, `RunRefused`, `RunLocked`, `JournalIntegrityError`; a stop of the
block ends the run as `NEEDS_ENGINEER` and is not raised.
"""

import re
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from eng_contract import CONTRACT_VERSION
from eng_contract.canonical import canonical_json, payload_sha256
from eng_contract.envelope import FailureEnvelope, Provenance
from eng_contract.errors import ContractError, ContractWarning, ErrorCode, ErrorDetail
from eng_contract.ids import Clock, IdSource
from eng_contract.refs import Ref, RefString
from eng_contract.store import ResultStore, Workspace
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from eng_harness import __version__, errors
from eng_harness._runlock import RunLock
from eng_harness.block import Registry, WorkflowDef
from eng_harness.ctx import ToolResult
from eng_harness.engine._codec import decode_summary
from eng_harness.engine._replay import ReplayIndex
from eng_harness.engine._steps import op_id, root_scope, step
from eng_harness.journal import Event, EventType, JournalReader, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalPort, BasisPort, CalcPort, HostInstance, HostPort, InputPort, RunClass, ToolPort

_RUN_ID = re.compile(r"^run_[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_TERMINAL = (EventType.RUN_COMPLETED, EventType.RUN_FAILED)
_REASONS = (
    (errors.ReplayDivergence, "replay_divergence"), (errors.NeedsReconciliation, "needs_reconciliation"),
    (errors.BlockRuleViolation, "block_rule_violation"),
)  # fmt: skip
"""The `run_escalated` reason of each stop; a `StepError` leaving the root block is `unhandled_error`."""
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
    """The ports an engine works through (spec 4.8); the decision, progress and run-control ports follow."""

    tool: ToolPort
    host: HostPort
    calc: CalcPort
    basis: BasisPort
    approvals: ApprovalPort
    inputs: InputPort


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


def _tool_result(name: str, done: ev.StepResult) -> ToolResult:
    """The block's view of a journaled result; a live and a replayed result are built alike (AC11)."""
    warnings = tuple(ContractWarning.model_validate(w) for w in done.warnings)
    summary = decode_summary(done.summary)
    return ToolResult(
        tool=name, ref=Ref.model_validate({"$ref": done.ref}), summary=summary, warnings=warnings,
        complete=done.complete, model=None,
    )  # fmt: skip


class _Ctx:
    """The ctx of the root block. Task T9 wires `tool` only; its model handle and retries, and the rest, are T10."""

    def __init__(self, tools: ToolPort, clock: Clock, run_id: str, writer: JournalWriter, index: ReplayIndex) -> None:
        """Serve one run: its tool port, clock, id, journal writer and replay index."""
        self._tools, self._clock, self._run_id, self._writer, self._index = tools, clock, run_id, writer, index

    async def tool(self, name: str, args: Mapping[str, JsonValue] | None = None) -> ToolResult:
        """Call the host tool `name` as one step, or return what the journal recorded for it (spec 4.3.2).

        Raises:
            ToolFailed: a failure envelope, live or recorded. `ContractError`: a tool outside the allowlist.
            ReplayDivergence, NeedsReconciliation: see `ReplayIndex.lookup`.
        """
        arguments = dict(args or {})
        return await step(lambda path: self._tool(path, name, arguments))

    async def _tool(self, path: str, name: str, args: dict[str, JsonValue]) -> ToolResult:
        digest = payload_sha256(args)
        recorded = self._index.lookup(path, "tool", name, digest)
        if recorded is not None and recorded.outcome is not None:  # the step is done: replay it
            if isinstance(recorded.outcome, ev.StepResult):
                return _tool_result(name, recorded.outcome)
            if isinstance(recorded.outcome, ErrorDetail):
                raise errors.ToolFailed(recorded.outcome)
            raise errors.ReplayDivergence(f"step {path} recorded the harness code {recorded.outcome.harness_code}")
        attempt = 1 if recorded is None else recorded.attempt + 1  # a retryable failure runs again, as the next attempt
        info = await self._tools.describe(name)
        op = op_id(self._run_id, path, attempt)
        model = args.get(info.model_param) if info.model_param else None
        key = model if isinstance(model, str) else None
        started = {
            "kind": "tool", "name": name, "args": args, "args_sha256": digest, "effect": info.effect,
            "op_id": op if info.effect == "write" else None, "host_key": info.host_key, "model_key": key,
        }  # fmt: skip
        self._writer.append(EventType.STEP_STARTED, started, path=path, attempt=attempt)
        began = self._clock.now_ms()
        envelope = await self._tools.call(name, args, op_id=op, model=key)
        millis = self._clock.now_ms() - began
        if isinstance(envelope, FailureEnvelope):
            error = envelope.error
            failed = {"error": error.model_dump(mode="json"), "retryable": error.retryable, "duration_ms": millis}
            self._writer.append(EventType.STEP_FAILED, failed, path=path, attempt=attempt)
            raise errors.ToolFailed(error)
        warnings = [w.model_dump(mode="json") for w in envelope.warnings]
        done = ev.StepResult(
            ref=envelope.result_id, summary=envelope.summary, warnings=warnings, complete=envelope.complete
        )
        self._writer.append(
            EventType.STEP_COMPLETED, ev.StepCompleted(result=done, duration_ms=millis), path=path, attempt=attempt
        )
        return _tool_result(name, done)


class Engine:
    """Starts runs and resumes them by replay; an engine holds the lock of one run at a time (spec 4.4.4)."""

    def __init__(
        self, workspace: Workspace, registry: Registry, ports: EnginePorts, store: ResultStore,
        settings: EngineSettings, clock: Clock, ids: IdSource,
    ) -> None:  # fmt: skip
        """Bind the workspace (runs live in `<root>/runs`), the registered workflows, the ports and the sources."""
        self._runs = workspace.root / "runs"
        self._registry, self._ports, self._store, self._clock, self._ids = registry, ports, store, clock, ids
        self._settings_sha256 = payload_sha256(settings.model_dump(mode="json"))

    def _find(self, name: str) -> WorkflowDef[Any, Any] | None:
        return next((b for b in self._registry.blocks if isinstance(b, WorkflowDef) and b.name == name), None)

    def _producer(self) -> Provenance:
        now = self._clock.now()
        return Provenance(tool="harness", tool_version=__version__, inputs={}, started_at=now, duration_ms=0)

    def _check_class(self, recorded: str) -> None:
        """Refuse a calc port whose run class is not the run's (AC65)."""
        if (actual := self._ports.calc.run_class.value) != recorded:
            raise errors.RunRefused(
                errors.HarnessCode.RUN_CLASS_MISMATCH, f"the calc port is {actual}, the run {recorded}"
            )

    async def start(self, request: RunRequest) -> RunOutcome:
        """Validate `request`, create the run, journal its header and run the workflow (spec 4.5.1).

        Raises:
            ContractError: `INVALID_ARGUMENT` for an unregistered workflow or an input that fails its model.
            RunRefused: `RUN_CLASS_MISMATCH`. Neither creates a run folder.
        """
        workflow = self._find(request.workflow)
        if workflow is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"workflow {request.workflow!r} is not registered")
        inp = _parse(workflow.input_model, request.input, "the run input")
        self._check_class(request.run_class.value)
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
                "contract_version": CONTRACT_VERSION, "settings_sha256": self._settings_sha256, "servers": [],
                "always_ask": list(workflow.always_ask), "unreleased_tools": dict(self._ports.tool.unreleased_tools()),
            }  # fmt: skip
            with closing(JournalWriter(run_dir, self._store, self._clock, self._ids)) as writer:
                writer.append(EventType.RUN_STARTED, header)
                return await self._drive(workflow, inp, run_id, writer, ReplayIndex(()))

    async def resume(self, run_id: str) -> RunOutcome:
        """Resume the run (steps 1 to 3 and 9 of spec 4.5.1); an ended run returns its recorded outcome (AC35).

        Raises:
            ContractError: `INVALID_ARGUMENT` for a run id that names no run, or a workflow that is not registered.
            RunLocked: another engine holds the run. RunRefused: `RUN_CLASS_MISMATCH`. Both leave the journal unchanged.
            JournalIntegrityError: the journal fails verification.
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
            with closing(JournalWriter(run_dir, self._store, self._clock, self._ids)) as writer:
                try:
                    workflow, inp = self._admit(head)  # step 3
                except errors.ReplayDivergence as stop:
                    return self._escalate(run_id, writer, stop)
                writer.append(EventType.RUN_RESUMED, self._resumed(workflow, head, events))
                # steps 4 to 8 (preflight, leases, units, reconciliation, host-state check) follow here: tasks T11b, T13
                return await self._drive(workflow, inp, run_id, writer, ReplayIndex(events))  # step 9

    def _admit(self, head: ev.RunHeader) -> tuple[WorkflowDef[Any, Any], BaseModel]:
        """The header against the registry (version rule, input) and the calc port; no port is called (4.5.1 step 3)."""
        workflow = self._find(head.block.name)
        if workflow is None:
            raise errors.ReplayDivergence(f"the block {head.block.name!r} is not registered")
        if str(workflow.version) != head.block.version:
            raise errors.ReplayDivergence(
                f"block {workflow.name} is at version {workflow.version}, the run has {head.block.version}"
            )
        self._check_class(head.run_class)
        value = self._store.payload(head.input_ref)["value"]
        if payload_sha256(value) != head.input_sha256:
            raise errors.ReplayDivergence("the stored run input differs from the hash in the run header")
        try:
            return workflow, _parse(workflow.input_model, value, "the stored run input")
        except ContractError as exc:
            raise errors.ReplayDivergence("the stored run input no longer fits the input model") from exc

    def _resumed(self, workflow: WorkflowDef[Any, Any], head: ev.RunHeader, events: list[Event]) -> dict[str, object]:
        """The `run_resumed` payload; `unreleased_tools` only when it differs from the last recorded mapping (AC68)."""
        recorded = [e.payload.unreleased_tools for e in events if isinstance(e.payload, ev.RunResumed)]
        last = [head.unreleased_tools, *(m for m in recorded if m is not None)][-1]
        payload: dict[str, object] = {
            "resume_no": len(recorded) + 1, "code_hash_changed": workflow.code_sha256 != head.block.code_sha256,
            "servers": [],
        }  # fmt: skip
        if (now := dict(self._ports.tool.unreleased_tools())) != last:
            payload["unreleased_tools"] = now
        return payload

    async def _ended(self, run_id: str, head: ev.RunHeader, events: list[Event], last: object) -> RunOutcome:
        """The recorded outcome of an ended run, after `close_started` for its journaled host instances (AC35)."""
        instances: dict[str, list[HostInstance]] = {}
        for event in events:
            if isinstance(started := event.payload, ev.HostStarted):
                instances.setdefault(started.host_key, []).append(
                    HostInstance.model_validate(started.model_dump(exclude={"host_key"}))
                )
        for host_key, found in instances.items():
            await self._ports.host.close_started(host_key, found)
        if not isinstance(last, ev.RunCompleted):
            return RunOutcome(run_id, RunStatus.FAILED)
        workflow = self._find(head.block.name)
        if workflow is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"workflow {head.block.name!r} is not registered")
        output = _parse(workflow.output_model, self._store.payload(last.output_ref)["value"], "the recorded output")
        return RunOutcome(run_id, RunStatus.COMPLETED, output)

    async def _drive(
        self, workflow: WorkflowDef[Any, Any], inp: BaseModel, run_id: str, writer: JournalWriter, index: ReplayIndex
    ) -> RunOutcome:
        """Run the root block and journal how it ends: `run_completed`, or `run_escalated` for a stop of the block."""
        try:
            with root_scope():
                out = await workflow.fn(_Ctx(self._ports.tool, self._clock, run_id, writer, index), inp)
            if not isinstance(out, workflow.output_model):
                wanted = workflow.output_model.__name__
                raise errors.BlockRuleViolation(f"{workflow.name} returned a {type(out).__name__}, not a {wanted}")
            index.finish()
        except (errors.ReplayDivergence, errors.NeedsReconciliation, errors.BlockRuleViolation,
                errors.StepError) as stop:  # fmt: skip
            return self._escalate(run_id, writer, stop)
        value = out.model_dump(mode="json")
        stored = self._store.put("harness.run_output/1", {"value": value}, self._producer())
        done = {"output_ref": stored.result_id, "output_sha256": payload_sha256(value), "draft": False}
        writer.append(EventType.RUN_COMPLETED, done)
        return RunOutcome(run_id, RunStatus.COMPLETED, out)

    @staticmethod
    def _escalate(run_id: str, writer: JournalWriter, stop: errors.EngineStop | errors.StepError) -> RunOutcome:
        """Journal `run_escalated` for `stop`; the run has not ended, and a resume replays it."""
        reason = next((r for kind, r in _REASONS if isinstance(stop, kind)), "unhandled_error")
        payload = {"reason": reason, "detail": stop.message, "evidence": list(stop.evidence)}
        escalated = ev.RunEscalated.model_validate(payload)
        writer.append(EventType.RUN_ESCALATED, escalated)
        return RunOutcome(run_id, RunStatus.NEEDS_ENGINEER, escalation=escalated)
