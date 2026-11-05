"""CSI error table (plan 0002 T9; spec 0002 4.5.5, AC20, AC29 interim).

Expected values are the rows of the spec's S-12 table written out here, not read back from the code under test: each
row names the Sasaah code, the call effect and the contract code, `retryable` (the rule of eng-contract 04 section 8.1)
and the host fields.
"""

from typing import Any

import pytest
from eng_contract.errors import ErrorCode
from eng_contract.ids import SeededIdSource

from eng_harness.adapters._errors import ErrorReply
from eng_harness.adapters.csi._errors import CSI_ERROR_TABLE, CSI_NOT_FOUND_TEXTS, CsiErrorMapper
from eng_harness.servers import CallEffect

R, W = CallEffect.READ, CallEffect.WRITE
C = ErrorCode
# (sasaah code, effect, data, contract code, retryable, host_code, host_method)
ROWS: list[tuple[str, CallEffect, dict[str, Any] | None, ErrorCode, bool, str | None, str | None]] = [
    ("no_target", R, None, C.HOST_NOT_CONNECTED, True, None, None),
    ("no_target", W, None, C.HOST_NOT_CONNECTED, True, None, None),
    ("ambiguous_target", W, None, C.INVALID_ARGUMENT, False, None, None),
    ("target_disconnected", R, None, C.HOST_NOT_CONNECTED, True, None, None),
    ("target_disconnected", W, None, C.TIMEOUT_UNKNOWN_OUTCOME, False, None, None),
    ("timeout", R, None, C.TIMEOUT_NO_EFFECT, True, None, None),
    ("timeout", W, None, C.TIMEOUT_UNKNOWN_OUTCOME, False, None, None),
    ("com_worker_recycled", R, None, C.TIMEOUT_NO_EFFECT, True, None, None),
    ("com_worker_recycled", W, None, C.TIMEOUT_NO_EFFECT, True, None, None),
    ("unsupported_by_version", R, None, C.NOT_SUPPORTED_BY_VERSION, False, None, None),
    ("api_not_available", W, None, C.NOT_SUPPORTED_BY_VERSION, False, None, None),
    ("confirmation_required", W, None, C.CONFIRMATION_REQUIRED, False, None, None),
    ("model_locked", W, None, C.HOST_LOCKED, False, None, None),
    ("not_launched_by_server", W, None, C.CONFLICT, False, None, None),
    ("read_only", W, None, C.INTERNAL, False, None, None),
    ("script_disabled", R, None, C.INTERNAL, False, None, None),
    ("generic_invoke_disabled", R, None, C.INTERNAL, False, None, None),
    ("unsupported_operation", W, None, C.INTERNAL, False, None, None),
    ("csi_error", W, {"member": "SapObject.Foo", "return_code": 7}, C.HOST_ERROR, False, "7", "SapObject.Foo"),
    ("csi_error", R, {"member": "SapModel.Bar", "hresult": -2147467259}, C.HOST_ERROR, False, "-2147467259", "SapModel.Bar"),
    ("csi_error", R, {"member": "SapModel.Baz"}, C.INVALID_ARGUMENT, False, None, None),
]  # fmt: skip


def _mapper() -> CsiErrorMapper:
    return CsiErrorMapper(SeededIdSource(b"errors"))


def _map(code: str | None, effect: CallEffect, data: dict[str, Any] | None = None, message: str = "m") -> Any:
    reply = ErrorReply(code=code, message=message, data=data or {})
    return _mapper().map(reply, effect=effect, tool="csi_x", op_id="op-9")


@pytest.mark.parametrize(("code", "effect", "data", "want", "retryable", "host_code", "host_method"), ROWS)
def test_mapping_table(
    code: str, effect: CallEffect, data: Any, want: ErrorCode, retryable: bool, host_code: Any, host_method: Any
) -> None:
    # AC20: contract code, retryable, host_code and host_method as tabled
    detail = _map(code, effect, data, "original text")
    assert detail.code is want
    assert detail.retryable is retryable
    assert (detail.host_code, detail.host_method) == (host_code, host_method)
    assert code in detail.message and "original text" in detail.message  # the original code and message are kept
    assert (detail.incident_id is not None) is (want is C.INTERNAL)
    assert detail.precondition is None
    # the op_id travels with an unknown outcome so that the engine reconciles that operation
    assert (detail.op_id == "op-9") is (want is C.TIMEOUT_UNKNOWN_OUTCOME)


def test_every_sasaah_code_is_in_the_table() -> None:
    codes = {row[0] for row in ROWS}
    assert codes == set(CSI_ERROR_TABLE) | {"csi_error"}


@pytest.mark.parametrize("text", ["Load combination 'X' was not found. Use it.", "Object does not exist"])
def test_csi_error_without_data_not_found_texts(text: str) -> None:
    assert any(t in text for t in CSI_NOT_FOUND_TEXTS)
    assert _map("csi_error", R, None, text).code is C.NOT_FOUND
    assert _map("csi_error", W, {}, text).code is C.NOT_FOUND


def test_csi_error_without_data_other_text_is_invalid_argument() -> None:
    assert _map("csi_error", W, None, "name must not be empty").code is C.INVALID_ARGUMENT


def test_unexpected_text_is_internal_with_fresh_incident_ids() -> None:
    # Program.cs:102-106: the text carries no code
    text = "The server encountered an unexpected error. Check stderr diagnostics."
    mapper = _mapper()
    reply = ErrorReply(code=None, message=text, data={})
    first = mapper.map(reply, effect=R, tool="t", op_id="o")
    second = mapper.map(reply, effect=W, tool="t", op_id="o")
    assert first.code is second.code is C.INTERNAL
    assert first.incident_id and second.incident_id and first.incident_id != second.incident_id


def test_no_code_text_that_says_timed_out_on_a_write_is_unknown_outcome() -> None:
    reply = ErrorReply(code=None, message="The call timed out", data={})
    assert _mapper().map(reply, effect=W, tool="t", op_id="o").code is C.TIMEOUT_UNKNOWN_OUTCOME
    assert _mapper().map(reply, effect=R, tool="t", op_id="o").code is C.INTERNAL


def test_unknown_sasaah_code_is_internal() -> None:
    assert _map("brand_new_code", W).code is C.INTERNAL


def test_model_locked_interim() -> None:
    # AC29: until ADR-0031 is accepted the code is HOST_LOCKED, never retried, and no unlock is offered
    detail = _map("model_locked", W, None, "Model is locked")
    assert detail.code is C.HOST_LOCKED
    assert detail.retryable is False
    assert detail.precondition is None
    assert "unlock" not in (detail.hint or "").lower()
