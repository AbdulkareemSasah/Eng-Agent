"""Invariants 5, 6 and 8 at start: design basis, honest outcomes and server checks (spec 0001 4.5.1, 4.6).

Purpose: `start` refuses a run whose design basis lacks a required field (#5) or whose servers fail their check (#8)
before the run folder exists. `Pending` holds, per host, the writes whose outcome is unknown (the call raised, returned
`TIMEOUT_UNKNOWN_OUTCOME` or returned `HOST_WEDGED`) and reconciles them (spec 4.5.3) before the next step on that
host, while steps on other hosts go on (#6). Units: none. Errors: `RunRefused`; `Stopped` (see `_inflight`) when the
engineer must decide a write, or abandoned the run; `ContractError` from a port call.
"""

import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence

from eng_harness import errors
from eng_harness.engine._inflight import Fold, Resume, _write
from eng_harness.journal import _events as ev
from eng_harness.ports import BasisPort, HostPort, ServerCheck


def check_basis(basis: BasisPort, basis_ref: str, required: Sequence[str]) -> None:
    """Invariant 5: every path in `required` is present and confirmed in the design basis (contract 4.10.2).

    Raises:
        RunRefused: `BASIS_INCOMPLETE`, with the absent or unconfirmed paths as evidence, in the order of `required`.
    """
    if required and (missing := basis.load(basis_ref).basis.missing(required)):
        message = "the design basis lacks or has not confirmed " + ", ".join(missing)
        raise errors.RunRefused(errors.HarnessCode.BASIS_INCOMPLETE, message, evidence=missing)


async def check_servers(host: HostPort, min_builds: Mapping[str, str]) -> list[ServerCheck]:
    """Invariant 8: the server checks against `min_builds`; none when the workflow names no minimum build.

    Raises:
        RunRefused: `SERVER_CHECK_FAILED`, with the servers whose check failed as evidence.
    """
    checks = await host.preflight(min_builds) if min_builds else []
    if failed := [c for c in checks if not c.ok]:
        message = "server check failed: " + "; ".join(f"{c.server} ({c.reason or 'not ok'})" for c in failed)
        raise errors.RunRefused(errors.HarnessCode.SERVER_CHECK_FAILED, message, evidence=[c.server for c in failed])
    return checks


class Pending:
    """Invariant 6: the hosts with reconciliation pending; each host is reconciled before its next step."""

    def __init__(self, rt: Resume) -> None:
        """Reconcile through `rt` (its ports, store, journal writer and engineer requests, spec 4.5.3)."""
        self._rt = rt
        self._paths: defaultdict[str, list[str]] = defaultdict(list)
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def settle(self, host_key: str) -> None:
        """Reconcile the writes of unknown outcome on `host_key`, if any; a step on that host waits for this."""
        async with self._locks[host_key]:
            paths = self._paths.pop(host_key, [])
            if paths:
                steps = Fold(self._rt.events()).steps
                for path in paths:
                    await _write(self._rt, steps[path])

    async def resolve(self, host_key: str, path: str, attempt: int) -> ev.StepReconciled:
        """Mark the write at `path` as of unknown outcome, reconcile its host, and return its `step_reconciled`.

        Raises:
            Stopped: the engineer must decide the write (the run is escalated) or abandoned the run.
            JournalIntegrityError: the reconciliation journaled no `step_reconciled` for the step.
        """
        self._paths[host_key].append(path)
        await self.settle(host_key)
        for event in reversed(self._rt.events()):
            if event.path == path and event.attempt == attempt and isinstance(event.payload, ev.StepReconciled):
                return event.payload
        raise errors.JournalIntegrityError(f"the write at step {path} was reconciled without a step_reconciled")
