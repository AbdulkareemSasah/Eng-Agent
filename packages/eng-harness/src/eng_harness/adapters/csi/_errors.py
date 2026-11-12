"""The CSI error table, S-12 section 6 (plan 0002 T9; spec 0002 4.5.5, AC20, AC29 interim).

Purpose: map a Sasaah CSI error reply to a contract error. Units: none. Errors: none raised; an unknown code or text is
`INTERNAL` with a new incident id. Interim (ADR-0031 not accepted): `model_locked` is `HOST_LOCKED` and
`not_launched_by_server` is `CONFLICT`; the switch task changes both rows.
"""

import logging
from typing import NamedTuple

from eng_contract.errors import ContractError, ErrorCode, ErrorDetail
from eng_contract.ids import IdSource

from eng_harness.adapters._errors import ErrorReply
from eng_harness.servers import CallEffect

__all__ = ["CSI_ERROR_TABLE", "CSI_NOT_FOUND_TEXTS", "CSI_TIMED_OUT_TEXTS", "CsiErrorMapper", "Row"]

_LOG = logging.getLogger(__name__)


class Row(NamedTuple):
    """Contract code of a Sasaah code for a read and for a write (save, analysis, design, unlock); its Sasaah source."""

    read: ErrorCode
    write: ErrorCode
    source: str


def _same(code: ErrorCode, source: str) -> Row:
    return Row(code, code, source)


_C = ErrorCode
_SRC = "02_Engines/Sasaah.Csi.Engine/CsiErrors.cs"
CSI_ERROR_TABLE: dict[str, Row] = {
    "no_target": _same(_C.HOST_NOT_CONNECTED, f"{_SRC}:32"),
    "ambiguous_target": _same(_C.INVALID_ARGUMENT, f"{_SRC}:33"),
    "target_disconnected": Row(_C.HOST_NOT_CONNECTED, _C.TIMEOUT_UNKNOWN_OUTCOME, f"{_SRC}:34"),
    "unsupported_by_version": _same(_C.NOT_SUPPORTED_BY_VERSION, f"{_SRC}:35"),
    "api_not_available": _same(_C.NOT_SUPPORTED_BY_VERSION, f"{_SRC}:36"),
    "confirmation_required": _same(_C.CONFIRMATION_REQUIRED, f"{_SRC}:37"),
    "read_only": _same(_C.INTERNAL, f"{_SRC}:38"),
    "script_disabled": _same(_C.INTERNAL, f"{_SRC}:39"),
    "timeout": Row(_C.TIMEOUT_NO_EFFECT, _C.TIMEOUT_UNKNOWN_OUTCOME, f"{_SRC}:40"),
    "com_worker_recycled": _same(_C.TIMEOUT_NO_EFFECT, "02_Engines/Sasaah.Csi.Engine/ComThread.cs:172"),
    "not_launched_by_server": _same(_C.CONFLICT, f"{_SRC}:43"),  # interim; PRECONDITION_FAILED after ADR-0031
    "unsupported_operation": _same(_C.INTERNAL, f"{_SRC}:44"),
    "model_locked": _same(_C.HOST_LOCKED, f"{_SRC}:45"),  # interim; PRECONDITION_FAILED after ADR-0031
    "generic_invoke_disabled": _same(_C.INTERNAL, f"{_SRC}:46"),
}
"""Sasaah code to contract codes; `csi_error` and replies without a code are decided by `CsiErrorMapper`."""

CSI_NOT_FOUND_TEXTS = (
    "was not found",  # CsiModel.cs:1538 and :2401 ("Load combination '...' was not found.")
    "does not exist",  # the example of spec 0002 4.5.5; no CSI engine line yet
)
"""Texts of a `csi_error` without data that mean the named object is absent."""

CSI_TIMED_OUT_TEXTS = ("timed out",)
"""Text of an unexpected error (Program.cs:102-106) that says the call timed out; a write is then an unknown outcome."""

_MAX = 200  # ErrorDetail.host_code and host_method limit


class CsiErrorMapper:
    """Maps CSI error replies by the table of spec 0002 4.5.5."""

    def __init__(self, ids: IdSource) -> None:
        """`ids` gives the incident id of an `INTERNAL` error."""
        self._ids = ids

    def map(self, reply: ErrorReply, *, effect: CallEffect, tool: str, op_id: str) -> ErrorDetail:
        """The contract error for `reply`; the original code and message stay in the message (2000 characters)."""
        shown = f"{reply.code or 'no code'}: {reply.message}"[:1990]
        write = effect is CallEffect.WRITE
        extra: dict[str, str] = {}
        if (row := CSI_ERROR_TABLE.get(reply.code or "")) is not None:
            code = row.write if write else row.read
        elif reply.code == "csi_error":
            code, extra = self._csi_error(reply)
        elif reply.code is None and write and any(t in reply.message.lower() for t in CSI_TIMED_OUT_TEXTS):
            code = ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
        else:
            code = ErrorCode.INTERNAL
        if code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME:
            extra["op_id"] = op_id
        if code is ErrorCode.INTERNAL:
            extra["incident_id"] = self._ids.new_ulid()
            _LOG.error("unmapped host error", extra={"incident_id": extra["incident_id"], "tool": tool})
        retryable = False if code is ErrorCode.HOST_ERROR else None
        return ContractError(code, shown, retryable=retryable, **extra).detail

    @staticmethod
    def _csi_error(reply: ErrorReply) -> tuple[ErrorCode, dict[str, str]]:
        """`HOST_ERROR` when the data names the member or a return code or HRESULT, else by the message text."""
        data = reply.data
        if not any(k in data for k in ("member", "return_code", "hresult")):
            if any(t in reply.message for t in CSI_NOT_FOUND_TEXTS):
                return ErrorCode.NOT_FOUND, {}
            return ErrorCode.INVALID_ARGUMENT, {}
        fields: dict[str, str] = {}
        if (value := data.get("return_code", data.get("hresult"))) is not None:
            fields["host_code"] = str(value)[:_MAX]
        if (member := data.get("member")) is not None:
            fields["host_method"] = str(member)[:_MAX]
        return ErrorCode.HOST_ERROR, fields
