"""Host replies as contract envelopes with limits and provenance (plan 0002 T8; spec 0002 section 4.5.3, AC19).

Purpose: parse the one JSON text block a Sasaah server sends, store the canonical-unit payload, and answer with a
success envelope: summary at most 4096 bytes, inline data only up to 16384 bytes (else in the store), `complete` false
with `PARTIAL_DATA` when the server reported `truncated`, and provenance with the tool, the build (from the
`ServerCheck`), the host program, the model id and revision, and the inputs as references.
Units: sizes in bytes, durations in milliseconds; payloads are already canonical. Errors: `ContractError`:
`HOST_ERROR` (host code `UNEXPECTED_REPLY`, spec 0002 A3) for a reply that is not one JSON object, `HOST_ERROR`
for an error reply that reached this layer (the error table of plan task T9 maps those first), `LIMIT_EXCEEDED` for
a summary over the limit, and the store's `INVALID_ARGUMENT` for a payload that is not valid for its kind.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from eng_contract.canonical import canonical_json
from eng_contract.envelope import (
    SUMMARY_LIMIT_BYTES,
    FileSource,
    HostInfo,
    LiteralInput,
    Provenance,
    RefInput,
    SuccessEnvelope,
    make_success,
)
from eng_contract.errors import ContractError, ContractWarning, ErrorCode, WarningCode
from eng_contract.ids import Timestamp
from eng_contract.mcp import extract_raw_reply
from eng_contract.store import ResultStore
from pydantic import BaseModel, ConfigDict, JsonValue

from eng_harness.adapters._args import referenced_results
from eng_harness.ports import ServerCheck

__all__ = ["HostReply", "make_envelope", "parse_reply"]

_HOST_CODE_MAX = 200


class HostReply(BaseModel):
    """A successful reply: its JSON object, and whether the server reported `truncated: true` (lists stop at 2000)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data: dict[str, JsonValue]
    truncated: bool


def parse_reply(result: Mapping[str, Any]) -> HostReply:
    """Parse an MCP tool result of a Sasaah server: exactly one text block holding a JSON object.

    Raises:
        ContractError: `HOST_ERROR` with the server's `code` as `host_code` for an `isError` reply, or with host code
            `UNEXPECTED_REPLY` for any other shape.
    """
    raw = extract_raw_reply(result)
    body = raw.json_texts[0] if raw.json_texts else None
    if raw.is_error:
        code = body.get("code") if isinstance(body, dict) else None
        host_code = code[:_HOST_CODE_MAX] if isinstance(code, str) else None
        raise ContractError(
            ErrorCode.HOST_ERROR, "the host replied with an error", retryable=False, host_code=host_code
        )
    if len(raw.texts) != 1 or raw.other_blocks or not isinstance(body, dict):
        raise ContractError(
            ErrorCode.HOST_ERROR, "the reply is not one JSON object", retryable=False, host_code="UNEXPECTED_REPLY"
        )
    return HostReply(data=body, truncated=body.get("truncated") is True)


def make_envelope(
    store: ResultStore,
    *,
    tool: str,
    kind: str,
    payload: dict[str, JsonValue],
    summary: dict[str, JsonValue],
    reply: HostReply,
    check: ServerCheck,
    host: HostInfo | None,
    inputs: Mapping[str, RefInput | LiteralInput],
    started_at: Timestamp,
    duration_ms: int,
    files: Sequence[FileSource] = (),
) -> SuccessEnvelope:
    """Store `payload` (canonical units) as a `kind` result and return its success envelope.

    `tool` is `<adapter>/<tool>`; the build in the provenance is `check.build`; the parents of the result are the
    results `inputs` refer to.

    Raises:
        ContractError: `LIMIT_EXCEEDED` (summary over 4096 bytes), `INVALID_ARGUMENT` (payload not valid for `kind`).
    """
    if len(canonical_json(summary)) > SUMMARY_LIMIT_BYTES:
        raise ContractError(ErrorCode.LIMIT_EXCEEDED, f"summary exceeds {SUMMARY_LIMIT_BYTES} bytes")
    producer = Provenance(
        tool=tool,
        tool_version=check.build,
        host=host,
        files=list(files),
        inputs=dict(inputs),
        started_at=started_at,
        duration_ms=duration_ms,
    )
    record = store.put(kind, payload, producer, parents=referenced_results(inputs), complete=not reply.truncated)
    partial = ContractWarning(
        code=WarningCode.PARTIAL_DATA, message="the host reply was truncated: lists are capped at 2000 with no paging"
    )
    return make_success(record, summary, [partial] if reply.truncated else [])
