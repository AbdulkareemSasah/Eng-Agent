"""Conformance of the fake decision providers and the shape of the provider error types (spec 0005 AC41, section 4.7).

The fakes are bound to the `DecisionProvider` and `LLMProvider` protocols by typed assignment (checked by mypy) and
driven through each method; the error types are asserted exactly as spec 0005 section 4.7 and spec 0009 section 4.3
define them.
"""

import asyncio
from collections.abc import Mapping

import pytest
from fakes.decision_providers import FakeDecisionProvider, FakeLLMProvider
from pydantic import ValidationError

from eng_harness.decisions.interfaces import (
    ChoiceAnswer,
    DecisionAnswer,
    DecisionCall,
    DecisionProvider,
    DecisionScreen,
    EngineerChoice,
    LLMAnswer,
    LLMProvider,
    OutgoingPlace,
    PendingAnswer,
    ProviderError,
    ProviderErrorCode,
    ProviderFailure,
    ProviderInfo,
    ProviderOption,
    ProviderRequest,
    Suggestion,
    YesNoAnswer,
)

_REQUEST = ProviderRequest(
    request_id="dec_1",
    point="footing_fix_strategy",
    point_version=1,
    options=(ProviderOption(value="enlarge", label="Enlarge the plan"), ProviderOption(value="deepen", label="Deepen")),
    state={"governing": "bearing"},
)


def test_fake_providers_conform() -> None:
    scores: Mapping[str, float] = {"enlarge": 0.75, "deepen": 0.25}
    model: DecisionProvider = FakeDecisionProvider(
        choices=[
            ChoiceAnswer(choice="enlarge", confidence=0.9),
            ChoiceAnswer(choice="deepen", confidence=0.8),
            ProviderError(ProviderErrorCode.TIMEOUT),
        ],
        yes_nos=[YesNoAnswer(answer=True, confidence=0.95)],
        scores=[scores],
    )
    llm: LLMProvider = FakeLLMProvider(answers=[LLMAnswer(choice="deepen", rationale="Only depth is short.")])
    assert isinstance(model.info, ProviderInfo)
    assert model.info.supports_batch is True
    assert asyncio.run(model.choose(_REQUEST)) == ChoiceAnswer(choice="enlarge", confidence=0.9)
    assert asyncio.run(model.yes_no(_REQUEST)) == YesNoAnswer(answer=True, confidence=0.95)
    assert asyncio.run(model.score(_REQUEST)) == scores
    batch = asyncio.run(model.batch([_REQUEST, _REQUEST]))
    assert batch == [ChoiceAnswer(choice="deepen", confidence=0.8), ProviderFailure(code=ProviderErrorCode.TIMEOUT)]
    answer = asyncio.run(llm.decide(_REQUEST))
    assert answer == LLMAnswer(choice="deepen", rationale="Only depth is short.")
    assert isinstance(model, FakeDecisionProvider)
    assert len(model.requests) == 5
    assert isinstance(llm, FakeLLMProvider)
    assert llm.requests == [_REQUEST]


def test_fake_provider_raises_scripted_failure() -> None:
    model = FakeDecisionProvider(choices=[ProviderError(ProviderErrorCode.RATE_LIMITED)])
    with pytest.raises(ProviderError) as caught:
        asyncio.run(model.choose(_REQUEST))
    assert caught.value.code is ProviderErrorCode.RATE_LIMITED
    with pytest.raises(ProviderError) as exhausted:
        asyncio.run(model.choose(_REQUEST))
    assert exhausted.value.code is ProviderErrorCode.NOT_IMPLEMENTED


def test_provider_error_shape() -> None:
    assert {member.name: member.value for member in ProviderErrorCode} == {
        "NO_KEY": "no_key",
        "CREDENTIAL_STORE": "credential_store",
        "NETWORK": "network",
        "TIMEOUT": "timeout",
        "AUTH": "auth",
        "RATE_LIMITED": "rate_limited",
        "HTTP_STATUS": "http_status",
        "BAD_RESPONSE": "bad_response",
        "INVALID_OUTPUT": "invalid_output",
        "REDACTION_BLOCKED": "redaction_blocked",
        "NOT_IMPLEMENTED": "not_implemented",
    }
    assert {member.name: member.value for member in OutgoingPlace} == {
        "POINT": "point",
        "OPTION_VALUE": "option_value",
        "OPTION_LABEL": "option_label",
        "STATE_KEY": "state_key",
        "STATE_VALUE": "state_value",
        "KEY_MATERIAL": "key_material",
    }
    plain = ProviderError(ProviderErrorCode.AUTH)
    assert isinstance(plain, Exception)
    assert str(plain) == "auth"
    assert (plain.code, plain.gap, plain.where) == (ProviderErrorCode.AUTH, None, None)
    gap = ProviderError(ProviderErrorCode.NOT_IMPLEMENTED, gap="J-G1")
    assert (str(gap), gap.gap, gap.where) == ("not_implemented", "J-G1", None)
    blocked = ProviderError(ProviderErrorCode.REDACTION_BLOCKED, where=OutgoingPlace.STATE_VALUE)
    assert (str(blocked), blocked.where) == ("redaction_blocked", OutgoingPlace.STATE_VALUE)
    with pytest.raises(ValueError, match="where"):
        ProviderError(ProviderErrorCode.NETWORK, where=OutgoingPlace.POINT)
    with pytest.raises(ValueError, match="gap"):
        ProviderError(ProviderErrorCode.NETWORK, gap="J-G1")
    failure = ProviderFailure(code=ProviderErrorCode.BAD_RESPONSE)
    assert set(ProviderFailure.model_fields) == {"code"}
    with pytest.raises(ValidationError):
        failure.code = ProviderErrorCode.AUTH


def test_provider_request_carries_no_sensitive_values() -> None:
    assert set(ProviderRequest.model_fields) == {"request_id", "point", "point_version", "options", "state"}
    with pytest.raises(ValidationError):
        ProviderRequest.model_validate({**_REQUEST.model_dump(), "sensitive_values": ["x"]})
    with pytest.raises(ValidationError):
        _REQUEST.point = "other"


def test_answer_bounds() -> None:
    with pytest.raises(ValidationError):
        ChoiceAnswer(choice="a", confidence=1.5)
    with pytest.raises(ValidationError):
        YesNoAnswer(answer=True, confidence=float("nan"))
    with pytest.raises(ValidationError):
        LLMAnswer(choice="a", rationale="Needs 12 mm")  # a digit in a rationale is refused (Rationale)


def test_port_models_shape() -> None:
    assert DecisionCall.model_fields["sensitive_values"].default == ()
    assert set(DecisionCall.model_fields) == {
        "request_id",
        "run_id",
        "step_path",
        "point",
        "options",
        "state",
        "rules",
        "policy",
        "basis",
        "engineer_choice",
        "sensitive_values",
    }
    assert set(DecisionAnswer.model_fields) == {
        "choice",
        "decided_by",
        "confidence",
        "latency_ms",
        "options",
        "state_sha256",
        "suggestions",
    }
    assert set(PendingAnswer.model_fields) == {"request_id", "batch_id", "screen", "rejected"}
    assert set(EngineerChoice.model_fields) == {"choice", "by", "answered_at"}
    assert "items" in DecisionScreen.model_fields
    assert set(Suggestion.model_fields) >= {"tier", "by", "outcome", "choice", "confidence", "rationale", "shadow"}
    with pytest.raises(ValidationError):
        Suggestion.model_validate(
            {"tier": 2, "by": "model:p/m@1", "outcome": "bogus", "choice": None, "latency_ms": 1, "shadow": True}
        )
