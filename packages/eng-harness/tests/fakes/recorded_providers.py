"""Synthetic replay fixtures and the T6 adapter's test entry point."""

import json
from collections.abc import AsyncIterator, Callable, Coroutine, Sequence
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

import httpx2
import pytest

from eng_harness.decisions.interfaces import (
    ChoiceAnswer,
    LLMAnswer,
    LLMProvider,
    ProviderError,
    ProviderErrorCode,
    ProviderInfo,
    ProviderOption,
    ProviderRequest,
)
from eng_harness.providers._config import LLMProviderConfig
from eng_harness.providers._credentials import CredentialStore
from fakes.decision_providers import FakeDecisionProvider, FakeLLMProvider

REQUEST = ProviderRequest(
    request_id="synthetic-request",
    point="fixture",
    point_version=1,
    options=(ProviderOption(value="deepen", label="Deepen"), ProviderOption(value="enlarge", label="Enlarge")),
    state={"note": "synthetic-request-body"},
)
RECORDING = Path(__file__).resolve().parents[1] / "data" / "recordings" / "providers" / "synthetic.json"
INFO = ProviderInfo(provider="recorded", model="fixture-model", version="fixture", is_local=True, supports_batch=False)
type Handler = Callable[[httpx2.Request], httpx2.Response | Coroutine[None, None, httpx2.Response]]


def recording() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(RECORDING.read_text(encoding="utf-8")))


class RecordedDecisionProvider(FakeDecisionProvider):
    def __init__(self, *, delayed: bool = False) -> None:
        data = recording()
        super().__init__(
            choices=[ChoiceAnswer.model_validate(data["choice"]), ProviderError(ProviderErrorCode(data["failure"]))],
            delay_s=data["delay_s"] if delayed else 0,
            info=INFO.model_copy(update={"supports_batch": True}),
        )


class RecordedLLMProvider(FakeLLMProvider):
    def __init__(self, *, delayed: bool = False) -> None:
        data = recording()
        super().__init__(
            answers=[LLMAnswer.model_validate(data["answer"]), ProviderError(ProviderErrorCode(data["failure"]))],
            delay_s=data["delay_s"] if delayed else 0,
            info=INFO,
        )


def completion(request: httpx2.Request, arguments: object = None) -> httpx2.Response:
    data = recording()
    body = json.loads(request.content)
    reply = data["completion"]
    function = reply["choices"][0]["message"]["tool_calls"][0]["function"]
    # Echo only the generated output tool name. The response and arguments are synthetic.
    function.update(
        name=body["tools"][0]["function"]["name"],
        arguments=json.dumps(data["answer"] if arguments is None else arguments),
    )
    return httpx2.Response(200, json=reply)


class _ClosableLLM(LLMProvider, Protocol):
    async def aclose(self) -> None: ...


class _Builder(Protocol):
    def __call__(
        self,
        config: LLMProviderConfig,
        store: CredentialStore,
        *,
        transport: httpx2.AsyncBaseTransport,
        sensitive_values: Sequence[str],
    ) -> _ClosableLLM: ...


@asynccontextmanager
async def llm_adapter(
    config: LLMProviderConfig, store: CredentialStore, handler: Handler, *, sensitive: Sequence[str] = ()
) -> AsyncIterator[LLMProvider]:
    name = "eng_harness.providers._llm"
    try:
        module = import_module(name)
    except ModuleNotFoundError as error:
        if error.name != name:
            raise
        pytest.fail(f"T6 LLM adapter feature is missing: {name}", pytrace=False)
    build = cast(_Builder, getattr(module, "build_llm_provider", None))
    assert callable(build), "T6 LLM adapter builder is missing"
    adapter = build(config, store, transport=httpx2.MockTransport(handler), sensitive_values=sensitive)
    try:
        yield adapter
    finally:
        await adapter.aclose()
