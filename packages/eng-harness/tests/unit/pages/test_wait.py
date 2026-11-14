"""The wait for an answer ends on a stop request or at once without `wait` (plan 0006 T7; AC36)."""

import asyncio
import threading
import time

from helpers.engine_standin import approval_request

from eng_harness.pages import PageApprovalPort
from eng_harness.pages._wait import wait_for

MAX_S = 1.0  # AC36: a stop ends the wait within one second


def test_stop_ends_wait() -> None:
    stop = threading.Event()
    port = PageApprovalPort(stop_requested=stop.is_set)
    request = approval_request()

    async def scenario() -> tuple[object, float, object, float]:
        await port.present(request)
        threading.Timer(0.3, stop.set).start()
        began = time.monotonic()
        stopped = await port.answer(request.request_id, wait=True)
        waited = time.monotonic() - began
        stop.clear()
        began = time.monotonic()
        none = await port.answer(request.request_id, wait=False)
        return stopped, waited, none, time.monotonic() - began

    stopped, waited, none, at_once = asyncio.run(scenario())
    assert stopped is None
    assert 0.25 <= waited < MAX_S  # the stop came at 0.3 s and ended the wait
    assert none is None
    assert at_once < 0.2  # wait=False and no answer: at once


def _wait(
    event_set: bool, *, wait: bool = True, stop: bool = False, timeout_s: float | None = None
) -> tuple[bool, float]:
    async def scenario() -> tuple[bool, float]:
        event = asyncio.Event()
        if event_set:
            event.set()
        began = time.monotonic()
        got = await wait_for(event, wait=wait, stop_requested=lambda: stop, timeout_s=timeout_s)
        return got, time.monotonic() - began

    return asyncio.run(scenario())


def test_wait_for_ways_out() -> None:
    assert _wait(True, wait=False, stop=True, timeout_s=0)[0] is True  # an answer already there beats everything
    assert _wait(True, stop=True)[0] is True
    got, took = _wait(False, wait=False)
    assert (got, took < 0.2) == (False, True)
    got, took = _wait(False, stop=True)
    assert (got, took < 0.2) == (False, True)
    got, took = _wait(False, timeout_s=0)
    assert (got, took < 0.2) == (False, True)
    got, took = _wait(False, timeout_s=0.2)  # the timeout cuts the last poll short
    assert got is False
    assert 0.15 <= took < 0.45


def test_wait_for_sees_an_answer_that_comes_while_it_waits() -> None:
    async def scenario() -> bool:
        event = asyncio.Event()
        asyncio.get_running_loop().call_later(0.1, event.set)
        return await wait_for(event, wait=True, stop_requested=lambda: False, timeout_s=None)

    assert asyncio.run(scenario()) is True


def test_wait_timeout_and_a_taken_answer() -> None:
    port = PageApprovalPort(wait_timeout_s=0.2)
    request = approval_request()

    async def scenario() -> tuple[object, float, object]:
        assert await port.answer("unknown", wait=True) is None  # never presented
        await port.present(request)
        began = time.monotonic()
        timed_out = await port.answer(request.request_id, wait=True)
        waited = time.monotonic() - began
        return timed_out, waited, await port.answer(request.request_id, wait=False)

    timed_out, waited, again = asyncio.run(scenario())
    assert timed_out is None
    assert 0.15 <= waited < 0.45
    assert again is None
