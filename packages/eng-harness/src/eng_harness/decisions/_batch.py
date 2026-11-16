"""Helpers of ``decide_many`` (spec 0005 section 4.8): the batch id, the all-or-nothing check, bounded concurrency
and the stored outcomes of a batch.

Units: none. Errors: pydantic ``ValidationError`` when a stored outcome is not a ``DecisionAnswer``.
"""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping, Sequence
from typing import Literal

from pydantic import JsonValue

from eng_harness.decisions._record import DecisionAnswer

__all__ = ["batch_id", "bounded", "refusal", "restored", "stored"]


def batch_id(request_ids: Iterable[str]) -> str:
    """``"batch_"`` and the first 16 hex digits of the sha256 of the sorted request ids, one on each line."""
    return "batch_" + hashlib.sha256("\n".join(sorted(request_ids)).encode()).hexdigest()[:16]


def refusal(
    expected: Collection[str], given: Mapping[str, str], options: Mapping[str, Collection[str]]
) -> Literal["incomplete", "not_an_option"] | None:
    """Why a set of engineer choices is refused as a whole (AC28), or ``None`` when it is complete and valid.

    ``expected`` are the open requests of the batch, ``given`` the choice of each request that carries one and
    ``options`` the option values of each request; no choice at all is no refusal, the batch is just asked again.
    """
    if not given:
        return None
    if any(request_id not in given for request_id in expected):
        return "incomplete"
    if any(choice not in options.get(request_id, ()) for request_id, choice in given.items()):
        return "not_an_option"
    return None


async def bounded[T](limit: int, jobs: Sequence[Callable[[], Awaitable[T]]]) -> list[T]:
    """Run the jobs at the same time, at most ``limit`` of them, and return their results in job order."""
    gate = asyncio.Semaphore(limit)

    async def run(job: Callable[[], Awaitable[T]]) -> T:
        async with gate:
            return await job()

    return list(await asyncio.gather(*(run(job) for job in jobs)))


def stored(answers: Mapping[str, DecisionAnswer]) -> dict[str, JsonValue]:
    """The resolved outcomes of a batch as the JSON object the pending store keeps, by request id."""
    return {request_id: answer.model_dump(mode="json", by_alias=True) for request_id, answer in answers.items()}


def restored(outcomes: Mapping[str, JsonValue]) -> dict[str, DecisionAnswer]:
    """The answers kept by ``stored``."""
    return {request_id: DecisionAnswer.model_validate(outcome) for request_id, outcome in outcomes.items()}
