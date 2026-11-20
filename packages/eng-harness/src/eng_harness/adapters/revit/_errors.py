"""The Revit error table (plan 0011 T5; spec 0011 AC6, §4.7).

Purpose: map a Sasaah Revit error reply (`"<code> <message> <hint>"`, S-12 §6) to a contract error. On a write,
only texts a resend cannot produce are certain not-applied; a consumed confirmation token or "NOT executed" is
`TIMEOUT_UNKNOWN_OUTCOME` and goes to reconciliation. Units: none. Errors: none raised; an unknown code is
`INTERNAL` with a new incident id.
"""

import logging
import re
from typing import Literal, NamedTuple

from eng_contract.errors import ContractError, ErrorCode, ErrorDetail
from eng_contract.ids import IdSource

from eng_harness.adapters._errors import ErrorReply
from eng_harness.servers import CallEffect

__all__ = [
    "REVIT_ERROR_TABLE",
    "RevitErrorMapper",
    "Row",
    "WriteCertainty",
    "parse_revit_error_text",
    "write_certainty",
]

_LOG = logging.getLogger(__name__)
_MAX = 200  # ErrorDetail.host_code limit
_SRC = "01_Core/Sasaah.Mcp.Protocol/Messages/ErrorCode.cs"  # S-12 §6 / spec 0011 §4.7

WriteCertainty = Literal["not_applied", "unknown"]

# Known Sasaah snake-case codes (spec 0011 §4.7); the parser lowercases and accepts a missing code.
_KNOWN_CODES = frozenset(
    {
        "invalid_request",
        "forbidden_destructive",
        "bridge_busy",
        "timeout",
        "cancelled",
        "bridge_unavailable",
        "internal_error",
        "compile_error",
        "runtime_exception",
    }
)
_CODE_PREFIX = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s+(.*)$", re.DOTALL)

_DECLINED_TEXTS = ("declined by the user",)
_CONSUMED_TOKEN_TEXTS = (
    "already consumed confirmation token",
    "token was prepared for",
    "expired",
)
_NOT_FOUND_TEXTS = ("was not found", "not found on element")
_NOT_EXECUTED = "was not executed"
_ALREADY_EXECUTING = "already executing"
_PREPARE_DESTRUCTIVE = "prepare_destructive"
_TRANSACTION_NOT_COMMITTED = "did not commit the transaction"
_UNEXPECTED = "the server encountered an unexpected error"
_BRIDGE_UNREACHABLE = "unknown tool or revit bridge is not reachable"
_RESPONSE_TOO_LARGE = "response_too_large"
_DECLINED_STANDALONE = "destructive operation was not confirmed in revit"


class Row(NamedTuple):
    """Contract code of a Sasaah code for a read and for a write; its Sasaah source."""

    read: ErrorCode
    write: ErrorCode
    source: str


def _same(code: ErrorCode, source: str) -> Row:
    return Row(code, code, source)


_C = ErrorCode
REVIT_ERROR_TABLE: dict[str, Row] = {
    "invalid_request": _same(_C.INVALID_ARGUMENT, f"{_SRC}; spec 0011 §4.7"),  # NOT_FOUND by text
    "forbidden_destructive": _same(_C.CONFIRMATION_REQUIRED, f"{_SRC}; spec 0011 §4.7"),  # or unknown by text
    "bridge_busy": _same(_C.HOST_BUSY, f"{_SRC}; spec 0011 §4.7"),
    "timeout": Row(_C.TIMEOUT_NO_EFFECT, _C.TIMEOUT_UNKNOWN_OUTCOME, "E/Runtime/MainThreadRequestQueue.cs; §4.7"),
    "cancelled": Row(_C.TIMEOUT_NO_EFFECT, _C.TIMEOUT_UNKNOWN_OUTCOME, f"{_SRC}; spec 0011 §4.7"),
    "bridge_unavailable": _same(_C.HOST_NOT_CONNECTED, f"{_SRC}; spec 0011 §4.7"),
    "internal_error": Row(_C.INTERNAL, _C.TIMEOUT_UNKNOWN_OUTCOME, f"{_SRC}; spec 0011 §4.7"),
    "compile_error": _same(_C.INTERNAL, f"{_SRC}; spec 0011 §4.7"),
    "runtime_exception": _same(_C.INTERNAL, f"{_SRC}; spec 0011 §4.7"),
}
"""Sasaah code to base contract codes; text rules in `RevitErrorMapper` refine the row."""

# Codes that prove a write was not applied (a resend cannot produce them as a false negative).
_CERTAIN_NOT_APPLIED = frozenset(
    {
        ErrorCode.NOT_FOUND,
        ErrorCode.INVALID_ARGUMENT,
        ErrorCode.CONFIRMATION_REQUIRED,
        ErrorCode.HOST_BUSY,
        ErrorCode.HOST_NOT_CONNECTED,
        ErrorCode.HOST_ERROR,  # TRANSACTION_NOT_COMMITTED rolls back
        ErrorCode.INTERNAL,  # compile/runtime allowlist bugs before a write effect
        ErrorCode.LIMIT_EXCEEDED,
    }
)


def write_certainty(detail: ErrorDetail) -> WriteCertainty:
    """`not_applied` when the mapped code is certain on a write; else `unknown` (reconcile)."""
    if detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME:
        return "unknown"
    if detail.code in _CERTAIN_NOT_APPLIED:
        return "not_applied"
    return "unknown"


def parse_revit_error_text(text: str) -> ErrorReply:
    """Split a Sasaah Revit error string into code and message; the code token is lowercased (§4.7)."""
    stripped = text.strip()
    match = _CODE_PREFIX.match(stripped)
    if match is not None:
        token, rest = match.group(1), match.group(2)
        if token.lower() in _KNOWN_CODES:
            return ErrorReply(code=token.lower(), message=rest, data={})
    return ErrorReply(code=None, message=stripped, data={})


class RevitErrorMapper:
    """Maps Revit error replies by the table of spec 0011 section 4.7."""

    def __init__(self, ids: IdSource) -> None:
        """`ids` gives the incident id of an `INTERNAL` error."""
        self._ids = ids

    def map(self, reply: ErrorReply, *, effect: CallEffect, tool: str, op_id: str) -> ErrorDetail:
        """The contract error for `reply`; the original code and message stay in the message (2000 characters)."""
        normalized = self._normalize(reply)
        code, extra, message = self._decide(normalized, effect=effect)
        shown = f"{normalized.code or 'no code'}: {message}"[:1990]
        if code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME:
            extra["op_id"] = op_id
        if code is ErrorCode.INTERNAL:
            extra["incident_id"] = self._ids.new_ulid()
            _LOG.error("unmapped host error", extra={"incident_id": extra["incident_id"], "tool": tool})
        # HOST_ERROR depends: force never-retry for the transaction-not-committed row; else leave default.
        retryable = False if code is ErrorCode.HOST_ERROR else None
        return ContractError(code, shown, retryable=retryable, **extra).detail

    @staticmethod
    def _normalize(reply: ErrorReply) -> ErrorReply:
        """Lowercase a known code; when `code` is missing, take it from the message prefix if present."""
        if reply.code is not None:
            lower = reply.code.lower()
            if lower in _KNOWN_CODES:
                return ErrorReply(code=lower, message=reply.message, data=reply.data)
            return ErrorReply(code=lower, message=reply.message, data=reply.data)
        return parse_revit_error_text(reply.message)

    def _decide(self, reply: ErrorReply, *, effect: CallEffect) -> tuple[ErrorCode, dict[str, object], str]:
        write = effect is CallEffect.WRITE
        lower_msg = reply.message.lower()
        extra: dict[str, object] = {}

        if reply.code is None:
            return self._no_code(lower_msg, reply.message, write=write)

        if reply.code == "invalid_request":
            if any(t in lower_msg for t in _NOT_FOUND_TEXTS):
                return ErrorCode.NOT_FOUND, extra, reply.message
            return ErrorCode.INVALID_ARGUMENT, extra, reply.message

        if reply.code == "forbidden_destructive" or _DECLINED_STANDALONE in lower_msg:
            if any(t in lower_msg for t in _DECLINED_TEXTS):
                return ErrorCode.CONFIRMATION_REQUIRED, extra, "declined in Revit"
            if write and any(t in lower_msg for t in _CONSUMED_TOKEN_TEXTS):
                return ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, extra, reply.message
            if write:
                return ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, extra, reply.message
            return ErrorCode.CONFIRMATION_REQUIRED, extra, reply.message

        if reply.code == "timeout":
            return self._timeout(lower_msg, reply.message, write=write, extra=extra)

        if reply.code == "internal_error":
            if _TRANSACTION_NOT_COMMITTED in lower_msg:
                extra["host_code"] = "TRANSACTION_NOT_COMMITTED"
                return ErrorCode.HOST_ERROR, extra, reply.message
            if write:
                return ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, extra, reply.message
            return ErrorCode.INTERNAL, extra, reply.message

        if (row := REVIT_ERROR_TABLE.get(reply.code)) is not None:
            return (row.write if write else row.read), extra, reply.message

        return ErrorCode.INTERNAL, extra, reply.message

    @staticmethod
    def _timeout(
        lower_msg: str, message: str, *, write: bool, extra: dict[str, object]
    ) -> tuple[ErrorCode, dict[str, object], str]:
        if _ALREADY_EXECUTING in lower_msg and _PREPARE_DESTRUCTIVE in lower_msg:
            extra["host_code"] = "MODAL_DIALOG"
            return ErrorCode.HOST_BUSY, extra, message
        if _ALREADY_EXECUTING in lower_msg:
            return (
                (ErrorCode.TIMEOUT_UNKNOWN_OUTCOME if write else ErrorCode.TIMEOUT_NO_EFFECT),
                extra,
                message,
            )
        if _NOT_EXECUTED in lower_msg:
            return (
                (ErrorCode.TIMEOUT_UNKNOWN_OUTCOME if write else ErrorCode.TIMEOUT_NO_EFFECT),
                extra,
                message,
            )
        # Default timeout row when the text carries no special marker.
        return (
            (ErrorCode.TIMEOUT_UNKNOWN_OUTCOME if write else ErrorCode.TIMEOUT_NO_EFFECT),
            extra,
            message,
        )

    def _no_code(self, lower_msg: str, message: str, *, write: bool) -> tuple[ErrorCode, dict[str, object], str]:
        extra: dict[str, object] = {}
        if _RESPONSE_TOO_LARGE in lower_msg:
            extra["hint"] = "narrow the request and retry"
            return ErrorCode.LIMIT_EXCEEDED, extra, message
        if _BRIDGE_UNREACHABLE in lower_msg:
            return ErrorCode.HOST_NOT_CONNECTED, extra, message
        if _DECLINED_STANDALONE in lower_msg and any(t in lower_msg for t in _DECLINED_TEXTS):
            return ErrorCode.CONFIRMATION_REQUIRED, extra, "declined in Revit"
        if _UNEXPECTED in lower_msg:
            # Read: HOST_NOT_CONNECTED when ping fails is decided by the caller via a later ping; unit default INTERNAL.
            if write:
                return ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, extra, message
            return ErrorCode.INTERNAL, extra, message
        if write:
            return ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, extra, message
        return ErrorCode.INTERNAL, extra, message
