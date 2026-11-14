"""In-memory fakes of the harness ports (spec 0001 section 4.8; plan 0001 T6; lead decision D-5).

Test doubles only: a fake host with a ledger of every call and its `op_id`, scripted outcomes, model state with
revision and fingerprint, units, a host crash, session epochs and leases; a fake CalcPort, BasisPort, ApprovalPort and
InputPort with scripted answers; a DecisionPort whose handler answers each call; a recording ProgressSink and a
RunControlPort. Nothing here reads a clock, a network or a host program. Revisions and fingerprints are counters, not
engineering values.
"""

from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from eng_contract.envelope import FailureEnvelope, Provenance, SuccessEnvelope, make_failure
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.ids import Clock, IdSource, new_model_id, new_result_id
from pydantic import JsonValue

from eng_harness.ctx import Preview
from eng_harness.decisions.interfaces import DecisionAnswer, DecisionCall, PendingAnswer
from eng_harness.journal import Event
from eng_harness.ports import (
    ApprovalAnswer,
    ApprovalRequest,
    CalcInfo,
    HostInstance,
    HostLease,
    HostModelState,
    InputAnswer,
    InputRequest,
    LoadedBasis,
    Reconciliation,
    RunClass,
    SavedModel,
    ServerCheck,
    ToolInfo,
    UnitsState,
)

ENVELOPE = SuccessEnvelope | FailureEnvelope


@dataclass(frozen=True)
class Raise:
    """A scripted outcome that raises instead of returning an envelope."""

    error: BaseException


@dataclass(frozen=True)
class LedgerEntry:
    """One call that reached the fake host: the tool, its arguments, the `op_id` and the model key."""

    tool: str
    args: Mapping[str, JsonValue]
    op_id: str
    model: str | None


def failure(code: ErrorCode, message: str = "scripted failure") -> FailureEnvelope:
    """A failure envelope of `code` (the retry flag comes from the contract rule)."""
    return make_failure(ContractError(code, message))


class FakeHost:
    """A fake ToolPort and HostPort over one in-memory host (S-10's reconciler stand-in)."""

    def __init__(
        self, tools: Sequence[ToolInfo], ids: IdSource, clock: Clock, unreleased: Mapping[str, str] | None = None
    ) -> None:
        """Hold `tools` by name; `ids` and `clock` are the deterministic contract sources."""
        self._tools = {t.name: t for t in tools}
        self._ids, self._clock = ids, clock
        self._unreleased = dict(unreleased or {})
        self.ledger: list[LedgerEntry] = []
        self.outcomes: dict[str, deque[ENVELOPE | Raise]] = defaultdict(deque)
        self.reconciliations: dict[str, Reconciliation] = {}
        self.epochs: dict[str, int] = defaultdict(int)
        self.leases: dict[str, HostLease] = {}
        self.models: dict[str, HostModelState] = {}
        self.bound: dict[str, str] = {}
        self.units: dict[str, UnitsState] = {}
        self.instances: dict[str, list[HostInstance]] = defaultdict(list)
        self.saved: list[SavedModel] = []
        self.previews: dict[str, Preview] = {}
        self.closed: list[HostInstance] = []
        self._succeeded: set[str] = set()

    def script(self, tool: str, *outcomes: ENVELOPE | Raise) -> None:
        """Queue outcomes for the next calls of `tool`; with none queued a call succeeds."""
        self.outcomes[tool].extend(outcomes)

    def add_model(self, model_key: str, instance: HostInstance, *, units: str = "unit-system-a") -> None:
        """Open a model at revision 0 on `instance`."""
        self.instances[instance.program].append(instance)
        self.bound[model_key] = instance.instance_id
        self.models[model_key] = HostModelState(
            loaded=True, model_id=new_model_id(self._ids), revision=0, fingerprint="fp0", file_sha256="0" * 64
        )
        self.units[model_key] = UnitsState(loaded=True, ok=True, present=units, expected=units)

    def crash(self, host_key: str) -> None:
        """A host crash: every model is reported not loaded and the session epoch increases."""
        self.epochs[host_key] += 1
        for key in self.models:
            self.models[key] = HostModelState(loaded=False)
            self.units[key] = UnitsState(loaded=False, ok=True, present=None, expected=self.units[key].expected)

    # ToolPort
    async def describe(self, tool: str) -> ToolInfo:
        """The tool's info; a tool outside the allowlist is `INVALID_ARGUMENT`."""
        if tool not in self._tools:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "tool is not in the allowlist", received=tool)
        return self._tools[tool]

    def unreleased_tools(self) -> Mapping[str, str]:
        """Tool name to release record."""
        return dict(self._unreleased)

    async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> ENVELOPE:
        """Record the call, then play the next scripted outcome or succeed (a write bumps the model revision)."""
        info = await self.describe(tool)
        self.ledger.append(LedgerEntry(tool, dict(args), op_id, model))
        queue = self.outcomes[tool]
        outcome = queue.popleft() if queue else self._success(info.name)
        if isinstance(outcome, Raise):
            raise outcome.error
        if outcome.ok:
            self._succeeded.add(op_id)
            if info.effect == "write" and model in self.models:
                state = self.models[model]
                if state.loaded and state.revision is not None:
                    n = state.revision + 1
                    self.models[model] = state.model_copy(update={"revision": n, "fingerprint": f"fp{n}"})
        return outcome

    def _success(self, name: str) -> SuccessEnvelope:
        prov = Provenance(tool="harness", tool_version="fake", inputs={}, started_at=self._clock.now(), duration_ms=0)
        return SuccessEnvelope(
            contract="eng-contract/1",
            ok=True,
            result_id=new_result_id(self._ids),
            kind="harness.run_output/1",
            summary={"tool": name},
            complete=True,
            provenance=prov,
        )

    def supports_reconcile(self, tool: str) -> bool:
        """True for every write tool."""
        return self._tools[tool].effect == "write"

    async def reconcile(self, tool: str, args: Mapping[str, JsonValue], op_id: str) -> Reconciliation:
        """The scripted reconciliation of `op_id`, else `applied` when a call with that `op_id` succeeded."""
        if op_id in self.reconciliations:
            return self.reconciliations[op_id]
        if op_id in self._succeeded:
            return Reconciliation(outcome="applied")
        return Reconciliation(outcome="not_applied")

    async def read_back(self, tool: str, args: Mapping[str, JsonValue]) -> ENVELOPE | None:
        """The fake host has no read-back helpers."""
        return None

    async def preview(self, tool: str, args: Mapping[str, JsonValue]) -> Preview:
        """The scripted preview of `tool`, or an empty one: the fake host changes nothing."""
        await self.describe(tool)
        return self.previews.get(tool, Preview(items=(), diff_ref=None, models=()))

    # HostPort
    async def preflight(self, min_builds: Mapping[str, str]) -> list[ServerCheck]:
        """One passing check per minimum build."""
        return [
            ServerCheck(server=s, build=b, min_build=b, fingerprint="f", expected_fingerprint="f", ok=True, reason=None)
            for s, b in sorted(min_builds.items())
        ]

    async def acquire(self, host_key: str) -> HostLease:
        """Lease the host; a second lease on a held host is `HOST_LOCKED`."""
        if host_key in self.leases:
            raise ContractError(ErrorCode.HOST_LOCKED, "host is leased", received=host_key)
        lease = HostLease(host_key=host_key, lease_id=new_result_id(self._ids))
        self.leases[host_key] = lease
        return lease

    async def release(self, lease: HostLease) -> None:
        """Release the lease."""
        self.leases.pop(lease.host_key, None)

    def session_epoch(self, host_key: str) -> int:
        """Count of crashes and restarts of the host."""
        return self.epochs[host_key]

    async def locate(self, model_key: str) -> HostInstance | None:
        """The bound instance when the model is loaded, else `None`."""
        if not self.models.get(model_key, HostModelState(loaded=False)).loaded:
            return None
        iid = self.bound[model_key]
        return next(i for group in self.instances.values() for i in group if i.instance_id == iid)

    async def model_state(self, model_key: str, instance_id: str) -> HostModelState:
        """The state, or not loaded when the instance does not hold the model."""
        if self.bound.get(model_key) != instance_id:
            return HostModelState(loaded=False)
        return self.models.get(model_key, HostModelState(loaded=False))

    async def check_model(self, model_key: str) -> ENVELOPE:
        """A success envelope standing for `issues.model_check/1`."""
        return self._success("check_model")

    async def save(self, model_key: str, role: str) -> SavedModel:
        """Save the model at its current revision."""
        state = self.models[model_key]
        if not state.loaded or state.model_id is None or state.revision is None or state.fingerprint is None:
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED, "model is not open", precondition=Precondition.model_open
            )
        saved = SavedModel(
            model_id=state.model_id,
            revision=state.revision,
            fingerprint=state.fingerprint,
            file_sha256=f"{state.revision:064x}",
            file_name=f"{role}-{state.revision}.edb",
        )
        self.saved.append(saved)
        return saved

    async def read_units(self, model_key: str, instance_id: str) -> UnitsState:
        """The units state; not loaded when the instance does not hold the model."""
        expected = self.units[model_key].expected
        if self.bound.get(model_key) != instance_id or not self.models[model_key].loaded:
            return UnitsState(loaded=False, ok=True, present=None, expected=expected)
        return self.units[model_key]

    async def working_copy(self, model_key: str, folder: Path) -> str:
        """Open a copy of the model as `<model_key>@copy` on the same instance."""
        copy_key = f"{model_key}@copy"
        self.bound[copy_key] = self.bound[model_key]
        self.models[copy_key] = self.models[model_key].model_copy(update={"model_id": new_model_id(self._ids)})
        self.units[copy_key] = self.units[model_key]
        return copy_key

    async def restore(self, model_key: str, saved: SavedModel) -> HostInstance:
        """Open the saved model on a new instance."""
        old = self.bound[model_key]
        program = next(i.program for g in self.instances.values() for i in g if i.instance_id == old)
        fresh = HostInstance(
            instance_id=f"{old}+r",
            pid=10_000 + len(self.instances[program]),
            process_started_at=self._clock.now(),
            program=program,
        )
        self.instances[program].append(fresh)
        self.bound[model_key] = fresh.instance_id
        self.models[model_key] = HostModelState(
            loaded=True,
            model_id=saved.model_id,
            revision=saved.revision,
            fingerprint=saved.fingerprint,
            file_sha256=saved.file_sha256,
        )
        expected = self.units[model_key].expected
        self.units[model_key] = UnitsState(loaded=True, ok=True, present=expected, expected=expected)
        return fresh

    def model_files(self, model_key: str) -> tuple[Path, ...]:
        """The model file only."""
        return (Path(f"{model_key}.edb"),)

    async def started_instances(self, host_key: str) -> list[HostInstance]:
        """Instances of `host_key` started in this run."""
        return list(self.instances[host_key])

    async def close_started(self, host_key: str, instances: Sequence[HostInstance]) -> None:
        """Close the given instances."""
        self.closed.extend(instances)
        gone = {i.instance_id for i in instances}
        self.instances[host_key] = [i for i in self.instances[host_key] if i.instance_id not in gone]


class FakeCalcPort:
    """A CalcPort over a table of `CalcInfo` and scripted results."""

    def __init__(self, run_class: RunClass, infos: Sequence[CalcInfo]) -> None:
        """Set the run class (read-only afterwards) and the known calcs."""
        self._run_class = run_class
        self._infos = {i.id: i for i in infos}
        self.results: dict[str, ENVELOPE | Raise] = {}
        self.runs: list[tuple[str, Mapping[str, JsonValue]]] = []

    @property
    def run_class(self) -> RunClass:
        """The run class given at construction."""
        return self._run_class

    def describe(self, calc_id: str) -> CalcInfo:
        """The calc's info; an unknown id is `INVALID_ARGUMENT`."""
        if calc_id not in self._infos:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "unknown calc", received=calc_id)
        return self._infos[calc_id]

    def run(self, calc_id: str, args: Mapping[str, JsonValue]) -> ENVELOPE:
        """Record the run and return or raise the scripted result."""
        self.describe(calc_id)
        self.runs.append((calc_id, dict(args)))
        outcome = self.results[calc_id]
        if isinstance(outcome, Raise):
            raise outcome.error
        return outcome


class FakeBasisPort:
    """A BasisPort over loaded bases keyed by reference string."""

    def __init__(self, bases: Mapping[str, LoadedBasis]) -> None:
        """Hold `bases` by ref."""
        self._bases = dict(bases)

    def load(self, basis_ref: str) -> LoadedBasis:
        """The basis of `basis_ref`; an unknown ref is `REF_NOT_FOUND`."""
        if basis_ref not in self._bases:
            raise ContractError(ErrorCode.REF_NOT_FOUND, "basis not found", received=basis_ref)
        return self._bases[basis_ref]


class _Scripted[Req, Ans]:
    """Shared body of the approval and input fakes: presented requests and answers scripted per request id."""

    def __init__(self) -> None:
        self.presented: list[Req] = []
        self.answers: dict[str, deque[Ans]] = defaultdict(deque)
        self.waits: list[bool] = []

    def script(self, request_id: str, *answers: Ans) -> None:
        """Queue answers for `request_id`."""
        self.answers[request_id].extend(answers)

    async def answer(self, request_id: str, *, wait: bool) -> Ans | None:
        """The next scripted answer, or `None` (no answer yet: the engine pauses)."""
        self.waits.append(wait)
        queue = self.answers[request_id]
        return queue.popleft() if queue else None


class FakeApprovalPort(_Scripted[ApprovalRequest, ApprovalAnswer]):
    """An ApprovalPort with scripted answers."""

    async def present(self, request: ApprovalRequest) -> None:
        """Record the request."""
        self.presented.append(request)


class FakeInputPort(_Scripted[InputRequest, InputAnswer]):
    """An InputPort with scripted answers."""

    async def present(self, request: InputRequest) -> None:
        """Record the request."""
        self.presented.append(request)


class FakeDecisionPort:
    """A DecisionPort whose `handler` answers each call (by default: the first option, decided by `rule:fake`).

    `calls` holds every call that reached the port, in order, and `batches` the size of each `decide_many`;
    `runtime` is what `runtime_summary()` returns and `summaries` counts its calls.
    """

    def __init__(self, handler: Callable[[DecisionCall], DecisionAnswer | PendingAnswer] | None = None) -> None:
        self.handler = handler or self._first
        self.calls: list[DecisionCall] = []
        self.batches: list[int] = []
        self.runtime: dict[str, JsonValue] = {}
        self.summaries = 0

    @staticmethod
    def _first(call: DecisionCall) -> DecisionAnswer:
        values = tuple(str(m.value) for m in call.options) if isinstance(call.options, type) else call.options
        choice = values[0] if isinstance(call.options, type) else "0"  # reference options answer by index
        return DecisionAnswer(
            choice=choice, decided_by="rule:fake", latency_ms=0, options=values, state_sha256="0" * 64
        )

    async def decide(self, call: DecisionCall) -> DecisionAnswer | PendingAnswer:
        """Record the call and return what the handler answers."""
        self.calls.append(call)
        return self.handler(call)

    async def decide_many(self, calls: Sequence[DecisionCall]) -> list[DecisionAnswer | PendingAnswer]:
        """Record the calls and the batch size, and return one answer for each call."""
        self.calls.extend(calls)
        self.batches.append(len(calls))
        return [self.handler(call) for call in calls]

    def runtime_summary(self) -> dict[str, JsonValue]:
        """Count the call and return `runtime`."""
        self.summaries += 1
        return dict(self.runtime)


@dataclass
class RecordingProgressSink:
    """A ProgressSink that records every event in arrival order."""

    events: list[Event] = field(default_factory=list)

    def emit(self, event: Event) -> None:
        """Record the event."""
        self.events.append(event)


@dataclass
class FakeRunControl:
    """A RunControlPort whose stop requests are set by the test."""

    stopped: set[str] = field(default_factory=set)

    def stop_requested(self, run_id: str) -> bool:
        """True when a stop was requested for `run_id`."""
        return run_id in self.stopped


__all__ = [
    "FakeApprovalPort",
    "FakeBasisPort",
    "FakeCalcPort",
    "FakeDecisionPort",
    "FakeHost",
    "FakeInputPort",
    "FakeRunControl",
    "LedgerEntry",
    "Raise",
    "RecordingProgressSink",
    "failure",
]
