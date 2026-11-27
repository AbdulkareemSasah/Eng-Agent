"""Spec 0009 AC14 and AC23–AC26 over the pinned SDK and a synthetic transport."""

import asyncio
import json
import logging
import traceback
from collections.abc import Callable

import httpx2
import pytest
from fakes.credential_stores import FakeCredentialStore
from fakes.recorded_providers import REQUEST, completion, llm_adapter
from pydantic import SecretStr, ValidationError
from pydantic_ai import models
from pydantic_ai.models.instrumented import InstrumentedModel

from eng_harness.decisions.interfaces import LLMAnswer, ProviderError, ProviderErrorCode
from eng_harness.providers._config import LLMProviderConfig

KEY = "synthetic-credential-marker"
REMOTE = "synthetic-response-body"
HEADER = "synthetic-header-value"
CONFIG = LLMProviderConfig(
    name="synthetic",
    model="fixture-model",
    model_version="fixture",
    base_url="https://model.invalid/v1",
    key_ref="fixture",
    request_timeout_ms=1000,
    max_output_tokens=50,
)


def _store() -> FakeCredentialStore:
    store = FakeCredentialStore()
    store.set("fixture", SecretStr(KEY))
    return store


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        {"choice": "other", "rationale": "Needs depth."},
        {"choice": "deepen", "rationale": "Value 1"},
        {"choice": "deepen", "rationale": "Value ١"},
        {"choice": "deepen", "rationale": ""},
        {"choice": "deepen", "rationale": "x" * 301},
        {"choice": "deepen", "rationale": "Needs depth.", "extra": True},
        {"choice": "deepen"},
        "plain text",
    ],
)
def test_valid_and_invalid_outputs(arguments: object) -> None:
    calls: list[httpx2.Request] = []

    def replay(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return completion(request, arguments)

    async def check() -> None:
        async with llm_adapter(CONFIG, _store(), replay) as adapter:
            if arguments is None:
                assert await adapter.decide(REQUEST) == LLMAnswer(choice="deepen", rationale="More depth is needed.")
            else:
                with pytest.raises(ProviderError) as error:
                    await adapter.decide(REQUEST)
                assert error.value.code is ProviderErrorCode.INVALID_OUTPUT
        assert len(calls) == 1

    asyncio.run(check())


def test_agent_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_instrumentation(*args: object, **kwargs: object) -> None:
        pytest.fail("The adapter invoked an instrumented model")

    def replay(request: httpx2.Request) -> httpx2.Response:
        with pytest.raises(RuntimeError, match="Model requests are not allowed"):
            models.check_allow_model_requests()
        (tool,) = json.loads(request.content)["tools"]
        assert tool["type"] == "function"
        assert tool["function"]["strict"] is True
        assert set(tool["function"]["parameters"]["properties"]) == {"choice", "rationale"}
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        return completion(request)

    async def check() -> None:
        async with llm_adapter(CONFIG, _store(), replay) as adapter:
            assert isinstance(await adapter.decide(REQUEST), LLMAnswer)
        async with llm_adapter(CONFIG, FakeCredentialStore(), replay) as adapter:
            with pytest.raises(ProviderError) as error:
                await adapter.decide(REQUEST)
            assert error.value.code is ProviderErrorCode.NO_KEY

    monkeypatch.setattr(InstrumentedModel, "request", unexpected_instrumentation)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-environment-credential")
    asyncio.run(check())


@pytest.mark.parametrize("cascade_timeout", [True, False])
def test_cancellation_and_ceiling(cascade_timeout: bool) -> None:
    async def check() -> None:
        tasks = asyncio.all_tasks()
        timeout = asyncio.timeout(None)
        cancelled = asyncio.Event()

        async def slow(_: httpx2.Request) -> httpx2.Response:
            if cascade_timeout:
                # Same timeout boundary as the cascade, expired once the request is in flight.
                timeout.reschedule(asyncio.get_running_loop().time())
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
            pytest.fail("The parked transport returned")

        config = CONFIG if cascade_timeout else CONFIG.model_copy(update={"request_timeout_ms": 100})
        async with llm_adapter(config, _store(), slow) as adapter:
            if cascade_timeout:
                with pytest.raises(TimeoutError):
                    async with timeout:
                        await adapter.decide(REQUEST)
                assert timeout.expired()
            else:
                with pytest.raises(ProviderError) as error:
                    await asyncio.wait_for(adapter.decide(REQUEST), timeout=2)
                assert error.value.code is ProviderErrorCode.TIMEOUT
            assert cancelled.is_set()
            assert asyncio.all_tasks() == tasks

    asyncio.run(check())


def test_local_and_remote_endpoints() -> None:
    calls: list[tuple[str, str | None]] = []

    def replay(request: httpx2.Request) -> httpx2.Response:
        calls.append((str(request.url), request.headers.get("Authorization")))
        return completion(request)

    async def check() -> None:
        local = LLMProviderConfig.model_validate(
            CONFIG.model_dump() | {"base_url": "http://127.0.0.1:8080/v1", "local": True, "key_ref": None},
        )
        for config, store in ((local, FakeCredentialStore()), (CONFIG, _store())):
            async with llm_adapter(config, store, replay) as adapter:
                assert isinstance(await adapter.decide(REQUEST), LLMAnswer)
                assert adapter.info.is_local is config.local
        async with llm_adapter(CONFIG, FakeCredentialStore(), replay) as adapter:
            with pytest.raises(ProviderError) as error:
                await adapter.decide(REQUEST)
            assert error.value.code is ProviderErrorCode.NO_KEY
        assert calls == [
            ("http://127.0.0.1:8080/v1/chat/completions", None),
            ("https://model.invalid/v1/chat/completions", f"Bearer {KEY}"),
        ]

    with pytest.raises(ValidationError, match="base_url"):
        LLMProviderConfig.model_validate(CONFIG.model_dump() | {"base_url": "http://model.invalid/v1"})
    asyncio.run(check())


@pytest.mark.parametrize(
    ("code", "status"),
    [
        # AC14 and §4.5: NOT_IMPLEMENTED is Jev-only.
        (ProviderErrorCode.NO_KEY, None),
        (ProviderErrorCode.CREDENTIAL_STORE, None),
        (ProviderErrorCode.NETWORK, None),
        (ProviderErrorCode.TIMEOUT, None),
        (ProviderErrorCode.AUTH, 401),
        (ProviderErrorCode.AUTH, 403),
        (ProviderErrorCode.RATE_LIMITED, 429),
        (ProviderErrorCode.HTTP_STATUS, 302),
        (ProviderErrorCode.HTTP_STATUS, 500),
        (ProviderErrorCode.BAD_RESPONSE, 200),
        (ProviderErrorCode.INVALID_OUTPUT, 200),
        (ProviderErrorCode.REDACTION_BLOCKED, None),
    ],
)
def test_no_secret_or_body_in_logs_full_stack(
    code: ProviderErrorCode,
    status: int | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BrokenStore(FakeCredentialStore):
        def get(self, key_ref: str) -> SecretStr | None:
            raise ProviderError(ProviderErrorCode.CREDENTIAL_STORE)

    def replay(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        failure: dict[ProviderErrorCode, Callable[..., httpx2.HTTPError]] = {
            ProviderErrorCode.NETWORK: httpx2.ConnectError,
            ProviderErrorCode.TIMEOUT: httpx2.ReadTimeout,
        }
        if status is None:
            raise failure[code](REMOTE, request=request)
        reply = (
            completion(request, {"choice": REMOTE, "rationale": "Needs depth."})
            if code is ProviderErrorCode.INVALID_OUTPUT
            else httpx2.Response(status, text=REMOTE)
        )
        reply.headers["X-Synthetic"] = HEADER
        return reply

    async def check() -> ProviderError:
        async with llm_adapter(CONFIG, store, replay, sensitive=sensitive) as adapter:
            with pytest.raises(ProviderError) as error:
                await adapter.decide(REQUEST)
            return error.value

    names = ("openai", "httpx2", "httpcore2", "pydantic_ai")
    caplog.set_level(logging.DEBUG)
    for name in names:
        caplog.set_level(logging.DEBUG, logger=name)
    calls: list[httpx2.Request] = []
    store = {ProviderErrorCode.NO_KEY: FakeCredentialStore(), ProviderErrorCode.CREDENTIAL_STORE: BrokenStore()}.get(
        code, _store()
    )
    sensitive = ("synthetic-request-body",) if code is ProviderErrorCode.REDACTION_BLOCKED else ()
    error = asyncio.run(check())
    assert error.code is code
    expected_calls = (
        0
        if code in {ProviderErrorCode.NO_KEY, ProviderErrorCode.CREDENTIAL_STORE, ProviderErrorCode.REDACTION_BLOCKED}
        else 1
    )
    assert len(calls) == expected_calls
    assert all(logging.getLogger(name).getEffectiveLevel() >= logging.WARNING for name in names)
    captured = (
        caplog.text + repr([vars(record) for record in caplog.records]) + "".join(traceback.format_exception(error))
    )
    assert all(marker not in captured for marker in (KEY, REMOTE, HEADER, "synthetic-request-body"))
