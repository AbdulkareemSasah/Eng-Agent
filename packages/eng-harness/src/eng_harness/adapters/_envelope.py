"""Host replies as contract envelopes (plan 0002 T8; spec 0002 section 4.5.3, AC19).

Purpose: parse a Sasaah reply (one JSON text block), store the canonical payload and answer with an envelope: summary
at most 4096 bytes, inline data up to 16384 bytes, `PARTIAL_DATA` on `truncated`, provenance with the build.
Units: bytes and milliseconds. Errors: `ContractError` `HOST_ERROR` (host code `UNEXPECTED_REPLY`, spec 0002 A3, or
the server's code for an error reply, which T9's table maps first), `LIMIT_EXCEEDED`, `INVALID_ARGUMENT` (payload).
"""

from collections.abc import Mapping
from typing import Any

from eng_contract.canonical import canonical_json
from eng_contract.envelope import (
    SUMMARY_LIMIT_BYTES,
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
from eng_contract.refs import parse_ref
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness.ports import ServerCheck


def parse_reply(result: Mapping[str, Any]) -> dict[str, JsonValue]:
    """The JSON object of a tool result that holds exactly one text block and no error.

    Raises:
        ContractError: `HOST_ERROR` with the server's `code` for an `isError` reply, else with host code
            `UNEXPECTED_REPLY` for any other shape.
    """
    raw = extract_raw_reply(result)
    body = raw.json_texts[0] if raw.json_texts else None
    if raw.is_error or len(raw.texts) != 1 or raw.other_blocks or not isinstance(body, dict):
        code = (body.get("code") if raw.is_error and isinstance(body, dict) else None) or "UNEXPECTED_REPLY"
        raise ContractError(
            ErrorCode.HOST_ERROR, "the host reply is not a success", retryable=False, host_code=str(code)[:200]
        )
    return body


def make_envelope(
    store: ResultStore,
    *,
    tool: str,
    kind: str,
    payload: dict[str, JsonValue],
    summary: dict[str, JsonValue],
    reply: Mapping[str, JsonValue],
    check: ServerCheck,
    host: HostInfo | None,
    inputs: Mapping[str, RefInput | LiteralInput],
    started_at: Timestamp,
    duration_ms: int,
) -> SuccessEnvelope:
    """Store `payload` (canonical units) as a `kind` result; `tool` is `<adapter>/<tool>`, the build is `check.build`.

    A `reply` with `truncated: true` makes the result incomplete, with `PARTIAL_DATA` (lists stop at 2000).

    Raises:
        ContractError: `LIMIT_EXCEEDED` (summary over 4096 bytes), `INVALID_ARGUMENT` (payload invalid for `kind`).
    """
    if len(canonical_json(summary)) > SUMMARY_LIMIT_BYTES:
        raise ContractError(ErrorCode.LIMIT_EXCEEDED, f"summary exceeds {SUMMARY_LIMIT_BYTES} bytes")
    producer = Provenance(
        tool=tool,
        tool_version=check.build,
        host=host,
        inputs=dict(inputs),
        started_at=started_at,
        duration_ms=duration_ms,
    )
    truncated = reply.get("truncated") is True
    parents = dict.fromkeys(parse_ref(i.ref)[0] for i in inputs.values() if isinstance(i, RefInput))
    record = store.put(kind, payload, producer, parents=list(parents), complete=not truncated)
    note = "the host reply was truncated: lists stop at 2000 with no paging"
    warnings = [ContractWarning(code=WarningCode.PARTIAL_DATA, message=note)] if truncated else []
    return make_success(record, summary, warnings)
