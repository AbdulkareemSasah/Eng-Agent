"""Revit error table and timeout text rules (plan 0011 T5; spec 0011 AC6, §4.7).

Expected values are the rows of spec 0011 §4.7 written out here, not read back from the code under test.
Certainty on a write: only texts a resend cannot produce are certain not-applied; consumed-token and
"NOT executed" are TIMEOUT_UNKNOWN_OUTCOME (reconcile).
"""

from typing import Any, Literal

import pytest
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource

from eng_harness.adapters._errors import ErrorReply
from eng_harness.servers import CallEffect

R, W = CallEffect.READ, CallEffect.WRITE
C = ErrorCode
Certainty = Literal["not_applied", "unknown"]

# (sasaah code, message, effect, contract code, retryable, host_code, write certainty or None on read)
ROWS: list[tuple[str | None, str, CallEffect, ErrorCode, bool, str | None, Certainty | None]] = [
    ("invalid_request", "Element 7 was not found.", R, C.NOT_FOUND, False, None, None),
    ("invalid_request", "Element 7 was not found.", W, C.NOT_FOUND, False, None, "not_applied"),
    ("invalid_request", "Parameter X not found on element.", W, C.NOT_FOUND, False, None, "not_applied"),
    ("invalid_request", "path is required.", W, C.INVALID_ARGUMENT, False, None, "not_applied"),
    (
        "forbidden_destructive",
        "Destructive operation was not confirmed in Revit. declined by the user",
        W,
        C.CONFIRMATION_REQUIRED,
        False,
        None,
        "not_applied",
    ),
    (
        "forbidden_destructive",
        "Invalid or already consumed confirmation token",
        W,
        C.TIMEOUT_UNKNOWN_OUTCOME,
        False,
        None,
        "unknown",
    ),
    ("bridge_busy", "bridge is busy", W, C.HOST_BUSY, True, None, "not_applied"),
    ("bridge_busy", "bridge is busy", R, C.HOST_BUSY, True, None, None),
    ("timeout", "revit_list_levels was NOT executed", R, C.TIMEOUT_NO_EFFECT, True, None, None),
    (
        "timeout",
        "revit_set_element_parameter_values was NOT executed",
        W,
        C.TIMEOUT_UNKNOWN_OUTCOME,
        False,
        None,
        "unknown",
    ),
    (
        "timeout",
        "prepare_destructive is already executing",
        W,
        C.HOST_BUSY,
        True,
        "MODAL_DIALOG",
        "not_applied",
    ),
    (
        "timeout",
        "revit_set_element_parameter_values is already executing",
        R,
        C.TIMEOUT_NO_EFFECT,
        True,
        None,
        None,
    ),
    (
        "timeout",
        "revit_set_element_parameter_values is already executing",
        W,
        C.TIMEOUT_UNKNOWN_OUTCOME,
        False,
        None,
        "unknown",
    ),
    ("cancelled", "cancelled", R, C.TIMEOUT_NO_EFFECT, True, None, None),
    ("cancelled", "cancelled", W, C.TIMEOUT_UNKNOWN_OUTCOME, False, None, "unknown"),
    ("bridge_unavailable", "bridge down", R, C.HOST_NOT_CONNECTED, True, None, None),
    ("bridge_unavailable", "bridge down", W, C.HOST_NOT_CONNECTED, True, None, "not_applied"),
    (
        None,
        "Unknown tool or Revit bridge is not reachable.",
        W,
        C.HOST_NOT_CONNECTED,
        True,
        None,
        "not_applied",
    ),
    (
        "internal_error",
        "duplicate_family_type did not commit the transaction",
        W,
        C.HOST_ERROR,
        False,
        "TRANSACTION_NOT_COMMITTED",
        "not_applied",
    ),
    ("internal_error", "something else failed", R, C.INTERNAL, False, None, None),
    ("internal_error", "something else failed", W, C.TIMEOUT_UNKNOWN_OUTCOME, False, None, "unknown"),
    ("compile_error", "bad allowlist script", R, C.INTERNAL, False, None, None),
    ("runtime_exception", "null ref", W, C.INTERNAL, False, None, "not_applied"),
    (None, "RESPONSE_TOO_LARGE: the reply exceeded the transport limit.", R, C.LIMIT_EXCEEDED, False, None, None),
]  # fmt: skip


def _mapper() -> Any:
    from eng_harness.adapters.revit._errors import RevitErrorMapper

    return RevitErrorMapper(SeededIdSource(b"revit-errors", FixedClock(1_767_225_600_000, 1)))


def _map(code: str | None, message: str, effect: CallEffect) -> Any:
    from eng_harness.adapters.revit._errors import write_certainty

    reply = ErrorReply(code=code, message=message, data={})
    detail = _mapper().map(reply, effect=effect, tool="revit_set_element_parameter_values", op_id="op-revit")
    certainty = write_certainty(detail) if effect is W else None
    return detail, certainty


@pytest.mark.parametrize(("code", "message", "effect", "want", "retryable", "host_code", "certainty"), ROWS)
def test_mapping_table(
    code: str | None,
    message: str,
    effect: CallEffect,
    want: ErrorCode,
    retryable: bool,
    host_code: str | None,
    certainty: Certainty | None,
) -> None:
    # AC6: contract code, retryable, host_code and applied/not-applied certainty as tabled (§4.7).
    detail, got_certainty = _map(code, message, effect)
    assert detail.code is want
    assert detail.retryable is retryable
    assert detail.host_code == host_code
    assert got_certainty == certainty
    if code is not None:
        assert code in detail.message.lower()
    # Declined dialog rewrites the message to "declined in Revit" (spec 0011 §4.7); others keep the host text.
    if want is C.CONFIRMATION_REQUIRED and "declined" in message.lower():
        assert "declined in Revit" in detail.message
    else:
        assert message.split()[0] in detail.message or message in detail.message
    assert (detail.incident_id is not None) is (want is C.INTERNAL)
    assert (detail.op_id == "op-revit") is (want is C.TIMEOUT_UNKNOWN_OUTCOME)


def test_timeout_text_rule() -> None:
    # AC6: "NOT executed" and "already executing" decide the timeout row; prepare_destructive → MODAL_DIALOG.
    from eng_harness.adapters.revit._errors import write_certainty

    not_exec_read, _ = _map("timeout", "revit_list_grids was NOT executed", R)
    assert not_exec_read.code is C.TIMEOUT_NO_EFFECT
    not_exec_write, certainty = _map("TIMEOUT", "revit_set_type_parameter_values was NOT executed", W)
    assert not_exec_write.code is C.TIMEOUT_UNKNOWN_OUTCOME
    assert certainty == "unknown"
    assert write_certainty(not_exec_write) == "unknown"

    dialog, dialog_certainty = _map("timeout", "prepare_destructive is already executing", W)
    assert dialog.code is C.HOST_BUSY
    assert dialog.host_code == "MODAL_DIALOG"
    assert dialog_certainty == "not_applied"

    write_busy, write_certainty_got = _map("timeout", "revit_set_element_parameter_values is already executing", W)
    assert write_busy.code is C.TIMEOUT_UNKNOWN_OUTCOME
    assert write_certainty_got == "unknown"


def test_unexpected_text_on_write() -> None:
    # AC6 / §4.7: code-less "unexpected error" on a write is TIMEOUT_UNKNOWN_OUTCOME (not INTERNAL).
    text = "The server encountered an unexpected error. Check stderr diagnostics."
    detail, certainty = _map(None, text, W)
    assert detail.code is C.TIMEOUT_UNKNOWN_OUTCOME
    assert certainty == "unknown"
    assert detail.op_id == "op-revit"
    read_detail, _ = _map(None, text, R)
    assert read_detail.code is C.INTERNAL
    assert read_detail.incident_id is not None


def test_consumed_token_and_not_executed_on_write_unknown() -> None:
    # AC6: on a write, consumed-token forbidden_destructive and "NOT executed" are unknown, not certain.
    from eng_harness.adapters.revit._errors import write_certainty

    for message in (
        "Invalid or already consumed confirmation token",
        "Token was prepared for a different operation",
        "confirmation token expired",
    ):
        detail, certainty = _map("forbidden_destructive", message, W)
        assert detail.code is C.TIMEOUT_UNKNOWN_OUTCOME, message
        assert certainty == "unknown", message
        assert write_certainty(detail) == "unknown"

    declined, declined_certainty = _map(
        "forbidden_destructive",
        "Destructive operation was not confirmed in Revit. declined by the user",
        W,
    )
    assert declined.code is C.CONFIRMATION_REQUIRED
    assert "declined in Revit" in declined.message
    assert declined_certainty == "not_applied"
    assert declined.retryable is False

    not_exec, not_exec_certainty = _map("timeout", "revit_duplicate_family_type was NOT executed", W)
    assert not_exec.code is C.TIMEOUT_UNKNOWN_OUTCOME
    assert not_exec_certainty == "unknown"


def test_code_token_is_case_insensitive() -> None:
    # AC6: the parser lowercases the code token.
    detail, _ = _map("Invalid_Request", "Element 1 was not found.", W)
    assert detail.code is C.NOT_FOUND
