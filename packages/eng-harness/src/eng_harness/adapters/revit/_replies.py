"""Revit success-reply parsing (plan 0011 T5; spec 0011 AC5, §4.5).

Purpose: parse a Sasaah Revit tool result with `eng_contract.mcp.extract_raw_reply`. A `_warning` member
added by the server (objects over 65536 bytes, `S/ResponseGuard.cs`) becomes a contract `HOST_WARNING` and is
stripped from the body. `truncated: true` makes the reply incomplete with `PARTIAL_DATA`. The code-less text
`RESPONSE_TOO_LARGE` raises `LIMIT_EXCEEDED` with the narrowing hint (§4.7).
Units: none. Errors: `ContractError` `LIMIT_EXCEEDED`, `HOST_ERROR` (`UNEXPECTED_REPLY`).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from eng_contract.errors import ContractError, ContractWarning, ErrorCode, WarningCode
from eng_contract.mcp import extract_raw_reply
from pydantic import JsonValue

__all__ = ["ParsedRevitReply", "parse_revit_reply"]

_NARROW_HINT = "narrow the request and retry"  # spec 0011 §4.7 RESPONSE_TOO_LARGE row


@dataclass(frozen=True)
class ParsedRevitReply:
    """A success reply body without `_warning`, its contract warnings, and whether the list is complete."""

    body: dict[str, JsonValue]
    warnings: tuple[ContractWarning, ...]
    complete: bool


def parse_revit_reply(result: Mapping[str, Any]) -> ParsedRevitReply:
    """Parse a Revit tool result: one JSON success object, or raise on `RESPONSE_TOO_LARGE` / bad shape.

    Raises:
        ContractError: `LIMIT_EXCEEDED` when the error text names `RESPONSE_TOO_LARGE`; `HOST_ERROR` with
            host code `UNEXPECTED_REPLY` for any other non-success shape.
    """
    raw = extract_raw_reply(result)
    if raw.is_error:
        text = "\n".join(raw.texts)
        if "RESPONSE_TOO_LARGE" in text:
            raise ContractError(ErrorCode.LIMIT_EXCEEDED, text[:1990], hint=_NARROW_HINT)
        raise ContractError(
            ErrorCode.HOST_ERROR, "the host reply is not a success", retryable=False, host_code="UNEXPECTED_REPLY"
        )
    body = raw.json_texts[0] if len(raw.json_texts) == 1 else None
    if len(raw.texts) != 1 or raw.other_blocks or not isinstance(body, dict):
        raise ContractError(
            ErrorCode.HOST_ERROR, "the host reply is not a success", retryable=False, host_code="UNEXPECTED_REPLY"
        )
    warnings: list[ContractWarning] = []
    data = dict(body)
    host_warning = data.pop("_warning", None)
    if isinstance(host_warning, str) and host_warning:
        warnings.append(ContractWarning(code=WarningCode.HOST_WARNING, message=host_warning[:2000]))
    complete = data.get("truncated") is not True
    if not complete:
        warnings.append(
            ContractWarning(code=WarningCode.PARTIAL_DATA, message="the host reply was truncated")
        )
    return ParsedRevitReply(body=data, warnings=tuple(warnings), complete=complete)
