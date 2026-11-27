"""The IDEA error table (plan 0014 T4; spec 0014 AC17 to AC19, sections 4.8 and 4.9).

Purpose: map a Sasaah IDEA error reply to a contract error. Units: none. Errors: none raised; an unknown code or a
text with no code on a read is `INTERNAL` with a new incident id. A hang that the client ends is the session backstop
(`call_timeout_s + client_grace_s`); this module only maps the reply shapes that reach it.
"""

import logging
from typing import NamedTuple

from eng_contract.errors import ContractError, ErrorCode, ErrorDetail, Precondition
from eng_contract.ids import IdSource

from eng_harness.adapters._errors import ErrorReply
from eng_harness.servers import CallEffect

__all__ = [
    "IDEA_ERROR_TABLE",
    "IDEA_HOST_ERROR_CODES",
    "IdeaErrorMapper",
    "Row",
    "license_seat_hint",
]

_LOG = logging.getLogger(__name__)

_SRC = "04_Deployments/Sasaah.Mcp.Idea.Server/IdeaErrors.cs"  # S-12 §6
_TIMEOUT_SRC = "04_Deployments/Sasaah.Mcp.Idea.Server/IdeaSession.cs:85-104"


class Row(NamedTuple):
    """Contract code of a Sasaah code for a read and for a write; its Sasaah source."""

    read: ErrorCode
    write: ErrorCode
    source: str


def _same(code: ErrorCode, source: str) -> Row:
    return Row(code, code, source)


_C = ErrorCode
IDEA_ERROR_TABLE: dict[str, Row] = {
    "no_project": _same(_C.PRECONDITION_FAILED, f"{_SRC}:31-41"),
    "connection_not_found": _same(_C.NOT_FOUND, f"{_SRC}:31-41"),
    "service_unavailable": _same(_C.HOST_NOT_CONNECTED, f"{_SRC}:31-41"),
    "unsupported_by_version": _same(_C.NOT_SUPPORTED_BY_VERSION, f"{_SRC}:31-41"),
    "api_not_available": _same(_C.NOT_SUPPORTED_BY_VERSION, f"{_SRC}:31-41"),
    "timeout": Row(_C.TIMEOUT_NO_EFFECT, _C.TIMEOUT_UNKNOWN_OUTCOME, _TIMEOUT_SRC),
    "confirmation_required": _same(_C.CONFIRMATION_REQUIRED, f"{_SRC}:31-41"),
    "read_only": _same(_C.INTERNAL, f"{_SRC}:31-41"),
    "script_disabled": _same(_C.INTERNAL, f"{_SRC}:31-41"),
}
"""Sasaah code to contract codes; `iom_error` / `idea_error` and no-code replies are decided by `IdeaErrorMapper`."""

IDEA_HOST_ERROR_CODES = frozenset({"iom_error", "idea_error"})
"""Sasaah codes that become `HOST_ERROR` with `host_code` and `host_method` the tool (spec 0014 §4.8)."""

# `idea_native_calculate` is analysis with allowlist effect `read` (save always false); a no-code reply is unknown.
_ANALYSIS_NO_CODE_TOOLS = frozenset({"idea_native_calculate"})

_MAX = 200  # ErrorDetail.host_code and host_method limit


def license_seat_hint(message: str) -> str | None:
    """A hint naming 'license seat' when the host text contains `licen` or `seat` (spec 0014 §4.9); else `None`."""
    lower = message.lower()
    if "licen" in lower or "seat" in lower:
        return "license seat may be unavailable (hint only; Sasaah has no license logic)"
    return None


class IdeaErrorMapper:
    """Maps IDEA error replies by the table of spec 0014 section 4.8."""

    def __init__(self, ids: IdSource) -> None:
        """`ids` gives the incident id of an `INTERNAL` error."""
        self._ids = ids

    def map(self, reply: ErrorReply, *, effect: CallEffect, tool: str, op_id: str) -> ErrorDetail:
        """The contract error for `reply`; the original code and message stay in the message (2000 characters)."""
        shown = f"{reply.code or 'no code'}: {reply.message}"[:1990]
        write = effect is CallEffect.WRITE
        extra: dict[str, object] = {}
        if (row := IDEA_ERROR_TABLE.get(reply.code or "")) is not None:
            code = row.write if write else row.read
            if reply.code == "no_project":
                extra["precondition"] = Precondition.model_open
            elif reply.code == "connection_not_found":
                extra["field"] = "connection"
        elif reply.code in IDEA_HOST_ERROR_CODES:
            code = ErrorCode.HOST_ERROR
            extra["host_code"] = str(reply.code)[:_MAX]
            extra["host_method"] = tool[:_MAX]
        elif reply.code is None:
            # unexpected error text (Program.cs:105): read → INTERNAL; write or analysis → unknown outcome
            code = ErrorCode.TIMEOUT_UNKNOWN_OUTCOME if write or tool in _ANALYSIS_NO_CODE_TOOLS else ErrorCode.INTERNAL
        else:
            code = ErrorCode.INTERNAL
        if code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME:
            extra["op_id"] = op_id
        if code is ErrorCode.INTERNAL:
            extra["incident_id"] = self._ids.new_ulid()
            _LOG.error("unmapped host error", extra={"incident_id": extra["incident_id"], "tool": tool})
        if (hint := license_seat_hint(reply.message)) is not None:
            extra["hint"] = hint
        retryable = False if code is ErrorCode.HOST_ERROR else None
        return ContractError(code, shown, retryable=retryable, **extra).detail
