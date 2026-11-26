"""Jev decision provider over the format boundary (spec 0009 section 4.6)."""

from collections.abc import Mapping, Sequence

import httpx2
from pydantic import ValidationError

from eng_harness.decisions.interfaces import (
    ChoiceAnswer,
    ProviderError,
    ProviderErrorCode,
    ProviderFailure,
    ProviderInfo,
    ProviderRequest,
    YesNoAnswer,
)
from eng_harness.providers._config import DecisionProviderConfig
from eng_harness.providers._credentials import CredentialStore
from eng_harness.providers._http import ProviderClient
from eng_harness.providers._jev_format import HttpCall, JevFormat, Operation, ParsedAnswer, select_format
from eng_harness.providers._outgoing import guard_request


def _valid_answer(answer: ChoiceAnswer | YesNoAnswer) -> bool:
    # Validate the fields even if a format created the model with model_construct.
    try:
        type(answer).model_validate(dict(answer), strict=True)
    except ValidationError:
        return False
    return True


def _valid_choice(answer: ChoiceAnswer, request: ProviderRequest) -> bool:
    return _valid_answer(answer) and any(answer.choice == option.value for option in request.options)


class JevProvider:
    def __init__(
        self,
        config: DecisionProviderConfig,
        client: ProviderClient,
        format_: JevFormat,
        *,
        sensitive_values: Sequence[str] = (),
    ) -> None:
        self.info = ProviderInfo(
            provider=config.name,
            model=config.model,
            version=f"{config.model_version};map-{format_.revision}",
            is_local=config.local,
            supports_batch=format_.supports_batch,
        )
        self._client = client
        self._format = format_
        self._sensitive_values = tuple(sensitive_values)

    async def _receive(
        self, op: Operation, requests: Sequence[ProviderRequest], call: HttpCall
    ) -> list[ParsedAnswer] | ProviderErrorCode:
        """Keep the remote body and any format exception out of the raised error's traceback."""
        body = await self._client.post_json(call.path, call.body, sensitive_values=self._sensitive_values)
        try:
            answers = self._format.parse(op, requests, body)
        except ProviderError as error:
            return error.code
        if len(answers) != len(requests):
            return ProviderErrorCode.BAD_RESPONSE
        return answers

    async def _exchange(self, op: Operation, requests: Sequence[ProviderRequest]) -> list[ParsedAnswer]:
        for request in requests:
            guard_request(request, self._sensitive_values)
        call = HttpCall.model_validate(self._format.build(op, requests))
        answers = await self._receive(op, requests, call)
        if isinstance(answers, ProviderErrorCode):
            raise ProviderError(answers)
        return answers

    async def _single(self, op: Operation, request: ProviderRequest) -> ParsedAnswer:
        (answer,) = await self._exchange(op, (request,))
        if isinstance(answer, ProviderFailure):
            raise ProviderError(answer.code)
        return answer

    async def choose(self, request: ProviderRequest) -> ChoiceAnswer:
        answer = await self._single("choose", request)
        if not isinstance(answer, ChoiceAnswer) or not _valid_choice(answer, request):
            del answer  # A rejected answer can contain arbitrary remote text.
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
        return answer

    async def yes_no(self, request: ProviderRequest) -> YesNoAnswer:
        answer = await self._single("yes_no", request)
        if not isinstance(answer, YesNoAnswer) or not _valid_answer(answer):
            del answer
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
        return answer

    async def score(self, request: ProviderRequest) -> Mapping[str, float]:
        answer = await self._single("score", request)
        if not isinstance(answer, Mapping) or answer.keys() != {option.value for option in request.options}:
            del answer
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
        return answer

    async def batch(self, requests: Sequence[ProviderRequest]) -> Sequence[ChoiceAnswer | ProviderFailure]:
        if not self.info.supports_batch:
            raise ProviderError(ProviderErrorCode.NOT_IMPLEMENTED)
        ordered_requests = tuple(requests)
        answers = await self._exchange("batch", ordered_requests)
        results: list[ChoiceAnswer | ProviderFailure] = []
        for request, answer in zip(ordered_requests, answers, strict=True):
            if isinstance(answer, ProviderFailure) or (
                isinstance(answer, ChoiceAnswer) and _valid_choice(answer, request)
            ):
                results.append(answer)
            else:
                results.append(ProviderFailure(code=ProviderErrorCode.INVALID_OUTPUT))
        return results

    async def aclose(self) -> None:
        await self._client.aclose()


def build_jev_provider(
    config: DecisionProviderConfig,
    store: CredentialStore,
    *,
    transport: httpx2.AsyncBaseTransport | None = None,
    sensitive_values: Sequence[str] = (),
) -> JevProvider:
    """Select the format before allocating a client, so an unavailable backend performs no I/O."""
    format_ = select_format(config.backend)
    client = ProviderClient(config, store, transport=transport)
    return JevProvider(config, client, format_, sensitive_values=sensitive_values)
