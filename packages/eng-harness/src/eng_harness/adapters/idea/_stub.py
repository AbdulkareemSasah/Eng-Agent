"""Stub markers of IDEA calculate replies (plan 0014 T5; spec 0014 AC11).

Purpose: refuse any reply of `idea_calculate` / `idea_get_check_results` (and native calculate) that carries a
Sasaah offline-stub marker so invented utilizations never become host verdicts.
Units: none. Errors: `ContractError` `HOST_ERROR` with `host_code` `OFFLINE_STUB` (spec 0014 AC11, A1).
"""

from collections.abc import Mapping
from typing import Any

from eng_contract.errors import ContractError, ErrorCode

__all__ = ["OFFLINE_STUB_MESSAGE", "is_stub_reply", "refuse_stub"]

OFFLINE_STUB_MESSAGE = "Offline stub."
"""The `unity_check_message` of a Sasaah offline stub check (spec 0014 AC11; E/IdeaSession.cs)."""


def is_stub_reply(reply: Mapping[str, Any]) -> bool:
    """True when `reply` carries any AC11 stub marker.

    Markers: `offline_stub` absent or not `false`; on a non-native reply, `backend` not `"rest"`; a truthy `notice`;
    or any check whose `unity_check_message` is `"Offline stub."`. Native replies may carry `backend: null`.
    """
    if reply.get("offline_stub") is not False:
        return True
    notice = reply.get("notice")
    if notice:
        return True
    if reply.get("route") != "native" and reply.get("backend") != "rest":
        return True
    for connection in reply.get("connections") or ():
        if not isinstance(connection, Mapping):
            continue
        for check in connection.get("checks") or ():
            if isinstance(check, Mapping) and check.get("unity_check_message") == OFFLINE_STUB_MESSAGE:
                return True
    return False


def refuse_stub(reply: Mapping[str, Any], *, host_method: str | None = None) -> None:
    """Raise `HOST_ERROR` / `OFFLINE_STUB` when `reply` is a stub; otherwise return.

    Raises:
        ContractError: `HOST_ERROR` with `host_code` `OFFLINE_STUB` (AC11).
    """
    if not is_stub_reply(reply):
        return
    raise ContractError(
        ErrorCode.HOST_ERROR,
        "the host reply is an offline stub; no verdict is produced",
        retryable=False,
        host_code="OFFLINE_STUB",
        host_method=host_method,
    )
