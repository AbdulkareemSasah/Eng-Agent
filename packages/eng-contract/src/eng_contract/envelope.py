"""Provenance and envelopes (spec 4.2.2, 4.2.5; 04 section 1).

Purpose: the one reply shape of every tool. Units: sizes in bytes, durations in milliseconds.
Errors: invalid content raises `pydantic.ValidationError`.
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Discriminator, Field, JsonValue, StringConstraints, Tag, model_validator

from eng_contract._types import FieldPath, KindName, Sha256Hex
from eng_contract.canonical import CanonicalJsonError, canonical_json
from eng_contract.errors import ContractError, ContractWarning, ErrorDetail, WarningCode
from eng_contract.ids import ModelId, ResultId, Timestamp

if TYPE_CHECKING:
    from eng_contract.records import ResultRecord

SUMMARY_LIMIT_BYTES = 4096
"""Largest canonical `summary` (spec 4.2.5 rule 1)."""
INLINE_DATA_LIMIT_BYTES = 16384
"""Largest canonical inline `data` (spec 4.2.5 rule 2)."""

_MODEL = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=False)
# Local form of `RefString` (spec 4.6.1): a result id, optionally followed by `#` and a pointer.
_RefText = Annotated[str, StringConstraints(pattern=r"^res_[0-7][0-9A-HJKMNP-TV-Z]{25}(#.*)?$", max_length=2000)]
_Tool = Annotated[
    str,
    StringConstraints(max_length=200, pattern=r"^([a-z0-9][a-z0-9-]*/[a-z0-9_.-]+|engineer|template|harness)$"),
]


class HostInfo(BaseModel):
    """Host program a result was read from (spec 4.2.2)."""

    model_config = _MODEL

    program: str = Field(max_length=64)
    version: str = Field(max_length=64)
    model_id: ModelId
    model_revision: int = Field(ge=0)


class FileSource(BaseModel):
    """Input file a result was read from; the base name only, so no personal path is recorded."""

    model_config = _MODEL

    name: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\]+$")
    sha256: Sha256Hex
    size_bytes: int = Field(ge=0)


class RefInput(BaseModel):
    """Input taken from a stored result: `{"ref": RefString}`."""

    model_config = _MODEL

    ref: _RefText


class LiteralInput(BaseModel):
    """Input given as a value: `{"literal": JsonValue}` (null is a value)."""

    model_config = _MODEL

    literal: JsonValue


class Provenance(BaseModel):
    """How a result was produced (spec 4.2.2). `inputs` never re-types a referenced value."""

    model_config = _MODEL

    tool: _Tool
    tool_version: str = Field(max_length=64)
    host: HostInfo | None = None
    files: list[FileSource] = Field(default_factory=list)
    inputs: dict[FieldPath, RefInput | LiteralInput]
    started_at: Timestamp
    duration_ms: int = Field(ge=0)


def _size(value: JsonValue) -> int:
    try:
        return len(canonical_json(value))
    except CanonicalJsonError as exc:
        raise ValueError(str(exc)) from exc


class SuccessEnvelope(BaseModel):
    """Reply of a tool that succeeded (spec 4.2.5)."""

    model_config = _MODEL

    contract: Literal["eng-contract/1"]
    ok: Literal[True]
    result_id: ResultId
    kind: KindName
    summary: dict[str, JsonValue]
    data: JsonValue = None
    complete: bool
    warnings: list[ContractWarning] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode="after")
    def _check_rules(self) -> Self:
        if _size(self.summary) > SUMMARY_LIMIT_BYTES:
            raise ValueError(f"summary exceeds {SUMMARY_LIMIT_BYTES} bytes")
        if self.data is not None and _size(self.data) > INLINE_DATA_LIMIT_BYTES:
            raise ValueError(f"data exceeds {INLINE_DATA_LIMIT_BYTES} bytes")
        partial = any(w.code is WarningCode.PARTIAL_DATA for w in self.warnings)
        if partial is self.complete:
            raise ValueError("PARTIAL_DATA must be present if and only if complete is false")
        return self


class FailureEnvelope(BaseModel):
    """Reply of a tool that failed (spec 4.2.5)."""

    model_config = _MODEL

    contract: Literal["eng-contract/1"]
    ok: Literal[False]
    error: ErrorDetail


def _tag(value: Any) -> str | None:
    """Discriminator: the tag of a JSON boolean `ok`; anything else (missing, 0/1, text) has no tag."""
    ok = value.get("ok") if isinstance(value, dict) else getattr(value, "ok", None)
    if ok is True:
        return "success"
    if ok is False:
        return "failure"
    return None


Envelope = Annotated[
    Annotated[SuccessEnvelope, Tag("success")] | Annotated[FailureEnvelope, Tag("failure")],
    Discriminator(_tag),
]
"""Either envelope, chosen by the boolean `ok`."""


def make_success(
    record: ResultRecord, summary: dict[str, JsonValue], warnings: Iterable[ContractWarning] = ()
) -> SuccessEnvelope:
    """Build the success envelope of a stored record.

    `data` is the payload when its canonical form is at most `INLINE_DATA_LIMIT_BYTES`, else null.

    Raises:
        pydantic.ValidationError: the summary is too large or the warnings contradict `record.complete`.
    """
    payload = record.payload
    inline = payload is not None and len(canonical_json(payload)) <= INLINE_DATA_LIMIT_BYTES
    return SuccessEnvelope(
        contract="eng-contract/1",
        ok=True,
        result_id=record.result_id,
        kind=record.kind,
        summary=summary,
        data=payload if inline else None,
        complete=record.complete,
        warnings=list(warnings),
        provenance=record.producer,
    )


def make_failure(error: ErrorDetail | ContractError) -> FailureEnvelope:
    """Wrap an `ErrorDetail`, or the detail of a `ContractError`, in a failure envelope."""
    detail = error.detail if isinstance(error, ContractError) else error
    return FailureEnvelope(contract="eng-contract/1", ok=False, error=detail)
