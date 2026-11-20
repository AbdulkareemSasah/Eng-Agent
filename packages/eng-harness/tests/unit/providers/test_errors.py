"""Provider error types (spec 0009 AC5): a regression test of the types built by plan 0005 T5."""

import pytest
from pydantic import ValidationError

from eng_harness.decisions.interfaces import OutgoingPlace, ProviderError, ProviderErrorCode, ProviderFailure

CODES = {
    "no_key",
    "credential_store",
    "network",
    "timeout",
    "auth",
    "rate_limited",
    "http_status",
    "bad_response",
    "invalid_output",
    "redaction_blocked",
    "not_implemented",
}


def test_error_shape() -> None:
    assert {c.value for c in ProviderErrorCode} == CODES
    for code in ProviderErrorCode:
        assert str(ProviderError(code)) == code.value
    gap = ProviderError(ProviderErrorCode.NOT_IMPLEMENTED, gap="J-G1")
    assert str(gap) == "not_implemented"
    assert gap.gap == "J-G1"
    blocked = ProviderError(ProviderErrorCode.REDACTION_BLOCKED, where=OutgoingPlace.STATE_KEY)
    assert str(blocked) == "redaction_blocked"
    assert blocked.where is OutgoingPlace.STATE_KEY
    with pytest.raises(ValueError, match="gap"):
        ProviderError(ProviderErrorCode.NETWORK, gap="J-G1")
    with pytest.raises(ValueError, match="where"):
        ProviderError(ProviderErrorCode.NETWORK, where=OutgoingPlace.POINT)
    failure = ProviderFailure(code=ProviderErrorCode.TIMEOUT)
    with pytest.raises(ValidationError):
        failure.code = ProviderErrorCode.AUTH
