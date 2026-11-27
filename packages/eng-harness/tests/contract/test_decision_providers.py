"""Conformance of the fake decision providers and the shape of the provider error types (spec 0005 AC41, section 4.7).

The fakes are bound to the `DecisionProvider` and `LLMProvider` protocols by typed assignment (checked by mypy) and
driven through each method; the error types are asserted exactly as spec 0005 section 4.7 and spec 0009 section 4.3
define them.
"""

import asyncio
from collections.abc import Callable, Coroutine, Mapping
from typing import Any

import httpx2
import pytest
from fakes.credential_stores import FakeCredentialStore
from fakes.decision_providers import FakeDecisionProvider, FakeLLMProvider
from fakes.jev_formats import FlatFormat
from fakes.recorded_providers import (
    REQUEST,
    RecordedDecisionProvider,
    RecordedLLMProvider,
    completion,
    llm_adapter,
    recording,
)
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
from eng_harness.providers._config import DecisionProviderConfig, LLMProviderConfig
from eng_harness.providers._http import ProviderClient
from eng_harness.providers._jev import JevProvider
from eng_harness.providers._jev_format import HttpCall
from eng_harness.providers._prompts import PROMPT_VERSION

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
    assert {"tier", "by", "outcome", "choice", "confidence", "reasoning", "shadow"} <= set(Suggestion.model_fields)
    assert Suggestion.model_fields["reasoning"].alias == "rationale"
    with pytest.raises(ValidationError):
        Suggestion.model_validate(
            {"tier": 2, "by": "model:p/m@1", "outcome": "bogus", "choice": None, "latency_ms": 1, "shadow": True}
        )


def test_suggestion_serializes_rationale_key_and_accepts_both_names() -> None:
    """Spec 4.9 names the journal key ``rationale``; dumps use it without by_alias, construction takes either name."""
    base = {"tier": 2, "by": "model:p/m@1", "outcome": "accepted", "choice": "a", "latency_ms": 1, "shadow": False}
    by_alias = Suggestion.model_validate({**base, "rationale": "Only depth is short."})
    by_name = Suggestion.model_validate({**base, "reasoning": "Only depth is short."})
    assert by_alias == by_name
    assert by_alias.model_dump()["rationale"] == "Only depth is short."
    assert "reasoning" not in by_alias.model_dump()
    assert '"rationale"' in by_alias.model_dump_json()


def test_adapters_conform() -> None:
    """AC27: the same success, failure and cancellation checks apply to recorded and SDK-backed providers."""
    type Ask = Callable[[ProviderRequest], Coroutine[Any, Any, ChoiceAnswer | LLMAnswer]]

    async def verify(ask: Ask, info: ProviderInfo, expected: ChoiceAnswer | LLMAnswer) -> None:
        assert isinstance(info, ProviderInfo)
        assert info.provider
        assert info.model
        assert info.version
        assert info.is_local is True
        assert info.supports_batch is isinstance(expected, ChoiceAnswer)
        result = await ask(REQUEST)
        assert type(result) is type(expected)
        assert result == expected
        with pytest.raises(ProviderError) as failed:
            await ask(REQUEST)
        assert failed.value.code is ProviderErrorCode.RATE_LIMITED

    async def cancel(ask: Ask, started: asyncio.Event | None = None) -> None:
        task = asyncio.create_task(ask(REQUEST))
        try:
            if started is None:
                await asyncio.sleep(0)  # recorded fake is now sleeping before delivering its answer
            else:
                await asyncio.wait_for(started.wait(), timeout=2)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    async def check() -> None:
        choice = ChoiceAnswer(choice="deepen", confidence=0.8)
        answer = LLMAnswer(choice="deepen", rationale="More depth is needed.")
        decision: DecisionProvider = RecordedDecisionProvider()
        llm: LLMProvider = RecordedLLMProvider()
        await verify(decision.choose, decision.info, choice)
        await verify(llm.decide, llm.info, answer)
        await cancel(RecordedDecisionProvider(delayed=True).choose)
        await cancel(RecordedLLMProvider(delayed=True).decide)

        started = asyncio.Event()
        responses = iter((200, 429))
        data = recording()

        async def replay(request: httpx2.Request) -> httpx2.Response:
            status = next(responses, None)
            if status is None:
                started.set()
                await asyncio.Future()
                pytest.fail("The parked transport returned")
            if status == 429:
                return httpx2.Response(status)
            return (
                completion(request)
                if request.url.path.endswith("/chat/completions")
                else httpx2.Response(status, json=data["jev"])
            )

        config = DecisionProviderConfig(
            name="synthetic",
            model="fixture-model",
            model_version="fixture",
            base_url="http://127.0.0.1:8080/v1",
            local=True,
            request_timeout_ms=1000,
        )
        store = FakeCredentialStore()
        client = ProviderClient(config, store, transport=httpx2.MockTransport(replay))
        try:
            jev = JevProvider(config, client, FlatFormat(HttpCall, [choice]))
            assert jev.info.version == "fixture;map-1"
            await verify(jev.choose, jev.info, choice)
            await cancel(jev.choose, started)
        finally:
            await client.aclose()
        started.clear()
        responses = iter((200, 429))
        llm_config = LLMProviderConfig.model_validate(
            config.model_dump(exclude={"backend"}) | {"max_output_tokens": 50}
        )
        async with llm_adapter(llm_config, store, replay) as adapter:
            assert adapter.info.version == f"fixture;prompt-{PROMPT_VERSION}"
            await verify(adapter.decide, adapter.info, answer)
            await cancel(adapter.decide, started)

    asyncio.run(check())
