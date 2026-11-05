"""Provider interfaces of the decision layer (spec 0005 section 4.7; plan 0005 T5).

No implementation here: the cascade catches the error types defined below and imports no provider code. Units:
``confidence`` is a ratio in [0, 1]. Errors: a provider fails only with ``ProviderError`` (a call) or
``ProviderFailure`` (one entry of a batch); their messages are fixed, so remote text never travels through them.
"""

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import Field, JsonValue

from eng_harness.decisions._record import (
    DecisionAnswer,
    DecisionCall,
    DecisionScreen,
    EngineerChoice,
    Frozen,
    PendingAnswer,
    ProviderOption,
    Suggestion,
)
from eng_harness.decisions._rules import Rationale

__all__ = [
    "ChoiceAnswer",
    "DecisionAnswer",
    "DecisionCall",
    "DecisionProvider",
    "DecisionScreen",
    "EngineerChoice",
    "LLMAnswer",
    "LLMProvider",
    "OutgoingPlace",
    "PendingAnswer",
    "ProviderError",
    "ProviderErrorCode",
    "ProviderFailure",
    "ProviderInfo",
    "ProviderOption",
    "ProviderRequest",
    "Suggestion",
    "YesNoAnswer",
]


class ProviderInfo(Frozen):
    """Who a provider is; recorded in suggestions and the run header."""

    provider: str
    model: str
    version: str
    is_local: bool
    supports_batch: bool


class ProviderRequest(Frozen):
    """The only data a provider receives: redaction-checked state, no ``Ref`` fields, no sensitive values."""

    request_id: str
    point: str
    point_version: int
    options: tuple[ProviderOption, ...]
    state: Mapping[str, JsonValue]


class ChoiceAnswer(Frozen):
    """A tier 2 choice with its confidence (ratio)."""

    choice: str
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class YesNoAnswer(Frozen):
    """A tier 2 yes or no with its confidence (ratio)."""

    answer: bool
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class LLMAnswer(Frozen):
    """A tier 3 choice with a rationale that contains no digit (``Rationale``)."""

    choice: str
    rationale: Rationale


class ProviderErrorCode(StrEnum):
    """Failure codes of spec 0009 sections 4.3 and 4.5."""

    NO_KEY = "no_key"
    CREDENTIAL_STORE = "credential_store"
    NETWORK = "network"
    TIMEOUT = "timeout"
    AUTH = "auth"
    RATE_LIMITED = "rate_limited"
    HTTP_STATUS = "http_status"
    BAD_RESPONSE = "bad_response"
    INVALID_OUTPUT = "invalid_output"
    REDACTION_BLOCKED = "redaction_blocked"
    NOT_IMPLEMENTED = "not_implemented"


class OutgoingPlace(StrEnum):
    """The kind of place a ``REDACTION_BLOCKED`` finding was in; never a path built from data."""

    POINT = "point"
    OPTION_VALUE = "option_value"
    OPTION_LABEL = "option_label"
    STATE_KEY = "state_key"
    STATE_VALUE = "state_value"
    KEY_MATERIAL = "key_material"


class ProviderError(Exception):
    """A provider call failed; ``str()`` is the code value only.

    ``gap`` is a fixed gap id (``NOT_IMPLEMENTED`` only); ``where`` is set for ``REDACTION_BLOCKED`` only. Raises
    ``ValueError`` when either is given with another code.
    """

    def __init__(self, code: ProviderErrorCode, *, gap: str | None = None, where: OutgoingPlace | None = None) -> None:
        if gap is not None and code is not ProviderErrorCode.NOT_IMPLEMENTED:
            raise ValueError("gap is set for not_implemented only")
        if where is not None and code is not ProviderErrorCode.REDACTION_BLOCKED:
            raise ValueError("where is set for redaction_blocked only")
        super().__init__(code.value)
        self.code = code
        self.gap = gap
        self.where = where


class ProviderFailure(Frozen):
    """The batch entry for one failed request."""

    code: ProviderErrorCode


@runtime_checkable
class DecisionProvider(Protocol):
    """Tier 2 (12 section 4); the cascade enforces timeouts, option validity and the confidence bound."""

    info: ProviderInfo

    async def choose(self, request: ProviderRequest) -> ChoiceAnswer:
        """Choose one option; raises ``ProviderError``."""

    async def yes_no(self, request: ProviderRequest) -> YesNoAnswer:
        """Answer a point that has ``yes_no`` set; raises ``ProviderError``."""

    async def score(self, request: ProviderRequest) -> Mapping[str, float]:
        """Score each option to order the engineer screen, never to choose; raises ``ProviderError``."""

    async def batch(self, requests: Sequence[ProviderRequest]) -> Sequence[ChoiceAnswer | ProviderFailure]:
        """One entry per request, in order."""


@runtime_checkable
class LLMProvider(Protocol):
    """Tier 3."""

    info: ProviderInfo

    async def decide(self, request: ProviderRequest) -> LLMAnswer:
        """Choose one option with a rationale; raises ``ProviderError``."""
