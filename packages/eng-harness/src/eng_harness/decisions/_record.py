"""Port data of the decision cascade (spec 0005 sections 4.5 and 4.9): call, answers, suggestion and screen.

Units: ``latency_ms`` in milliseconds, ``confidence`` as a ratio in [0, 1]. Errors: pydantic ``ValidationError`` for a
field out of bounds. Imported through ``eng_harness.decisions.interfaces``, which is their public home.
"""

from enum import StrEnum
from typing import Literal

from eng_contract.ids import Timestamp
from pydantic import BaseModel, ConfigDict, Field, InstanceOf, JsonValue

from eng_harness.ctx import BasisView
from eng_harness.decisions._points import DecisionPoint
from eng_harness.decisions._policy import DecisionPolicy
from eng_harness.decisions._rules import Rationale, Rule


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProviderOption(Frozen):
    """One option as a provider or the engineer sees it: the value and its label."""

    value: str
    label: str


class EngineerChoice(Frozen):
    """The engineer's answer to a pending decision: an option value, who answered and when."""

    choice: str
    by: str = Field(min_length=1)
    answered_at: Timestamp


class DecisionCall(BaseModel):
    """What the engine hands the cascade; ``sensitive_values`` are the model file base names the run touches."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    request_id: str
    run_id: str
    step_path: str
    point: InstanceOf[DecisionPoint]
    options: type[StrEnum] | tuple[str, ...]
    state: InstanceOf[BaseModel]
    rules: tuple[InstanceOf[Rule], ...]
    policy: DecisionPolicy
    basis: InstanceOf[BasisView]
    engineer_choice: EngineerChoice | None = None
    sensitive_values: tuple[str, ...] = ()


class SuggestionCode(Frozen):
    """The identity of the rule code that answered (spec 4.9)."""

    rule_version: int
    rule_sha256: str


class Suggestion(Frozen):
    """One tier's entry in ``decision_made.suggestions``; ``error`` is a class name and code, never a message."""

    tier: Literal[1, 2, 3]
    by: str
    outcome: Literal[
        "accepted",
        "below_threshold",
        "shadow",
        "invalid",
        "error",
        "timeout",
        "skipped_local_only",
        "skipped_redaction",
    ]
    choice: str | None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    # Serialized as "rationale" (spec 4.9); gate rule FB006 accepts only a bare Rationale type on that name.
    reasoning: Rationale | None = Field(default=None, alias="rationale")
    latency_ms: int = Field(ge=0)
    shadow: bool
    code: SuggestionCode | None = None
    error: str | None = None


class DecisionAnswer(Frozen):
    """A decided call; the engine builds ``decision_made`` from it."""

    choice: str
    decided_by: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    latency_ms: int = Field(ge=0)
    options: tuple[str, ...]
    state_sha256: str
    suggestions: tuple[Suggestion, ...] = ()


class ScreenField(Frozen):
    """One labeled state field; ``ref`` is set (and ``value`` null) for a ``Ref`` field."""

    label: str
    value: JsonValue = None
    ref: str | None = None


class ScreenItem(Frozen):
    """One call on the engineer screen: title, options, fields and every suggestion."""

    request_id: str
    title: str
    options: tuple[ProviderOption, ...]
    fields: tuple[ScreenField, ...] = ()
    suggestions: tuple[Suggestion, ...] = ()


class DecisionScreen(Frozen):
    """Data for the engineer page (spec 0006) to render; one item per pending call of a batch."""

    items: tuple[ScreenItem, ...]


class PendingAnswer(Frozen):
    """The call waits for the engineer; ``rejected`` says why a previous choice was refused."""

    request_id: str
    batch_id: str | None = None
    screen: DecisionScreen
    rejected: Literal["not_an_option", "incomplete"] | None = None
