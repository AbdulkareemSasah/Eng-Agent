"""IDEA error table (plan 0014 T4; spec 0014 AC17, section 4.8).

Expected values are the rows of the spec's S-12 / IdeaErrors.cs table written out here, not read back from the
code under test. A reply with no code is the unexpected-error row (S/Program.cs:105).
"""

from typing import Any

import pytest
from eng_contract.errors import ErrorCode, Precondition
from eng_contract.ids import FixedClock, SeededIdSource

from eng_harness.adapters._errors import ErrorReply
from eng_harness.adapters.idea._errors import IDEA_ERROR_TABLE, IdeaErrorMapper
from eng_harness.servers import CallEffect

R, W = CallEffect.READ, CallEffect.WRITE
C = ErrorCode
# (sasaah code, effect, tool, contract code, retryable, host_code, host_method, precondition, field)
ROWS: list[
    tuple[str | None, CallEffect, str, ErrorCode, bool, str | None, str | None, Precondition | None, str | None]
] = [
    ("no_project", R, "idea_list_connections", C.PRECONDITION_FAILED, False, None, None, Precondition.model_open, None),
    ("no_project", W, "idea_open_project", C.PRECONDITION_FAILED, False, None, None, Precondition.model_open, None),
    ("connection_not_found", R, "idea_get_check_results", C.NOT_FOUND, False, None, None, None, "connection"),
    ("connection_not_found", W, "idea_calculate", C.NOT_FOUND, False, None, None, None, "connection"),
    ("service_unavailable", R, "idea_status", C.HOST_NOT_CONNECTED, True, None, None, None, None),
    ("service_unavailable", W, "idea_calculate", C.HOST_NOT_CONNECTED, True, None, None, None, None),
    ("unsupported_by_version", R, "idea_status", C.NOT_SUPPORTED_BY_VERSION, False, None, None, None, None),
    ("api_not_available", W, "idea_open_project", C.NOT_SUPPORTED_BY_VERSION, False, None, None, None, None),
    ("timeout", R, "idea_list_connections", C.TIMEOUT_NO_EFFECT, True, None, None, None, None),
    ("timeout", R, "idea_native_calculate", C.TIMEOUT_NO_EFFECT, True, None, None, None, None),
    ("timeout", W, "idea_calculate", C.TIMEOUT_UNKNOWN_OUTCOME, False, None, None, None, None),
    ("timeout", W, "idea_native_set_loads", C.TIMEOUT_UNKNOWN_OUTCOME, False, None, None, None, None),
    ("iom_error", R, "idea_native_get_loads", C.HOST_ERROR, False, "iom_error", "idea_native_get_loads", None, None),
    ("idea_error", W, "idea_native_set_loads", C.HOST_ERROR, False, "idea_error", "idea_native_set_loads", None, None),
    ("confirmation_required", W, "idea_calculate", C.CONFIRMATION_REQUIRED, False, None, None, None, None),
    ("read_only", W, "idea_open_project", C.INTERNAL, False, None, None, None, None),
    ("script_disabled", R, "idea_status", C.INTERNAL, False, None, None, None, None),
    (None, R, "idea_list_connections", C.INTERNAL, False, None, None, None, None),
    (None, W, "idea_calculate", C.TIMEOUT_UNKNOWN_OUTCOME, False, None, None, None, None),
    (None, R, "idea_native_calculate", C.TIMEOUT_UNKNOWN_OUTCOME, False, None, None, None, None),
]  # fmt: skip


def _mapper() -> IdeaErrorMapper:
    return IdeaErrorMapper(SeededIdSource(b"idea-errors", FixedClock(1_767_225_600_000, 1)))


def _map(
    code: str | None,
    effect: CallEffect,
    tool: str,
    *,
    message: str = "m",
    data: dict[str, Any] | None = None,
) -> Any:
    reply = ErrorReply(code=code, message=message, data=data or {})
    return _mapper().map(reply, effect=effect, tool=tool, op_id="op-idea")


@pytest.mark.parametrize(
    ("code", "effect", "tool", "want", "retryable", "host_code", "host_method", "precondition", "field"),
    ROWS,
)
def test_mapping_table(
    code: str | None,
    effect: CallEffect,
    tool: str,
    want: ErrorCode,
    retryable: bool,
    host_code: str | None,
    host_method: str | None,
    precondition: Precondition | None,
    field: str | None,
) -> None:
    # AC17: contract code, retryable, host_code, host_method and precondition as tabled
    text = "The server encountered an unexpected error." if code is None else "original host text"
    detail = _map(code, effect, tool, message=text)
    assert detail.code is want
    assert detail.retryable is retryable
    assert (detail.host_code, detail.host_method) == (host_code, host_method)
    assert detail.precondition is precondition
    assert detail.field == field
    assert (code or "no code") in detail.message
    assert text in detail.message
    assert (detail.incident_id is not None) is (want is C.INTERNAL)
    assert (detail.op_id == "op-idea") is (want is C.TIMEOUT_UNKNOWN_OUTCOME)


def test_every_sasaah_code_is_in_the_table() -> None:
    # S-12 §6 / IdeaErrors.cs:31-41, plus the no-code row exercised above
    codes = {row[0] for row in ROWS if row[0] is not None}
    assert codes == set(IDEA_ERROR_TABLE) | {"iom_error", "idea_error"}


def test_unknown_sasaah_code_is_internal() -> None:
    assert _map("brand_new_code", W, "idea_calculate").code is C.INTERNAL


def test_license_seat_hint_on_refusal_text() -> None:
    # §4.9: hint only when the host text contains licen or seat
    detail = _map(
        "service_unavailable",
        W,
        "idea_calculate",
        message="IDEA StatiCa service refused request: no license seat available.",
    )
    assert detail.code is C.HOST_NOT_CONNECTED
    assert detail.hint is not None
    assert "license seat" in detail.hint.lower()
    plain = _map("service_unavailable", W, "idea_calculate", message="service down")
    assert plain.hint is None
