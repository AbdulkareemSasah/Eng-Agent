"""The wait for an answer ends on a stop request or at once without `wait` (plan 0006 T7; AC36)."""

import asyncio
import threading
import time

from helpers.engine_standin import approval_request

from eng_harness.pages import PageApprovalPort

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
