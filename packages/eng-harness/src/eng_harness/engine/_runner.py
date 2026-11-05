"""The run engine: `Engine.start` (spec 0001 4.4.4, 4.5.1; plan 0001 T9).

Purpose: validate a request, hold the run lock, journal the run header, run the root block and return how it ended.
Task T9 builds `start` and a minimal `ctx.tool` (live, with no retry, approval or model handle). Resume and the replay
index follow in task T9b, the other ctx calls in T10, and the basis, server and host checks in T11b and T13, so the
header records no server check yet and a finished run is never a draft.
Units: none; durations in ms. Errors: `ContractError`, `RunRefused`, `RunLocked`; a stop of the block ends the run as
`NEEDS_ENGINEER` and is not raised.
"""

from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from eng_contract import CONTRACT_VERSION
from eng_contract.canonical import canonical_json, payload_sha256
from eng_contract.envelope import FailureEnvelope, Provenance
from eng_contract.errors import ContractError, ContractWarning, ErrorCode
from eng_contract.ids import Clock, IdSource
from eng_contract.refs import Ref, RefString
from eng_contract.store import ResultStore, Workspace
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from eng_harness import __version__, errors
from eng_harness._runlock import RunLock
from eng_harness.block import Registry, WorkflowDef
from eng_harness.ctx import ToolResult
from eng_harness.engine._codec import decode_summary
from eng_harness.engine._steps import op_id, root_scope, step
from eng_harness.journal import EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalPort, BasisPort, CalcPort, HostPort, InputPort, RunClass, ToolPort

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
    return ToolResult(
        tool=name,
        ref=Ref.model_validate({"$ref": done.ref}),
        summary=decode_summary(done.summary),
        warnings=tuple(ContractWarning.model_validate(w) for w in done.warnings),
        complete=done.complete,
        model=None,
    )


class _Ctx:
    """The ctx of the root block. Task T9 wires `tool` only; the other calls, retries and handles are task T10."""

    def __init__(self, tools: ToolPort, clock: Clock, run_id: str, writer: JournalWriter) -> None:
        """Serve one run: its tool port, clock, id and journal writer."""
        self._tools, self._clock, self._run_id, self._writer = tools, clock, run_id, writer

    async def tool(self, name: str, args: Mapping[str, JsonValue] | None = None) -> ToolResult:
        """Call the host tool `name` as one step (spec 4.3.2).

        Raises:
            ToolFailed: a failure envelope. `ContractError`: a tool outside the allowlist.
            BlockRuleViolation: a step started while another is in progress in the same scope.
        """
        arguments = dict(args or {})
        return await step(lambda path: self._tool(path, name, arguments))

    async def _tool(self, path: str, name: str, args: dict[str, JsonValue]) -> ToolResult:
        info = await self._tools.describe(name)
        op = op_id(self._run_id, path, 1)
        model = args.get(info.model_param) if info.model_param else None
        key = model if isinstance(model, str) else None
        started = {
            "kind": "tool", "name": name, "args": args, "args_sha256": payload_sha256(args), "effect": info.effect,
            "op_id": op if info.effect == "write" else None, "host_key": info.host_key, "model_key": key,
        }  # fmt: skip
        self._writer.append(EventType.STEP_STARTED, started, path=path, attempt=1)
        began = self._clock.now_ms()
        envelope = await self._tools.call(name, args, op_id=op, model=key)
        millis = self._clock.now_ms() - began
        if isinstance(envelope, FailureEnvelope):
            error = envelope.error
            failed = {"error": error.model_dump(mode="json"), "retryable": error.retryable, "duration_ms": millis}
            self._writer.append(EventType.STEP_FAILED, failed, path=path, attempt=1)
            raise errors.ToolFailed(error)
        done = ev.StepResult(
            ref=envelope.result_id,
            summary=envelope.summary,
            warnings=[w.model_dump(mode="json") for w in envelope.warnings],
            complete=envelope.complete,
        )
        completed = ev.StepCompleted(result=done, duration_ms=millis)
        self._writer.append(EventType.STEP_COMPLETED, completed, path=path, attempt=1)
        return _tool_result(name, done)


class Engine:
    """Starts runs; an engine holds the lock of one run at a time (spec 4.4.4)."""

    def __init__(
        self, workspace: Workspace, registry: Registry, ports: EnginePorts, store: ResultStore,
        settings: EngineSettings, clock: Clock, ids: IdSource,
    ) -> None:  # fmt: skip
        """Bind the workspace (runs live in `<root>/runs`), the registered workflows, the ports and the sources."""
        self._runs = workspace.root / "runs"
        self._registry, self._ports, self._store, self._clock, self._ids = registry, ports, store, clock, ids
        self._settings_sha256 = payload_sha256(settings.model_dump(mode="json"))

    def _producer(self) -> Provenance:
        return Provenance(
            tool="harness", tool_version=__version__, inputs={}, started_at=self._clock.now(), duration_ms=0
        )

    async def start(self, request: RunRequest) -> RunOutcome:
        """Validate `request`, create the run, journal its header and run the workflow (spec 4.5.1).

        Raises:
            ContractError: `INVALID_ARGUMENT` for an unregistered workflow or an input that fails its model.
            RunRefused: `RUN_CLASS_MISMATCH` when the calc port's class is not the request's. Neither creates a run
                folder.
            RunLocked: another engine holds the new run's lock.
        """
        found = next((b for b in self._registry.blocks if b.name == request.workflow), None)
        if not isinstance(found, WorkflowDef):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"workflow {request.workflow!r} is not registered")
        workflow: WorkflowDef[Any, Any] = found
        inp = _parse(workflow.input_model, request.input, "the run input")
        if (actual := self._ports.calc.run_class) is not request.run_class:
            raise errors.RunRefused(
                errors.HarnessCode.RUN_CLASS_MISMATCH,
                f"the calc port is {actual.value}, the run {request.run_class.value}",
            )
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
                return await self._drive(workflow, inp, run_id, writer)

    async def _drive(
        self, workflow: WorkflowDef[Any, Any], inp: BaseModel, run_id: str, writer: JournalWriter
    ) -> RunOutcome:
        """Run the root block and journal how it ends: `run_completed`, or `run_escalated` for a stop of the block."""
        try:
            with root_scope():
                out = await workflow.fn(_Ctx(self._ports.tool, self._clock, run_id, writer), inp)
            if not isinstance(out, workflow.output_model):
                wanted = workflow.output_model.__name__
                raise errors.BlockRuleViolation(f"{workflow.name} returned a {type(out).__name__}, not a {wanted}")
        except errors.BlockRuleViolation as stop:
            return self._escalate(run_id, writer, "block_rule_violation", stop)
        except errors.StepError as stop:  # a failure that left the root block
            return self._escalate(run_id, writer, "unhandled_error", stop)
        value = out.model_dump(mode="json")
        stored = self._store.put("harness.run_output/1", {"value": value}, self._producer())
        done = {"output_ref": stored.result_id, "output_sha256": payload_sha256(value), "draft": False}
        writer.append(EventType.RUN_COMPLETED, done)
        return RunOutcome(run_id, RunStatus.COMPLETED, out)

    @staticmethod
    def _escalate(
        run_id: str, writer: JournalWriter, reason: str, stop: errors.EngineStop | errors.StepError
    ) -> RunOutcome:
        """Journal `run_escalated` for `stop`; the run has not ended."""
        payload = {"reason": reason, "detail": stop.message, "evidence": list(stop.evidence)}
        escalated = ev.RunEscalated.model_validate(payload)
        writer.append(EventType.RUN_ESCALATED, escalated)
        return RunOutcome(run_id, RunStatus.NEEDS_ENGINEER, escalation=escalated)
