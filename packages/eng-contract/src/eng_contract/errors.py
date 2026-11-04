"""Error codes, retry rules, warnings and ContractError (spec 4.2.3, 4.2.4; 04 section 8).

Purpose: the fixed vocabulary of failures every tool reports. No units are involved.
Errors: invalid details raise `pydantic.ValidationError`; `ContractError` carries a valid `ErrorDetail`.
"""

from enum import StrEnum
from types import MappingProxyType
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from eng_contract._types import FieldPath


class ErrorCode(StrEnum):
    """The 22 error codes of 04 section 8.1."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    REF_NOT_FOUND = "REF_NOT_FOUND"
    REF_POINTER_INVALID = "REF_POINTER_INVALID"
    REF_KIND_MISMATCH = "REF_KIND_MISMATCH"
    REF_UNIT_MISMATCH = "REF_UNIT_MISMATCH"
    REF_STALE = "REF_STALE"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    HOST_NOT_CONNECTED = "HOST_NOT_CONNECTED"
    HOST_BUSY = "HOST_BUSY"
    HOST_WEDGED = "HOST_WEDGED"
    HOST_LOCKED = "HOST_LOCKED"
    HOST_ERROR = "HOST_ERROR"
    TIMEOUT_NO_EFFECT = "TIMEOUT_NO_EFFECT"
    TIMEOUT_UNKNOWN_OUTCOME = "TIMEOUT_UNKNOWN_OUTCOME"
    NOT_SUPPORTED_BY_VERSION = "NOT_SUPPORTED_BY_VERSION"
    INTERNAL = "INTERNAL"


class WarningCode(StrEnum):
    """The five warning codes of 04 section 8.2."""

    PARTIAL_DATA = "PARTIAL_DATA"
    MODEL_CHANGED_OUTSIDE = "MODEL_CHANGED_OUTSIDE"
    DIALOG_DISMISSED = "DIALOG_DISMISSED"
    HOST_WARNING = "HOST_WARNING"
    DEPRECATED = "DEPRECATED"


class Precondition(StrEnum):
    """State named by `PRECONDITION_FAILED` (04 section 8.1)."""

    model_saved = "model_saved"
    model_open = "model_open"
    analysis_current = "analysis_current"
    units_verified = "units_verified"
    local_workspace = "local_workspace"


class RetryRule(StrEnum):
    """How `retryable` is determined for a code (spec 4.2.3)."""

    never = "never"
    always = "always"
    after_wedge_clears = "after_wedge_clears"
    reconcile_first = "reconcile_first"
    depends = "depends"


_ALWAYS = (ErrorCode.HOST_NOT_CONNECTED, ErrorCode.HOST_BUSY, ErrorCode.TIMEOUT_NO_EFFECT)
_OTHER = {
    ErrorCode.HOST_WEDGED: RetryRule.after_wedge_clears,
    ErrorCode.TIMEOUT_UNKNOWN_OUTCOME: RetryRule.reconcile_first,
    ErrorCode.HOST_ERROR: RetryRule.depends,
}
RETRY_RULES = MappingProxyType(
    {code: (RetryRule.always if code in _ALWAYS else _OTHER.get(code, RetryRule.never)) for code in ErrorCode}
)
"""Retry rule per error code (spec 4.2.3); immutable."""

_HOST_FIELD_CODES = (ErrorCode.HOST_ERROR, ErrorCode.HOST_BUSY)

_MODEL = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=False)


def _expected_retryable(code: ErrorCode) -> bool | None:
    """Required `retryable` for a code, or None when the producer decides."""
    rule = RETRY_RULES[code]
    if rule is RetryRule.depends:
        return None
    return rule in (RetryRule.always, RetryRule.after_wedge_clears)


class ErrorDetail(BaseModel):
    """Error of a failure envelope (spec 4.2.3). Validation enforces the retry and code-specific rules."""

    model_config = _MODEL

    code: ErrorCode
    message: str = Field(min_length=1, max_length=2000)
    field: FieldPath | None = None
    expected: dict[str, JsonValue] | None = None
    received: JsonValue = None
    hint: str | None = Field(default=None, max_length=2000)
    retryable: bool
    precondition: Precondition | None = None
    host_code: str | None = Field(default=None, max_length=200)
    host_method: str | None = Field(default=None, max_length=200)
    op_id: str | None = Field(default=None, max_length=200)
    incident_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _check_rules(self) -> Self:
        want = _expected_retryable(self.code)
        if want is not None and self.retryable is not want:
            raise ValueError(f"{self.code} requires retryable={want} (rule {RETRY_RULES[self.code]})")
        if (self.precondition is not None) is not (self.code is ErrorCode.PRECONDITION_FAILED):
            raise ValueError("precondition is required for, and only allowed on, PRECONDITION_FAILED")
        if (self.incident_id is not None) is not (self.code is ErrorCode.INTERNAL):
            raise ValueError("incident_id is required for, and only allowed on, INTERNAL")
        if self.code not in _HOST_FIELD_CODES and (self.host_code is not None or self.host_method is not None):
            raise ValueError("host_code and host_method are only allowed on HOST_ERROR and HOST_BUSY")
        return self


class ContractWarning(BaseModel):
    """Non-fatal condition of a success envelope (spec 4.2.4)."""

    model_config = _MODEL

    code: WarningCode
    message: str = Field(min_length=1, max_length=2000)
    field: FieldPath | None = None


class ContractError(Exception):
    """Exception carrying one `ErrorDetail` in `.detail`; subclasses of other modules fix the code."""

    def __init__(self, code: ErrorCode, message: str, *, retryable: bool | None = None, **fields: Any) -> None:
        """Build the detail, filling `retryable` from `RETRY_RULES`.

        Raises:
            TypeError: the rule is `depends` and `retryable` is not passed.
            pydantic.ValidationError: the fields contradict the rules of spec 4.2.3.
        """
        if retryable is None:
            retryable = _expected_retryable(code)
            if retryable is None:
                raise TypeError(f"{code} requires an explicit retryable value")
        self.detail = ErrorDetail(code=code, message=message, retryable=retryable, **fields)
        super().__init__(f"{code}: {message}")
