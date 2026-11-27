"""Closed PydanticAI language-model provider over the shared client (spec 0009 sections 4.5 and 4.7)."""

import asyncio
from collections.abc import Sequence
from typing import cast, override

import httpx2
from pydantic import SecretStr, ValidationError
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, ModelConnectionError, ModelTimeoutError, UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai_compatible import OpenAICompatibleProvider
from pydantic_ai.settings import ModelSettings

from eng_harness.decisions.interfaces import (
    LLMAnswer,
    ProviderError,
    ProviderErrorCode,
    ProviderInfo,
    ProviderRequest,
)
from eng_harness.providers._config import LLMProviderConfig
from eng_harness.providers._credentials import CredentialStore
from eng_harness.providers._http import _classify, build_http_client
from eng_harness.providers._llm_types import build_tool_output
from eng_harness.providers._outgoing import find_body_place, guard_request
from eng_harness.providers._prompts import PROMPT_VERSION, render_messages

_SDK_KEY = "unused"  # spec 0009 section 4.5
_NO_RETRIES = 0  # spec 0009 sections 4.5 and 4.7
_TEMPERATURE = 0.0  # spec 0009 section 4.7
_MS_PER_SECOND = 1000
_CHOICE_COUNT = 1  # one completion carrying the requested output


class _ClientBoundChatModel(OpenAIChatModel):
    """Use the configured client without enabling PydanticAI's process-wide request switch."""

    @override
    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        settings, parameters = self.prepare_request(model_settings, model_request_parameters)
        try:
            # The pinned OpenAIChatModel's non-streaming path, scoped to this private model instance.
            response = await self._completions_create(
                messages, False, cast(OpenAIChatModelSettings, settings or {}), parameters
            )
            if isinstance(response, ModelResponse):
                return response
            if len(response.choices) == _CHOICE_COUNT:
                return self._process_response(response)
        except AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError, UnexpectedModelBehavior:
            pass  # A malformed SDK response can contain arbitrary remote text.
        raise ProviderError(ProviderErrorCode.BAD_RESPONSE)


async def _check_response(response: httpx2.Response) -> None:
    if response.is_success:
        await response.aread()
    code, _ = _classify(response)
    if code is not None:
        raise ProviderError(code)


class LlmProvider:
    def __init__(
        self,
        config: LLMProviderConfig,
        store: CredentialStore,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
        sensitive_values: Sequence[str] = (),
    ) -> None:
        self.info = ProviderInfo(
            provider=config.name,
            model=config.model,
            version=f"{config.model_version};prompt-{PROMPT_VERSION}",
            is_local=config.local,
            supports_batch=False,
        )
        self._requires_key = not config.local or config.key_ref is not None
        self._sensitive_values = tuple(sensitive_values)
        self._timeout_s = config.request_timeout_ms / _MS_PER_SECOND
        self._http = build_http_client(config, store, transport=transport)
        self._http.event_hooks = {"request": [self._check_request], "response": [_check_response]}
        provider = OpenAICompatibleProvider(
            config.name, base_url=config.base_url, api_key=_SDK_KEY, http_client=self._http
        )
        sdk = provider.client
        sdk.max_retries = _NO_RETRIES
        sdk.admin_api_key = sdk.organization = sdk.project = sdk.webhook_secret = None
        self._model = _ClientBoundChatModel(
            config.model,
            provider=provider,
            profile=OpenAIModelProfile(openai_supports_strict_tool_definition=True, openai_supports_reasoning=False),
            settings=OpenAIChatModelSettings(
                temperature=_TEMPERATURE,
                max_tokens=config.max_output_tokens,
                extra_headers={"Authorization": ""},  # Only the shared HTTP auth hook supplies a bearer key.
            ),
        )

    async def _check_request(self, request: httpx2.Request) -> None:
        # HTTPX runs this after its auth hook and before it invokes the transport.
        authorization = request.headers.get("Authorization", "")
        key = authorization.removeprefix("Bearer ")
        if self._requires_key and not key:
            raise ProviderError(ProviderErrorCode.NO_KEY)
        body = await request.aread()
        place = find_body_place(body, self._sensitive_values, SecretStr(key) if key else None)
        if place is not None:
            raise ProviderError(ProviderErrorCode.REDACTION_BLOCKED, where=place)
        # Discard SDK metadata and ambient custom headers. Keep only the request's wire headers and shared auth.
        request.headers = httpx2.Headers(
            {
                "Host": request.url.netloc.decode("ascii"),
                "Content-Length": str(len(body)),
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        if key:
            request.headers["Authorization"] = authorization

    async def _run(self, request: ProviderRequest) -> LLMAnswer | ProviderError:
        """Reduce failures to fixed codes here so the raised error cannot retain SDK frames."""
        try:
            guard_request(request, self._sensitive_values)
            agent = Agent(self._model, output_type=build_tool_output(request), retries=_NO_RETRIES)
            agent.instrument = False
            async with asyncio.timeout(self._timeout_s):
                result = await agent.run(message_history=render_messages(request), infer_name=False)
            return LLMAnswer.model_validate(result.output.model_dump())
        except ProviderError as error:
            return ProviderError(error.code, where=error.where)
        except TimeoutError, httpx2.TimeoutException, ModelTimeoutError:
            return ProviderError(ProviderErrorCode.TIMEOUT)
        except OSError, httpx2.HTTPError, ModelConnectionError:
            return ProviderError(ProviderErrorCode.NETWORK)
        except ModelAPIError:
            return ProviderError(ProviderErrorCode.BAD_RESPONSE)
        except ValidationError, UnexpectedModelBehavior:
            return ProviderError(ProviderErrorCode.INVALID_OUTPUT)

    async def decide(self, request: ProviderRequest) -> LLMAnswer:
        outcome = await self._run(request)
        del request
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome

    async def aclose(self) -> None:
        await self._http.aclose()


def build_llm_provider(
    config: LLMProviderConfig,
    store: CredentialStore,
    *,
    transport: httpx2.AsyncBaseTransport | None = None,
    sensitive_values: Sequence[str] = (),
) -> LlmProvider:
    return LlmProvider(config, store, transport=transport, sensitive_values=sensitive_values)
