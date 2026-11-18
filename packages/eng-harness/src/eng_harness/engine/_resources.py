"""Resource limits, the progress sink's delivery and the stop check of one run (spec 0001 4.10, AC58, AC59).

Purpose: `Limits` holds the semaphores of `EngineSettings` and one lock for each host key, so steps on one host are
serialized in the engine as well as by the server (11 section 8). A `ctx.parallel` call takes its own children
semaphore, so a child that starts a `ctx.parallel` of its own cannot starve its children of permits. A host call takes
its host's lock first and then a permit of `max_concurrent_hosts`, so a call waiting for its host holds no permit.
`commit_hook` delivers each committed event to the `ProgressSink`; a sink that raises is detached and the failure
logged (progress is derived from the journal, which stays complete). `Limits.check_stop` asks the `RunControlPort`.
Units: counts. Errors: `StopRequested`, a `Pause`.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from eng_harness import errors
from eng_harness.journal import Event
from eng_harness.ports import ProgressSink, RunControlPort

if TYPE_CHECKING:
    from eng_harness.engine._runner import EngineSettings

_LOG = logging.getLogger(__name__)


class StopRequested(errors.Pause):
    """The engineer asked the run to stop: `run_paused` with the reason `stop_requested` (spec 4.8, 4.4.2)."""


class Limits:
    """The limits of one run's settings, its host locks and its stop check."""

    def __init__(self, settings: EngineSettings, control: RunControlPort | None, run_id: str) -> None:
        """Take the limits of `settings`; `control` is asked about `run_id` (none: no stop check)."""
        self._children, self._control, self._run_id = settings.max_parallel_children, control, run_id
        self.hosts, self.decisions = (
            asyncio.Semaphore(settings.max_concurrent_hosts),
            asyncio.Semaphore(settings.max_concurrent_decisions),
        )
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def children(self) -> asyncio.Semaphore:
        """A semaphore for the children of one `ctx.parallel` call; permits go in argument order."""
        return asyncio.Semaphore(self._children)

    @asynccontextmanager
    async def host(self, key: str) -> AsyncIterator[None]:
        """Hold the host `key` alone, and one of the `max_concurrent_hosts` permits, for a call to it."""
        async with self._locks[key], self.hosts:
            yield

    def check_stop(self, path: str) -> None:
        """Pause the run before the live step at `path` when the engineer asked for a stop.

        Raises:
            StopRequested: the port says so; an engine-inserted step (a `~` in its path) is not asked.
        """
        if self._control is not None and "~" not in path and self._control.stop_requested(self._run_id):
            raise StopRequested(f"a stop was requested before step {path}")


def commit_hook(sink: ProgressSink | None) -> Callable[[Event], None] | None:
    """The `on_commit` hook of a `JournalWriter` that delivers each event to `sink`; none without a sink.

    A sink whose `emit` raises is detached for the rest of the run and the failure is logged (AC58).
    """
    if sink is None:
        return None
    detached = False

    def deliver(event: Event) -> None:
        nonlocal detached
        if detached:
            return
        try:
            sink.emit(event)
        except Exception as exc:
            detached = True
            _LOG.warning(
                "the progress sink raised %r at event %d and is detached; the journal is complete", exc, event.seq
            )

    return deliver
