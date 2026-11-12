"""Invariants 5, 6, 8 and 9: design basis, honest outcomes, server checks, the first-use binding and host units.

Purpose: `start` refuses a run whose design basis lacks a required field (#5) or whose servers fail their check (#8)
before the run folder exists. `Pending` holds, per host, the writes whose outcome is unknown (the call raised, returned
`TIMEOUT_UNKNOWN_OUTCOME` or returned `HOST_WEDGED`) and reconciles them (spec 4.5.3) before the next step on that
host, while steps on other hosts go on (#6). It also binds each model to the instance that holds it before the first
step addressed to it (spec 4.8) and reads the units of the models of a host at that first use and after a reconnect or
a timeout (#9). Units: none. Errors: `RunRefused`; `Stopped` (see `_inflight`) when the engineer must decide a write,
or abandoned the run, or the units differ (`units_mismatch`); `ContractError`: `PRECONDITION_FAILED` (`model_open`) or
from a port call.
"""

import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence

from eng_contract.errors import ContractError, ErrorCode, Precondition
from pydantic import JsonValue

from eng_harness import errors
from eng_harness.engine import _hoststate
from eng_harness.engine._inflight import Fold, Resume, _write
from eng_harness.engine._invariants import _Ctx, path_key
from eng_harness.engine._steps import inserted_path
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import BasisPort, HostPort, ServerCheck, ToolInfo

_Obj = dict[str, JsonValue]


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
    """Invariants 6 and 9: the hosts with reconciliation pending, the models bound to instances, and their units."""

    def __init__(self, rt: Resume) -> None:
        """Work through `rt` (its ports, store, journal writer and engineer requests); read what the journal holds."""
        self._rt = rt
        self._paths: defaultdict[str, list[str]] = defaultdict(list)
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        events = rt.events()
        self._bound = {key: (b.host_key, b.instance_id) for key, b in Fold(events).bound.items()}
        started = [(e, p) for e in events if isinstance(p := e.payload, ev.StepStarted) and p.name[:5] == "units"]
        self._read = {p.model_key for _, p in started if p.kind == "read"}
        self._taken = {(e.path, e.attempt) for e, _ in started}  # the units steps journaled: one per path and attempt
        self._epochs: dict[str, int] = {}  # the session epoch of each host when this process first saw it (4.6 #9)
        self._timed: set[str] = set()  # the hosts on which a timeout was observed, until their units are read again
        self._turn = asyncio.Lock()

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

    async def bind(self, ctx: _Ctx, path: str, key: str | None, info: ToolInfo, *, after: bool = False) -> None:
        """Bind the model `key` to the instance that holds it and read its units, before its first step (4.8, 4.6 #9 a).

        The binding (`first_use`) and the step `<path>~pre.units.<key>` come before the step at `path`; for a tool
        with action `open` the model is not open before it, so both come after it (`after`, `~post.units`).

        Raises:
            ContractError: `PRECONDITION_FAILED` `model_open` when no instance holds the model before the step.
            Stopped: its units differ (the run is escalated, `units_mismatch`).
        """
        if key is None or after != (info.action == "open"):
            return
        async with self._turn:
            if key not in self._bound:
                if (found := await self._rt.host.locate(key)) is None:
                    if after:
                        return
                    message = f"the model {key} is not open in any host instance"
                    raise ContractError(ErrorCode.PRECONDITION_FAILED, message, precondition=Precondition.model_open)
                _hoststate.bind(self._rt.writer, self._rt.host, key, info.host_key, found.instance_id, "first_use")
                self._bound[key] = (info.host_key, found.instance_id)
            first = inserted_path(path, "post" if after else "pre", "units", path_key(key))
            ctx._look(first, "read", "units", {"model_key": key})  # a recorded step is visited, so replay finds it
            if key not in self._read:
                await self._check(ctx, first, key, self._bound[key][1], 1)

    def replay(self, ctx: _Ctx, path: str, key: str | None) -> None:
        """Visit the units steps recorded for the step at `path`, so that replay finds them (AC47); no port call."""
        if key is not None:
            for phase in ("pre", "post"):
                ctx._look(inserted_path(path, phase, "units", path_key(key)), "read", "units", {"model_key": key})

    def timed_out(self, host_key: str) -> None:
        """Note a timeout, `TIMEOUT_UNKNOWN_OUTCOME` or `HOST_WEDGED` observed on `host_key` (4.6 #9 c)."""
        self._timed.add(host_key)

    async def reconnected(self, ctx: _Ctx, path: str, attempt: int, host_key: str) -> None:
        """Read the units of the models bound on `host_key` again when its session epoch changed in this process, or
        when a timeout was observed on it since (`timed_out`), as `<path>~host.units.<key>` (4.6 #9 c).

        Raises:
            Stopped: the units differ (the run is escalated, `units_mismatch`).
        """
        async with self._turn:
            epoch = self._rt.host.session_epoch(host_key)
            changed, self._epochs[host_key] = self._epochs.setdefault(host_key, epoch) != epoch, epoch
            if changed or host_key in self._timed:
                self._timed.discard(host_key)
                for key, (bound_host, instance_id) in sorted(self._bound.items()):
                    if bound_host == host_key:
                        units, nth = inserted_path(path, "host", "units", path_key(key)), attempt
                        while (units, nth) in self._taken:  # a second read at one step takes the next attempt
                            nth += 1
                        self._taken.add((units, nth))
                        await self._check(ctx, units, key, instance_id, nth)

    async def _check(self, ctx: _Ctx, path: str, key: str, instance_id: str, attempt: int) -> None:
        """Read the units of `key` in `instance_id` as the inserted step `path`; differing units end the run (#9)."""
        rt, args = self._rt, _Obj(model_key=key)
        units = await rt.host.read_units(key, instance_id)
        if not units.ok:  # the step is not recorded, so a resume reads the units again; a block cannot catch the stop
            rt.stop(f"the units of {key} are {units.present}, not {units.expected}", None, "units_mismatch")
        began = ctx._begin(path, attempt, "read", "units", args, effect="read", model_key=key)
        summary = _Obj(loaded=units.loaded, instance_id=instance_id)
        stored = rt.store.put("harness.journal_blob/1", {"value": summary}, rt.producer())
        ctx._done(
            path, attempt, began, ev.StepResult(ref=stored.result_id, summary=summary, warnings=[], complete=True)
        )
        rt.writer.append(EventType.CHECK_ENFORCED, {"invariant": 9, "model_key": key, "outcome": "pass"}, path=path)
        self._read.add(key)
