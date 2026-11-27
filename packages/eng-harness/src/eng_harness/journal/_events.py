"""The 21 journal event types and their payload models (spec 0001 section 4.4.2).

Every payload has `extra="forbid"`. Durations are milliseconds; timestamps are contract `Timestamp`s. Opaque JSON
fields belong to later tasks (ports, ctx, decisions). Errors: `pydantic.ValidationError` on a bad payload.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, Self

from eng_contract.errors import ErrorDetail
from eng_contract.ids import ModelId, ResultId, Timestamp
from eng_contract.refs import RefString
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    StrictBool,
    StringConstraints,
    model_serializer,
    model_validator,
)

from eng_harness.errors import HarnessCode

_Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Name = Annotated[str, StringConstraints(pattern=r"^[^/\\]+$", max_length=255)]
_Obj = dict[str, JsonValue]
_Ms = Annotated[int, Field(ge=0)]


class EventType(StrEnum):
    """Event types, in the order of the table of spec section 4.4.2."""

    RUN_STARTED = "run_started"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_RECONCILED = "step_reconciled"
    STEP_RERUN = "step_rerun"
    DECISION_MADE = "decision_made"
    INPUT_REQUESTED = "input_requested"
    INPUT_PROVIDED = "input_provided"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    HOST_STARTED = "host_started"
    MODEL_BOUND = "model_bound"
    CHECK_ENFORCED = "check_enforced"
    MODEL_SAVED = "model_saved"
    RUN_PAUSED = "run_paused"
    RUN_RESUMED = "run_resumed"
    RUN_ESCALATED = "run_escalated"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    SIGNED_OFF = "signed_off"


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class BlockRef(_P):
    """Name, version and code hash of a block."""

    name: str
    version: str
    code_sha256: _Sha


class CalcRef(_P):
    """The calc a calc step ran."""

    id: str
    version: str
    content_sha256: _Sha
    status: str


class StepResult(_P):
    """The envelope summary of a step result: the stored result by reference."""

    ref: RefString
    summary: _Obj
    warnings: list[_Obj]
    complete: bool


class HarnessError(_P):
    """A failure that is not a contract `ErrorDetail`."""

    harness_code: HarnessCode
    message: str


class RunHeader(_P):
    """`run_started`."""

    run_id: str
    workflow: str
    block: BlockRef
    input_ref: RefString
    input_sha256: _Sha
    basis_ref: RefString
    mode: Literal["work_on_copy", "approve_each_write", "autonomous_logged"]
    run_class: Literal["trial", "production"]
    engine_version: str
    contract_version: str
    settings_sha256: _Sha
    servers: list[_Obj]
    always_ask: list[str]
    unreleased_tools: _Obj = Field(default_factory=dict)
    decision_runtime: _Obj = Field(default_factory=dict)


class StepStarted(_P):
    """`step_started`: exactly one of `args` and `args_ref` (a `harness.journal_blob/1` result).

    `action` is the tool's `ToolInfo.action` (spec 4.4.2). It is optional, so a journal written before it existed
    still reads. `opens_model_without_writing` (B-562) is a strict optional boolean, true only on a `tool` step with
    effect `write` and action `open`; `None` is left out of the serialized payload, so earlier payloads keep their form.
    """

    kind: str
    name: str
    args: _Obj | None = None
    args_ref: ResultId | None = None
    args_sha256: _Sha
    effect: Literal["none", "read", "write"]
    action: Literal["plain", "open", "save", "analysis", "design", "delete", "unlock"] | None = None
    opens_model_without_writing: StrictBool | None = None
    op_id: str | None = None
    host_key: str | None = None
    model_key: str | None = None
    under: str | None = None
    item: str | None = None
    child: BlockRef | None = None

    @model_validator(mode="after")
    def _one_args(self) -> Self:
        if (self.args is None) is (self.args_ref is None):
            raise ValueError("exactly one of args and args_ref must be set")
        if self.opens_model_without_writing and (self.kind, self.effect, self.action) != ("tool", "write", "open"):
            raise ValueError("opens_model_without_writing is true only on a tool write with action open")
        return self

    @model_serializer(mode="wrap")
    def _omit_unset(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        data: dict[str, object] = handler(self)
        if data.get("opens_model_without_writing") is None:
            data.pop("opens_model_without_writing", None)
        return data


class StepCompleted(_P):
    """`step_completed`: a step result, or the output ref of a block step."""

    result: StepResult | None = None
    output_ref: RefString | None = None
    duration_ms: _Ms
    calc: CalcRef | None = None


class StepFailed(_P):
    """`step_failed`."""

    error: ErrorDetail | HarnessError
    retryable: bool
    duration_ms: _Ms


class StepReconciled(_P):
    """`step_reconciled`."""

    op_id: str
    outcome: Literal["applied", "not_applied"]
    result: StepResult | None = None
    decided_by: Annotated[str, StringConstraints(pattern=r"^(adapter|engineer:.+)$")]
    evidence: list[RefString]


class StepRerun(_P):
    """`step_rerun`."""

    reason: Literal["read_in_flight", "retryable_failure", "restored"]


class DecisionMade(_P):
    """`decision_made`."""

    point: str
    options: list[JsonValue]
    choice: JsonValue
    decided_by: str
    confidence: float | None
    latency_ms: _Ms
    state_sha256: _Sha
    suggestions: list[JsonValue]
    request_id: str | None = None


class InputRequested(_P):
    """`input_requested`."""

    request_id: str
    kind: Literal["block", "engine.in_flight", "engine.host_state", "engine.escalation", "engine.decision"]
    title: str
    fields_schema_sha256: _Sha


class InputProvided(_P):
    """`input_provided`."""

    request_id: str
    answer_ref: RefString
    by: str


class ApprovalRequested(_P):
    """`approval_requested`."""

    request_id: str
    kind: str
    title: str
    preview_ref: RefString
    shown_sha256: _Sha
    binding: _Obj
    items: list[str]


class ApprovalResolved(_P):
    """`approval_resolved`."""

    request_id: str
    shown_sha256: _Sha
    decision: Literal["approve", "reject"]
    rejected_items: list[str]
    item_reasons: dict[str, str] = Field(default_factory=dict)
    acknowledged_unreleased: bool = False
    reason: str | None = None
    by: Annotated[str, StringConstraints(pattern=r"^(engineer|mode):.+$")]


class HostStarted(_P):
    """`host_started`."""

    host_key: str
    instance_id: str
    pid: Annotated[int, Field(ge=1)]
    process_started_at: Timestamp
    program: str


class ModelBound(_P):
    """`model_bound`."""

    model_key: str
    host_key: str
    instance_id: str
    reason: Literal["first_use", "restored", "reopened"]
    file_names: list[_Name]


class CheckEnforced(_P):
    """`check_enforced`."""

    invariant: Annotated[int, Field(ge=1, le=10)]
    model_key: str | None = None
    host_key: str | None = None
    outcome: Literal["pass", "fail"]
    ref: RefString | None = None


class ModelSaved(_P):
    """`model_saved`."""

    model_key: str
    model_id: ModelId
    revision: Annotated[int, Field(ge=0)]
    fingerprint: str
    file_sha256: _Sha
    file_name: _Name
    role: Literal["working_copy", "revision", "pre_analysis", "baseline", "promoted"]
    origin_sha256: _Sha | None = None
    origin_file_names: list[_Name] = Field(default_factory=list)


class RunPaused(_P):
    """`run_paused`."""

    reason: Literal["awaiting_approval", "awaiting_input", "stop_requested"]
    request_ids: list[str]


class RunResumed(_P):
    """`run_resumed`; `unreleased_tools` and `decision_runtime` only when they differ from the last record."""

    resume_no: Annotated[int, Field(ge=1)]
    code_hash_changed: bool
    servers: list[_Obj]
    restored_to_seq: Annotated[int, Field(ge=1)] | None = None
    unreleased_tools: _Obj | None = None
    decision_runtime: _Obj | None = None


class RunEscalated(_P):
    """`run_escalated`; not terminal."""

    reason: Literal[
        "replay_divergence", "needs_reconciliation", "host_state_mismatch", "units_mismatch",
        "attempts_exhausted", "block_escalation", "block_rule_violation", "unhandled_error",
    ]  # fmt: skip
    detail: str
    evidence: list[str]
    request_id: str | None = None


class RunCompleted(_P):
    """`run_completed`; terminal."""

    output_ref: RefString
    output_sha256: _Sha
    draft: bool


class RunFailed(_P):
    """`run_failed`; terminal."""

    reason: Literal["abandoned"]
    by: str


class SignedOff(_P):
    """`signed_off`: accepted after a terminal event."""

    outputs: list[RefString]
    approval_request_id: str
    by: str


PAYLOAD_MODELS: dict[EventType, type[BaseModel]] = {
    EventType.RUN_STARTED: RunHeader, EventType.STEP_STARTED: StepStarted,
    EventType.STEP_COMPLETED: StepCompleted, EventType.STEP_FAILED: StepFailed,
    EventType.STEP_RECONCILED: StepReconciled, EventType.STEP_RERUN: StepRerun,
    EventType.DECISION_MADE: DecisionMade, EventType.INPUT_REQUESTED: InputRequested,
    EventType.INPUT_PROVIDED: InputProvided, EventType.APPROVAL_REQUESTED: ApprovalRequested,
    EventType.APPROVAL_RESOLVED: ApprovalResolved, EventType.HOST_STARTED: HostStarted,
    EventType.MODEL_BOUND: ModelBound, EventType.CHECK_ENFORCED: CheckEnforced,
    EventType.MODEL_SAVED: ModelSaved, EventType.RUN_PAUSED: RunPaused, EventType.RUN_RESUMED: RunResumed,
    EventType.RUN_ESCALATED: RunEscalated, EventType.RUN_COMPLETED: RunCompleted,
    EventType.RUN_FAILED: RunFailed, EventType.SIGNED_OFF: SignedOff,
}  # fmt: skip
"""The payload model of each event type."""


@dataclass(frozen=True)
class Event:
    """One journal event with its typed payload."""

    seq: int
    type: EventType
    path: str | None
    attempt: int | None
    at: str
    payload: BaseModel
