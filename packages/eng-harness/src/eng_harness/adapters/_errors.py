"""Host error replies and the wedged host (plan 0002 T9; spec 0002 4.5.5, 4.5.6, AC20, AC21).

Purpose: read an error reply of a host server (`ErrorReply`), map it to a contract `ErrorDetail` (`HostErrorMapper`, one
per adapter), and keep the wedged state of a host (`HostHealth`). Units: none. Errors: `ContractError` `HOST_WEDGED`
from `HostHealth.check`.
"""

from collections import defaultdict
from collections.abc import Mapping
from typing import Any, Protocol

from eng_contract.errors import ContractError, ErrorCode, ErrorDetail
from eng_contract.mcp import extract_raw_reply
from pydantic import BaseModel, ConfigDict, JsonValue

from eng_harness.servers import CallEffect

__all__ = ["WEDGING_CODES", "ErrorReply", "HostErrorMapper", "HostHealth", "parse_error_reply"]

WEDGING_CODES = frozenset(
    {ErrorCode.TIMEOUT_NO_EFFECT, ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, ErrorCode.HOST_NOT_CONNECTED}
)
"""Codes after which the host is wedged: a timeout, a backstop, a crash or a reconnect (spec 4.5.6)."""


class ErrorReply(BaseModel):
    """An `isError` reply: the server's `code` (`None` when the text carries none), its message and `data`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str | None
    message: str
    data: dict[str, JsonValue]


class HostErrorMapper(Protocol):
    """An adapter's table from host error replies to contract error details."""

    def map(self, reply: ErrorReply, *, effect: CallEffect, tool: str, op_id: str) -> ErrorDetail:
        """The contract error for `reply` of `tool`; an unknown outcome carries `op_id`."""


def parse_error_reply(result: Mapping[str, Any]) -> ErrorReply | None:
    """The error of a tool result, or `None` when it is not an `isError` result."""
    raw = extract_raw_reply(result)
    if not raw.is_error:
        return None
    body = raw.json_texts[0] if len(raw.json_texts) == 1 else None
    code = body.get("code") if isinstance(body, dict) else None
    if isinstance(body, dict) and isinstance(code, str):
        data = body.get("data")
        message = body.get("message")
        return ErrorReply(
            code=code,
            message=message if isinstance(message, str) else "",
            data=data if isinstance(data, dict) else {},
        )
    return ErrorReply(code=None, message="\n".join(raw.texts), data={})


class HostHealth:
    """Which hosts are wedged, by which operation, and the epoch increases the adapter made itself."""

    def __init__(self) -> None:
        """Start with no wedged host."""
        self._wedged: dict[str, str] = {}
        self._bumps: defaultdict[str, int] = defaultdict(int)

    def wedged(self, host_key: str) -> str | None:
        """The op id that wedged the host, `None` when it is not wedged."""
        return self._wedged.get(host_key)

    def epoch_bumps(self, host_key: str) -> int:
        """Epoch increases made by the adapter, added to the session's own count (a server `timeout` reply)."""
        return self._bumps[host_key]

    def mark_wedged(self, host_key: str, op_id: str, *, bump_epoch: bool) -> None:
        """Wedge the host for `op_id`; `bump_epoch` when the session did not already increase its epoch."""
        self._wedged.setdefault(host_key, op_id)
        if bump_epoch:
            self._bumps[host_key] += 1

    def reconciled(self, op_id: str) -> None:
        """The engine reconciled `op_id`: every host it wedged is free again."""
        for key in [k for k, v in self._wedged.items() if v == op_id]:
            del self._wedged[key]

    def check(self, host_key: str) -> None:
        """Raise `HOST_WEDGED` (nothing is sent) while the host waits for the reconciliation of an operation."""
        if (op_id := self._wedged.get(host_key)) is not None:
            raise ContractError(ErrorCode.HOST_WEDGED, f"host {host_key} is wedged until {op_id} is reconciled")
