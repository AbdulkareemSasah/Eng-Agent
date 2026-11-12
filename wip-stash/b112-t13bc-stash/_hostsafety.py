"""Invariants 5, 6, 8, 9 and 10: basis, outcomes, server checks, units and host leases (spec 4.6).

Purpose: refuse or stop before unsafe host work; bind models, journal instances and reconcile wedged writes. Units:
none. Errors: `RunRefused`, `ContractError`, `NeedsReconciliation`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from pathlib import Path

from eng_contract.envelope import Provenance
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.ids import Clock, IdSource
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness import errors
from eng_harness.engine._invariants import path_key
from eng_harness.engine._steps import inserted_path
from eng_harness.journal import Event, EventType, JournalReader, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import BasisPort, HostLease, HostPort, InputPort, ServerCheck, ToolInfo, ToolPort

_UNKNOWN = {ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, ErrorCode.HOST_WEDGED}
_Obj = dict[str, JsonValue]


def check_basis(basis: BasisPort, basis_ref: str, required: Sequence[str]) -> None:
    """Invariant 5: every `required` path of the design basis must be present and confirmed."""
    if not required:
        return
    if missing := basis.load(basis_ref).basis.missing(required):
        raise errors.RunRefused(errors.HarnessCode.BASIS_INCOMPLETE, "the design basis is incomplete", evidence=missing)


async def preflight(host: HostPort, min_builds: Mapping[str, str]) -> list[ServerCheck]:
    """Invariant 8: every server check must pass before any write (spec 4.5.1 step 4)."""
    checks = await host.preflight(min_builds)
    if bad := [c for c in checks if not c.ok]:
        names = ", ".join(c.server for c in bad)
        raise errors.RunRefused(errors.HarnessCode.SERVER_CHECK_FAILED, f"server check failed for {names}")
    return checks


def addressed(events: Sequence[Event]) -> list[str]:
    """Model keys the journal addressed in tool, calc or read steps."""
    keys: set[str] = set()
    for event in events:
        payload = event.payload
        if isinstance(payload, ev.StepStarted) and payload.model_key:
            keys.add(payload.model_key)
    return sorted(keys)


def host_keys(events: Sequence[Event]) -> set[str]:
    """Host keys the journal has touched."""
    keys = {p.host_key for e in events if isinstance(p := e.payload, ev.HostStarted)}
    for e in events:
        if isinstance(p := e.payload, ev.StepStarted) and p.host_key:
            keys.add(p.host_key)
        if isinstance(p := e.payload, ev.ModelBound):
            keys.add(p.host_key)
    return keys


class Safety:
    """Per-run host safety state for invariants 6, 9 and 10."""

    def __init__(
        self,
        host: HostPort,
        tool: ToolPort,
        inputs: InputPort,
        writer: JournalWriter,
        store: ResultStore,
        clock: Clock,
        ids: IdSource,
        events: Sequence[Event],
        run_dir: Path,
        run_id: str,
        producer: Callable[[], Provenance],
    ) -> None:
        self._host, self._tool, self._inputs = host, tool, inputs
        self._writer, self._store, self._clock, self._ids = writer, store, clock, ids
        self._events, self._run_dir, self._run_id, self._producer = events, run_dir, run_id, producer
        self._leased: set[str] = set()
        self._leases: dict[str, HostLease] = {}
        self._epochs = {key: host.session_epoch(key) for key in host_keys(events)}
        self._wedged: set[str] = set()
        self._journaled: set[tuple[str, str]] = {
            (p.host_key, p.instance_id) for e in events if isinstance(p := e.payload, ev.HostStarted)
        }
        self._bound = {p.model_key for e in events if isinstance(p := e.payload, ev.ModelBound)}

    def _resume(self) -> object:
        from eng_harness.engine._inflight import Resume

        number = max((p.resume_no for e in self._events if isinstance(p := e.payload, ev.RunResumed)), default=0)
        return Resume(
            self._run_dir, self._run_id, self._tool, self._inputs, self._store, self._clock, self._ids,
            self._producer, self._writer, number, self._host,
        )

    async def resume_begin(self, min_builds: Mapping[str, str]) -> None:
        """Steps 4 and 5 of a resume (leases for hosts that need them)."""
        from eng_harness.engine._inflight import Fold

        await preflight(self._host, min_builds)
        fold = Fold(self._events)
        keys = host_keys(self._events)
        for step in fold.pending():
            if step.began.host_key:
                keys.add(step.began.host_key)
        for key in fold.written():
            if key in fold.bound:
                keys.add(fold.bound[key].host_key)
        for key in sorted(keys):
            lease = await self._host.acquire(key)
            self._leased.add(key)
            self._leases[key] = lease

    async def ensure_host(self, host_key: str) -> None:
        """Invariant 10: acquire the lease before the first step on `host_key`."""
        if host_key not in self._leased:
            lease = await self._host.acquire(host_key)
            self._leased.add(host_key)
            self._leases[host_key] = lease

    async def release_all(self) -> None:
        """Release every lease this engine acquired (spec 4.6 #10)."""
        for lease in self._leases.values():
            await self._host.release(lease)
        self._leases.clear()
        self._leased.clear()

    async def journal_started(self, host_key: str) -> None:
        """Journal every started instance not yet in the run (invariant 10)."""
        for instance in await self._host.started_instances(host_key):
            token = (host_key, instance.instance_id)
            if token in self._journaled:
                continue
            body = {"host_key": host_key, **instance.model_dump(mode="json")}
            self._writer.append(EventType.HOST_STARTED, body)
            self._journaled.add(token)

    async def replay_units(self, ctx: object, base: str, model: str | None) -> None:
        """Replay a recorded `~pre.units` step when the tool step at `base` is replayed (AC47)."""
        if not model:
            return
        path = inserted_path(base, "pre", "units", path_key(model))
        args: _Obj = {"model_key": model}
        recorded = ctx._look(path, "read", "units", args)  # type: ignore[attr-defined]  # B-112: duck-typed Ctx avoids import cycle
        if recorded is not None:
            ctx._replayed(recorded)  # type: ignore[attr-defined]  # B-112: duck-typed Ctx avoids import cycle

    async def bind_and_units(self, ctx: object, path: str, model: str | None, info: ToolInfo) -> None:
        """Bind a model before `step_started`, then read units on first address (spec Q29)."""
        if not model:
            await self.ensure_host(info.host_key)
            return
        await self.ensure_host(info.host_key)
        if model not in self._bound:
            found = await self._host.locate(model)
            if found is None:
                raise ContractError(
                    ErrorCode.PRECONDITION_FAILED, f"model {model!r} is not open", precondition=Precondition.model_open
                )
            from eng_harness.engine import _hoststate

            _hoststate.bind(self._writer, self._host, model, info.host_key, found.instance_id, "first_use")
            self._bound.add(model)
            await self._units_step(ctx, inserted_path(path, "pre", "units", path_key(model)), model, found.instance_id)
        await self.before_host_step(ctx, path, info.host_key, model)

    async def before_host_step(self, ctx: object, path: str, host_key: str, model: str | None) -> None:
        """Units after a session change, and reconciliation before a wedged host continues (invariants 6 and 9)."""
        if host_key in self._wedged:
            await self.reconcile_host(ctx)
        if model and host_key in self._epochs:
            epoch = self._host.session_epoch(host_key)
            if epoch != self._epochs[host_key]:
                self._epochs[host_key] = epoch
                if instance := _bound_instance(self._events, model):
                    await self._units_step(
                        ctx, inserted_path(path, "host", "units", path_key(model)), model, instance
                    )

    def mark_wedge(self, host_key: str) -> None:
        """Invariant 6: no further live host work until reconciliation."""
        self._wedged.add(host_key)

    async def reconcile_host(self, ctx: object) -> None:
        """Reconcile every write still in flight on the wedged hosts."""
        from eng_harness.engine import _inflight as inflight
        from eng_harness.engine._inflight import Fold

        rt = self._resume()
        events = rt.events()
        pending = [s for s in Fold(events).pending() if s.began.host_key in self._wedged]
        for step in pending:
            if step.began.effect == "write":
                await inflight._write(rt, step)
        with closing(JournalReader(self._run_dir)) as reader:
            self._events = reader.events()
        ctx._sync_index()  # type: ignore[attr-defined]  # B-112: duck-typed Ctx avoids import cycle
        still = {s.began.host_key for s in Fold(self._events).pending() if s.began.effect == "write"}
        self._wedged &= still

    async def _units_step(self, ctx: object, path: str, model: str, instance_id: str) -> None:
        args: _Obj = {"model_key": model}
        recorded = ctx._look(path, "read", "units", args)  # type: ignore[attr-defined]  # B-112: duck-typed Ctx avoids import cycle
        if recorded is not None and ctx._replayed(recorded) is not None:  # type: ignore[attr-defined]  # B-112: duck-typed Ctx avoids import cycle
            return
        began = ctx._begin(path, 1, "read", "units", args, effect="read", model_key=model)  # type: ignore[attr-defined]  # B-112: duck-typed Ctx avoids import cycle
        units = await self._host.read_units(model, instance_id)
        if not units.ok:
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED,
                f"the units of {model} are {units.present}, not {units.expected}",
                precondition=Precondition.units_verified,
            )
        summary: _Obj = {"loaded": units.loaded, "ok": units.ok, "instance_id": instance_id, "model_key": model}
        ref = self._store.put("harness.journal_blob/1", {"value": summary}, self._producer()).result_id
        done = ev.StepResult(ref=ref, summary=summary, warnings=[], complete=True)
        ctx._done(path, 1, began, done)  # type: ignore[attr-defined]  # B-112: duck-typed Ctx avoids import cycle
        self._writer.append(
            EventType.CHECK_ENFORCED, {"invariant": 9, "model_key": model, "outcome": "pass"}, path=path
        )


def _bound_instance(events: Sequence[Event], model: str) -> str | None:
    for e in reversed(events):
        if isinstance(p := e.payload, ev.ModelBound) and p.model_key == model:
            return p.instance_id
    return None
