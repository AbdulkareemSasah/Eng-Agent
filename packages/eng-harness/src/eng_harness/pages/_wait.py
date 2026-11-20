"""The wait for an answer (spec 0006 4.4.5 step 2; AC36).

Purpose: await the event the page sets when it accepts an answer, looking at the stop request twice a second so that a
stop ends the wait within the one second AC36 allows. Units: seconds. Errors: none; every way out but the event is a
`False` result, and the engine then pauses.
"""

import asyncio
import contextlib
import time
from collections.abc import Callable

POLL_S = 0.5  # seconds between looks at the stop request: a software setting, below the 1 s of AC36


async def wait_for(
    event: asyncio.Event, *, wait: bool, stop_requested: Callable[[], bool], timeout_s: float | None
) -> bool:
    """True once `event` is set; False at once for `wait=False`, on a stop request, or after `timeout_s` seconds."""
    end = None if timeout_s is None else time.monotonic() + timeout_s
    while not event.is_set():
        left = None if end is None else end - time.monotonic()
        if not wait or stop_requested() or (left is not None and left <= 0):
            return False
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(event.wait(), POLL_S if left is None else min(POLL_S, left))
    return True
