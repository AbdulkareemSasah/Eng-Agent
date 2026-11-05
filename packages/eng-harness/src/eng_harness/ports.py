"""Ports of the run engine and their data types (spec 0001 sections 4.8, 4.9, 4.9.1).

Purpose: each port is a `typing.Protocol` implemented by adapters (0002), calcs (0003), the basis (0004) and the pages
(0006); fakes in `tests/fakes/` stand in for tests. Host results are contract `Envelope`s; data types are frozen
Pydantic models. Units: none (counters, hashes, `Timestamp`s). Errors: `ContractError` for contract conditions,
`CalcRefused` from a CalcPort, `pydantic.ValidationError` for invalid data. Methods that wait on a host or a person
are `async`; methods that read held state are synchronous. Not here: `DecisionPort` (plan T14) and `ToolPort.preview`
(needs `Preview` of `eng_harness.ctx`, plan T7).
"""

from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Envelope
from eng_contract.ids import ModelId, ResultId, Timestamp
from eng_contract.kinds.basis import DesignBasis
from eng_contract.refs import Ref, RefRule, RefString
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

from eng_harness.calc import CalcStatus
from eng_harness.journal import Event

# fmt: off
__all__ = [
    "ApprovalAnswer", "ApprovalPort", "ApprovalRequest", "BasisPort", "CalcInfo", "CalcPort", "HostInstance",
    "HostLease", "HostModelState", "HostPort", "InputAnswer", "InputPort", "InputRequest", "LoadedBasis",
    "ModelBinding", "ProgressSink", "Reconciliation", "RunClass", "RunControlPort", "SavedModel", "ServerCheck",
    "ToolInfo", "ToolPort", "UnitsState",
]
# fmt: on

_Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Obj = Mapping[str, JsonValue]
_REASON_MAX = 500


class RunClass(StrEnum):
    """Whether a run may use calcs that are not yet approved (spec 0003 section 4.5)."""

    TRIAL = "trial"
    PRODUCTION = "production"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ToolInfo(_M):
    """A tool of the allowlist; an adapter subclass overrides `overwrites_original`."""

    name: str
    effect: Literal["read", "write"]
    action: Literal["plain", "open", "save", "analysis", "design", "delete", "unlock"]
    host_key: str
    model_param: str | None = None
    engineering_params: tuple[str, ...] = ()

    def overwrites_original(self, args: _Obj) -> bool:
        """True when a call with `args` would overwrite the engineer's original file; plain tools never do."""
        return False


class Reconciliation(_M):
    """What reconciliation found about an in-flight operation (spec 0001 section 4.5.3)."""

    outcome: Literal["applied", "not_applied", "partial", "unknown"]
    result: Envelope | None = None
    missing: tuple[str, ...] = ()
    evidence: tuple[Ref, ...] = ()


class ServerCheck(_M):
    """Result of the preflight of one server (spec 0002 section 4.3.4)."""

    server: str
    build: str
    min_build: str
    fingerprint: str
    expected_fingerprint: str
    ok: bool
    reason: str | None


class HostModelState(_M):
    """State of a model in its host instance; the last four fields are `None` exactly when `loaded` is false."""

    loaded: bool
    model_id: ModelId | None = None
    revision: int | None = Field(default=None, ge=0)
    fingerprint: str | None = None
    file_sha256: _Sha | None = None

    @model_validator(mode="after")
    def _loaded_rule(self) -> Self:
        values = (self.model_id, self.revision, self.fingerprint, self.file_sha256)
        if self.loaded is not all(v is not None for v in values) or (
            not self.loaded and any(v is not None for v in values)
        ):
            raise ValueError("model_id, revision, fingerprint and file_sha256 are set if and only if loaded is true")
        return self


class SavedModel(_M):
    """A saved model file: the state it holds and its base name (no path)."""

    model_id: ModelId
    revision: int = Field(ge=0)
    fingerprint: str
    file_sha256: _Sha
    file_name: Annotated[str, StringConstraints(pattern=r"^[^/\\]+$", max_length=255)]


class UnitsState(_M):
    """Units of a model against those it was opened with; `ok` true and `present` `None` when not loaded."""

    loaded: bool
    ok: bool
    present: str | None
    expected: str

    @model_validator(mode="after")
    def _not_loaded(self) -> Self:
        if not self.loaded and (not self.ok or self.present is not None):
            raise ValueError("a model that is not loaded has ok true and present None")
        return self


class HostLease(_M):
    """A lease on the server group of a host (spec 0002 section 4.4.1)."""

    host_key: str
    lease_id: str


class HostInstance(_M):
    """One running host program instance; `process_started_at` guards against pid reuse."""

    instance_id: str
    pid: int = Field(ge=1)
    process_started_at: Timestamp
    program: str


class CalcInfo(_M):
    """A calc as the CalcPort describes it; `ref_rules` maps an argument field path to its contract `RefRule`."""

    id: str
    version: int = Field(ge=1)
    content_sha256: _Sha
    status: CalcStatus
    engineering_params: tuple[str, ...]
    basis_fields: tuple[str, ...]
    ref_rules: Mapping[str, RefRule]


class LoadedBasis(_M):
    """A frozen design basis and the result it came from."""

    result_id: ResultId
    basis: DesignBasis


class ModelBinding(_M):
    """The state of one model that an approval is bound to (spec 0001 section 4.9)."""

    model_key: str
    model_id: ModelId
    revision: int = Field(ge=0)
    fingerprint: str
    file_sha256: _Sha


class ApprovalRequest(_M):
    """An approval presented to the engineer; `shown_sha256` is the `payload_sha256` of the stored preview."""

    request_id: str
    run_id: str
    kind: str
    title: str
    preview_ref: RefString
    shown_sha256: _Sha
    binding: tuple[ModelBinding, ...]
    items: tuple[str, ...]


class ApprovalAnswer(_M):
    """The engineer's answer; a rejected item needs a reason of 1 to 500 characters after trimming."""

    request_id: str
    shown_sha256: _Sha
    decision: Literal["approve", "reject"]
    rejected_items: tuple[str, ...] = ()
    item_reasons: Mapping[str, str] = Field(default_factory=dict)
    acknowledged_unreleased: bool = False
    reason: str | None = None
    by: str = Field(min_length=1)

    @model_validator(mode="after")
    def _reasons(self) -> Self:
        for item in self.rejected_items:
            if item not in self.item_reasons:
                raise ValueError(f"rejected item {item!r} has no reason")
        for item, text in self.item_reasons.items():
            if not 1 <= len(text.strip()) <= _REASON_MAX:
                raise ValueError(f"reason of item {item!r} must have 1 to {_REASON_MAX} characters after trimming")
        return self


class InputRequest(_M):
    """A request for data or a choice; `fields_schema` carries the `x-eng-input` marker (spec 0001 section 4.9.1)."""

    request_id: str
    kind: Literal["block", "engine.in_flight", "engine.host_state", "engine.escalation", "engine.decision"]
    title: str
    fields_schema: Mapping[str, JsonValue]
    evidence: tuple[RefString, ...] = ()

    @property
    def fields_schema_sha256(self) -> str:
        """SHA-256 of the canonical schema; an answer must quote it."""
        return payload_sha256(dict(self.fields_schema))


class InputAnswer(_M):
    """An answer holding exactly one of `values` (data request) and `choices` (property name to option value)."""

    request_id: str
    shown_sha256: _Sha
    values: Mapping[str, JsonValue] | None = None
    choices: Mapping[str, str] | None = None
    by: str = Field(min_length=1)

    @model_validator(mode="after")
    def _one_of(self) -> Self:
        if (self.values is None) is (self.choices is None):
            raise ValueError("exactly one of values and choices must be set")
        return self


class ToolPort(Protocol):
    """Tools of a host (spec 0002). Every call returns a contract `Envelope`."""

    async def describe(self, tool: str) -> ToolInfo:
        """Return the tool's info; `ContractError` `INVALID_ARGUMENT` for a tool outside the allowlist."""

    def unreleased_tools(self) -> Mapping[str, str]:
        """Tool name to the record of its project-lane work (ADR-0026 section 3); empty when all are released."""

    async def call(self, tool: str, args: _Obj, *, op_id: str, model: str | None) -> Envelope:
        """Call `tool` for the model `model` (a model key or `None`); `op_id` makes the call reconcilable."""

    def supports_reconcile(self, tool: str) -> bool:
        """True when `reconcile` can decide the outcome of a lost call of `tool`."""

    async def reconcile(self, tool: str, args: _Obj, op_id: str) -> Reconciliation:
        """Decide whether the call with `op_id` took effect."""

    async def read_back(self, tool: str, args: _Obj) -> Envelope | None:
        """Read the state a write would produce, or `None` when the adapter has no read-back for `tool`."""


class HostPort(Protocol):
    """Host programs, their models and leases (spec 0002 sections 4.4, 4.5.9)."""

    async def preflight(self, min_builds: Mapping[str, str]) -> list[ServerCheck]:
        """Check each server against its minimum build."""

    async def acquire(self, host_key: str) -> HostLease:
        """Lease the host's server group; `HOST_LOCKED` when held elsewhere."""

    async def release(self, lease: HostLease) -> None:
        """Release a lease."""

    def session_epoch(self, host_key: str) -> int:
        """Counter that grows on timeout, crash, restart or reconnect of the host's servers."""

    async def locate(self, model_key: str) -> HostInstance | None:
        """The bound instance that holds the model, or `None`."""

    async def model_state(self, model_key: str, instance_id: str) -> HostModelState:
        """State in `instance_id`; never raises for an instance that lacks the model: `loaded` is false."""

    async def check_model(self, model_key: str) -> Envelope:
        """Run the model check (`issues.model_check/1`)."""

    async def save(self, model_key: str, role: str) -> SavedModel:
        """Save the model under `role`."""

    async def read_units(self, model_key: str, instance_id: str) -> UnitsState:
        """Units of the model in `instance_id`; never raises for an instance that lacks the model."""

    async def working_copy(self, model_key: str, folder: Path) -> str:
        """Copy the model into `folder`, open the copy and return its model key."""

    async def restore(self, model_key: str, saved: SavedModel) -> HostInstance:
        """Open `saved` for `model_key` and return the instance that holds it."""

    def model_files(self, model_key: str) -> tuple[Path, ...]:
        """The files of the model."""

    async def started_instances(self, host_key: str) -> list[HostInstance]:
        """Instances this run started on the host."""

    async def close_started(self, host_key: str, instances: Sequence[HostInstance]) -> None:
        """Close the given instances."""


class CalcPort(Protocol):
    """Calcs (spec 0003)."""

    @property
    def run_class(self) -> RunClass:
        """The run class given at construction; it does not change."""

    def describe(self, calc_id: str) -> CalcInfo:
        """Return the calc's info."""

    def run(self, calc_id: str, args: _Obj) -> Envelope:
        """Run a calc; raises `CalcRefused` for a calc not approved in a production run, or withdrawn."""


class BasisPort(Protocol):
    """Design bases (spec 0004)."""

    def load(self, basis_ref: str) -> LoadedBasis:
        """Load the `basis.design_basis/1` result named by `basis_ref`."""


class ApprovalPort(Protocol):
    """Approvals presented to the engineer (spec 0006)."""

    async def present(self, request: ApprovalRequest) -> None:
        """Show the request."""

    async def answer(self, request_id: str, *, wait: bool) -> ApprovalAnswer | None:
        """The answer, or `None` when there is none (the engine pauses)."""


class InputPort(Protocol):
    """Input requests presented to the engineer (spec 0006)."""

    async def present(self, request: InputRequest) -> None:
        """Show the request."""

    async def answer(self, request_id: str, *, wait: bool) -> InputAnswer | None:
        """The answer, or `None` when there is none (the engine pauses)."""


class ProgressSink(Protocol):
    """Receives every journal event after its commit."""

    def emit(self, event: Event) -> None:
        """Synchronous; must not block."""


class RunControlPort(Protocol):
    """Stop requests from the engineer."""

    def stop_requested(self, run_id: str) -> bool:
        """True when the run should pause (checked between steps)."""
