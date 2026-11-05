"""The replay index and divergence (spec 0001 4.5.2; plan 0001 T9b).

Purpose: at a resume each ctx call at path `p` is matched with what the journal recorded at `p`. A recorded step returns
its result without a port call, a changed block is stopped before any live call, and a block that ends before the
journal does is a divergence too. The last attempt of a step decides: its result, its non-retryable failure (raised
again), or nothing (a retryable failure or a reconciled `not_applied`: it runs again as the next attempt); a step with
no closing event was in flight (`NeedsReconciliation`). `~host` and `@resume` steps are audit records and housekeeping,
never matched. Units: none. Errors: `ReplayDivergence`, `NeedsReconciliation`, `JournalIntegrityError`.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from eng_contract.errors import ErrorDetail

from eng_harness.errors import JournalIntegrityError, NeedsReconciliation, ReplayDivergence
from eng_harness.journal import Event
from eng_harness.journal import _events as ev

type _Closing = ev.StepCompleted | ev.StepFailed | ev.StepReconciled
_PARTS = ("kind", "name", "arguments", "child")  # what a call is matched on, in the order of `lookup`'s record


@dataclass(frozen=True)
class Recorded:
    """A matched step: the attempt it was recorded at, and its outcome (None: it runs again, as `attempt + 1`)."""

    attempt: int
    outcome: ev.StepResult | ErrorDetail | ev.HarnessError | None


@dataclass
class _Step:
    attempt: int
    started: ev.StepStarted
    closing: _Closing | None = None


def _outcome(path: str, closing: _Closing | None) -> ev.StepResult | ErrorDetail | ev.HarnessError | None:
    """What a step's closing event leaves for the block."""
    if closing is None:
        raise NeedsReconciliation(f"step {path} was in flight when the run stopped")
    if isinstance(closing, ev.StepFailed):
        return None if closing.retryable else closing.error
    if isinstance(closing, ev.StepReconciled) and closing.outcome == "not_applied":
        return None
    if closing.result is None:
        raise NeedsReconciliation(f"step {path} was closed without a result")
    return closing.result


class ReplayIndex:
    """The recorded steps of a run by path, and which of them the block has called."""

    def __init__(self, events: Iterable[Event]) -> None:
        """Index the step events of `events`; of a path's attempts the last counts.

        Raises:
            JournalIntegrityError: a step is closed that was never started.
        """
        self._steps: dict[str, _Step] = {}
        self._visited: set[str] = set()
        for event in events:
            path, payload = event.path, event.payload
            if path is None or event.attempt is None or "~host." in path or path.startswith("@"):
                continue
            if isinstance(payload, ev.StepStarted):
                self._steps[path] = _Step(event.attempt, payload)
            elif isinstance(payload, ev.StepCompleted | ev.StepFailed | ev.StepReconciled):
                if path not in self._steps:
                    raise JournalIntegrityError(f"step event seq {event.seq} has no step_started")
                self._steps[path].closing = payload

    def lookup(
        self, path: str, kind: str, name: str, args_sha256: str, child: tuple[str, str] | None = None
    ) -> Recorded | None:
        """Match the call at `path` with its record; None when `path` is not recorded (the run goes live).

        `args_sha256` is the step's digest (an approval's `shown_sha256`); `child` a block step's (name, version).

        Raises:
            ReplayDivergence: the record differs in kind, name, digest or child.
            NeedsReconciliation: the step was in flight, or closed without a result.
        """
        step = self._steps.get(path)
        if step is None:
            return None
        self._visited.add(path)
        s = step.started
        recorded = (s.kind, s.name, s.args_sha256, (s.child.name, s.child.version) if s.child else None)
        called = (kind, name, args_sha256, child)
        if recorded != called:
            what = [part for part, r, c in zip(_PARTS, recorded, called, strict=True) if r != c]
            raise ReplayDivergence(f"step {path} differs from the journal in its {', '.join(what)}")
        return Recorded(step.attempt, _outcome(path, step.closing))

    def finish(self) -> None:
        """Check that the block called every recorded path; `ReplayDivergence` names those it did not."""
        if missing := sorted(self._steps.keys() - self._visited):
            raise ReplayDivergence(f"the block ended without calling the recorded steps {', '.join(missing)}")
