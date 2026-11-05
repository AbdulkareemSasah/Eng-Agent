"""Fake decision providers (spec 0005 section 4.7; plan 0005 T5; lead decision D-5).

Test doubles only: scripted answers, delays and failures for tier 2 (`FakeDecisionProvider`) and tier 3
(`FakeLLMProvider`). Nothing here opens a socket or reads a clock; a delay is an `asyncio.sleep` of the stated seconds.
Every request received is kept in `requests`, so a test can assert what a provider was given.
"""

import asyncio
from collections import deque
from collections.abc import Mapping, Sequence

from eng_harness.decisions.interfaces import (
    ChoiceAnswer,
    LLMAnswer,
    ProviderError,
    ProviderErrorCode,
    ProviderFailure,
    ProviderInfo,
    ProviderRequest,
    YesNoAnswer,
)

_DEFAULT_INFO = ProviderInfo(provider="fake", model="fake-model", version="0", is_local=True, supports_batch=True)


class _Scripted[T]:
    """A queue of scripted outcomes; an exception in the queue is raised, anything else is returned."""

    def __init__(self, outcomes: Sequence[T | Exception]) -> None:
        self._outcomes: deque[T | Exception] = deque(outcomes)

    def next(self) -> T:
        if not self._outcomes:
            raise ProviderError(ProviderErrorCode.NOT_IMPLEMENTED, gap="FAKE-G1")
        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeDecisionProvider:
    """A tier 2 provider answering from scripts; `delay_s` seconds pass before each answer."""

    def __init__(
        self,
        *,
        choices: Sequence[ChoiceAnswer | Exception] = (),
        yes_nos: Sequence[YesNoAnswer | Exception] = (),
        scores: Sequence[Mapping[str, float] | Exception] = (),
        info: ProviderInfo = _DEFAULT_INFO,
        delay_s: float = 0.0,
    ) -> None:
        self.info = info
        self.requests: list[ProviderRequest] = []
        self._choices = _Scripted(choices)
        self._yes_nos = _Scripted(yes_nos)
        self._scores = _Scripted(scores)
        self._delay_s = delay_s

    async def _enter(self, request: ProviderRequest) -> None:
        self.requests.append(request)
        if self._delay_s:
            await asyncio.sleep(self._delay_s)

    async def choose(self, request: ProviderRequest) -> ChoiceAnswer:
        await self._enter(request)
        return self._choices.next()

    async def yes_no(self, request: ProviderRequest) -> YesNoAnswer:
        await self._enter(request)
        return self._yes_nos.next()

    async def score(self, request: ProviderRequest) -> Mapping[str, float]:
        await self._enter(request)
        return self._scores.next()

    async def batch(self, requests: Sequence[ProviderRequest]) -> Sequence[ChoiceAnswer | ProviderFailure]:
        """One entry per request, in order; a scripted `ProviderError` becomes that request's `ProviderFailure`."""
        results: list[ChoiceAnswer | ProviderFailure] = []
        for request in requests:
            await self._enter(request)
            try:
                results.append(self._choices.next())
            except ProviderError as error:
                results.append(ProviderFailure(code=error.code))
        return results


class FakeLLMProvider:
    """A tier 3 provider answering from a script; `delay_s` seconds pass before each answer."""

    def __init__(
        self,
        *,
        answers: Sequence[LLMAnswer | Exception] = (),
        info: ProviderInfo = _DEFAULT_INFO,
        delay_s: float = 0.0,
    ) -> None:
        self.info = info
        self.requests: list[ProviderRequest] = []
        self._answers = _Scripted(answers)
        self._delay_s = delay_s

    async def decide(self, request: ProviderRequest) -> LLMAnswer:
        self.requests.append(request)
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        return self._answers.next()
