"""The Jev wire-format boundary (spec 0009 section 4.6)."""

from collections.abc import Mapping, Sequence
from typing import Literal, Protocol
from urllib.parse import urlsplit

from eng_contract.errors import ContractError, ErrorCode
from pydantic import BaseModel, ConfigDict, JsonValue, field_validator

from eng_harness.decisions.interfaces import (
    ChoiceAnswer,
    ProviderError,
    ProviderErrorCode,
    ProviderFailure,
    ProviderRequest,
    YesNoAnswer,
)

type JevBackend = Literal["openrouter", "typesafe"]
type Operation = Literal["choose", "yes_no", "score", "batch"]
type ParsedAnswer = ChoiceAnswer | YesNoAnswer | Mapping[str, float] | ProviderFailure


class HttpCall(BaseModel):
    """A POST under the configured endpoint. The shared client supplies authentication."""

    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    method: Literal["POST"]
    path: str
    body: dict[str, JsonValue]

    @field_validator("method", mode="before")
    @classmethod
    def _post_only(cls, method: object) -> object:
        if method != "POST":
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "the format HTTP method must be POST", field="method")
        return method

    @field_validator("path")
    @classmethod
    def _endpoint_path(cls, path: str) -> str:
        parts = urlsplit(path)
        if parts.scheme or parts.netloc:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "the format must supply an endpoint path", field="path")
        return path


class JevFormat(Protocol):
    revision: int
    supports_batch: bool

    def build(self, op: Operation, requests: Sequence[ProviderRequest]) -> HttpCall: ...

    def parse(self, op: Operation, requests: Sequence[ProviderRequest], body: JsonValue) -> list[ParsedAnswer]:
        """Decode entries in request order. Raise BAD_RESPONSE if the response shape cannot be decoded."""


def select_format(backend: JevBackend) -> JevFormat:
    """Both configured backends await the S-07 report (AC16)."""
    error = ProviderError(ProviderErrorCode.NOT_IMPLEMENTED, gap="J-G1")
    error.add_note("Jev wire formats await spike S-07.")
    raise error
