"""Permission modes: working copies, the approval before a write, the always-ask list (spec 0001 4.7; AC48 to AC51).

Purpose: `Modes` inserts, before a tool step, `p~pre.working_copy.<model>` (the first write to an open model in
`work_on_copy`; later steps on the model go to the copy) and `p~pre.approve`, an approval of `ToolPort.preview` (each
write in `approve_each_write`; in every mode a delete, a save over an original and a tool of `WorkflowDef.always_ask`),
whose rejection raises `ApprovalRejected`. `ModeApprovals` resolves an `INFO` or `CHANGE_SET` approval of the block in
`autonomous_logged` and follows a model to its copy. A recorded step replays from the journal with no port call.
Units: none. Errors: `ApprovalRejected`, `ApprovalVoid`, `BlockRuleViolation`, `ContractError`.
"""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from eng_contract.envelope import Provenance
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness import errors
from eng_harness.ctx import Approval, ApprovalKind, Preview
from eng_harness.engine import _approvals
from eng_harness.engine._invariants import _Ctx, path_key
from eng_harness.engine._steps import inserted_path
from eng_harness.journal import Event, EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalPort, HostModelState, HostPort, ModelBinding, ToolInfo, ToolPort

_Obj = dict[str, JsonValue]
_AUTONOMOUS, _COPY, _EACH = "autonomous_logged", "work_on_copy", "approve_each_write"
_STATE = ("model_id", "revision", "fingerprint", "file_sha256")


class _Step(_Ctx, Protocol):
    async def _approved(
        self, path: str, title: str, preview: Preview, kind: ApprovalKind, *, engine: bool = False
    ) -> Approval: ...


class ModeApprovals(_approvals.Approvals):
    """The approvals of a run under a mode (spec 4.7); a model is followed to its working copy."""

    def __init__(
        self, mode: str, copies: Mapping[str, str], port: ApprovalPort, host: HostPort, store: ResultStore,
        writer: JournalWriter, producer: Callable[[], Provenance], run_id: str, events: Sequence[Event],
    ) -> None:  # fmt: skip
        """Serve one run in `mode`; `copies` maps a model to its working copy."""
        super().__init__(port, host, store, writer, producer, run_id, events)
        self._mode, self._copies = mode, copies

    async def settle(
        self, path: str, title: str, preview: Preview, kind: ApprovalKind, args: _Obj, *, engine: bool = False
    ) -> tuple[Approval, str]:  # fmt: skip
        """As `Approvals.settle`; `autonomous_logged` approves a block's `INFO` or `CHANGE_SET`, `engine` ones never."""
        if engine or self._mode != _AUTONOMOUS or kind not in (ApprovalKind.INFO, ApprovalKind.CHANGE_SET):
            return await super().settle(path, title, preview, kind, args)
        request = await self._request(_approvals.request_id(self._run_id, path), title, preview, kind, args)
        rid = request.request_id
        if (answer := self._answers.get(rid)) is None:
            answer = ev.ApprovalResolved(
                request_id=rid, shown_sha256=request.shown_sha256, decision="approve", rejected_items=[],
                by="mode:" + self._mode,
            )  # fmt: skip
            self._writer.append(EventType.APPROVAL_RESOLVED, answer)
            self._answers[rid] = answer
        return self._grant(path, request, answer, preview), request.preview_ref

    def stored(self, path: str) -> Preview | None:
        """The stored preview of the request made at `path`, or `None`."""
        held = self._asked.get(_approvals.request_id(self._run_id, path))
        return None if held is None else Preview.model_validate(self._store.payload(held.preview_ref))

    def _origin(self, key: str) -> str:
        return next((origin for origin, copy in self._copies.items() if copy == key), key)

    def _named(self, rid: str, key: str) -> str:
        grant = self._grants.get(rid)
        return key if grant is None or key in grant.binding else self._origin(key)

    async def _state(self, key: str) -> HostModelState | None:
        return await super()._state(self._copies.get(key, key))

    async def authorize(self, under: Approval | None, item: str | None, key: str | None, *, write: bool) -> None:
        """As `Approvals.authorize`, for the model name the approval binds."""
        named = key if under is None or key is None else self._named(under.request_id, key)
        await super().authorize(under, item, named, write=write)

    def stepped(self, under: str | None, key: str | None, ref: str) -> None:
        """As `Approvals.stepped`, for the model name the approval binds."""
        super().stepped(under, key if under is None or key is None else self._named(under, key), ref)

    def expire(self, model: str) -> None:
        """As `Approvals.expire`, also for approvals bound to the original of the copy `model`."""
        super().expire(model)
        super().expire(self._origin(model))

    def rebase(self, origin: str, before: Mapping[str, JsonValue], after: Mapping[str, JsonValue]) -> None:
        """A grant bound to the untouched state of `origin` is bound to its new working copy."""
        for grant in self._grants.values():
            bound = grant.binding.get(origin)
            if bound is not None and all(getattr(bound, name) == before[name] for name in _STATE):
                grant.binding[origin] = ModelBinding.model_validate({"model_key": origin, **after})


class Modes:
    """The permission mode of one run, its working copies and the steps it inserts before a tool step."""

    def __init__(
        self, mode: str, always_ask: Sequence[str], run_dir: Path, tools: ToolPort, host: HostPort, store: ResultStore,
        writer: JournalWriter, producer: Callable[[], Provenance], leases: _Leases, port: ApprovalPort, run_id: str,
        events: Sequence[Event],
    ) -> None:  # fmt: skip
        """Serve the run in `run_dir`; `events` are the journal replayed."""
        self.run_dir, self.copies = run_dir, dict[str, str]()
        self.records: dict[str, Mapping[str, JsonValue]] = {}  # working copy key to the record of the step that took it
        self.approvals = ModeApprovals(mode, self.copies, port, host, store, writer, producer, run_id, events)
        self._mode, self._always, self._tools, self._host, self._store = mode, frozenset(always_ask), tools, host, store
        self._writer, self._producer, self._leases, self._lock = writer, producer, leases, asyncio.Lock()
        copied = {e.path for e in events if isinstance(p := e.payload, ev.StepStarted) and p.name == "working_copy"}
        self._taken = {
            e.path.split("~")[0]: p.result.summary for e in events
            if e.path in copied and e.path and isinstance(p := e.payload, ev.StepCompleted) and p.result
        }  # fmt: skip

    async def enter(
        self, ctx: _Step, path: str, name: str, args: _Obj, info: ToolInfo | None, journaled: _Obj | None,
        under: Approval | None,
    ) -> tuple[_Obj, Approval | None]:  # fmt: skip
        """The inserted steps before the tool step at `path`; the arguments and approval it runs with.

        `info` is the tool of a live step; a recorded step (`journaled` its arguments) replays from the journal alone.
        """
        async with self._lock:
            param = info.model_param if info is not None else None
            key = args.get(param) if param is not None else None
            if (taken := self._taken.get(path)) is not None:
                await self._copy(ctx, path, str(taken["model"]), None)
            elif info is not None and self._copies_first(info, key):
                await self._copy(ctx, path, str(key), info.host_key)
            args = {k: self._swap(k, v, param, journaled) for k, v in args.items()}
            apath = inserted_path(path, "pre", "approve")
            preview = self.approvals.stored(apath)
            if preview is None and info is not None and under is None and self._asks(name, info, args):
                await self._leases.acquire(info.host_key)
                preview = await self._tools.preview(name, args)
            if preview is None:
                return args, under
            approval = await ctx._approved(apath, f"Apply {name}", preview, ApprovalKind.CHANGE_SET, engine=True)
            if not approval.approved or approval.rejected_items:
                raise errors.ApprovalRejected(f"the approval of {name} was rejected", evidence=[approval.request_id])
            bound = {m.model_key for m in preview.models}
            written = info.effect == "write" if info is not None else under is None
            named = {str(key), str(args.get(param or ""))}  # the model as the block names it, and its working copy
            return args, approval if written and bound & named else under

    def _copies_first(self, info: ToolInfo, key: JsonValue) -> bool:
        """A write, in `work_on_copy`, to a model without a working copy (an `open` tool is none)."""
        return (
            self._mode == _COPY and info.effect == "write" and info.action != "open"
            and isinstance(key, str) and key not in {*self.copies, *self.records}
        )  # fmt: skip

    def _swap(self, key: str, value: JsonValue, param: str | None, journaled: _Obj | None) -> JsonValue:
        copy = self.copies.get(value) if isinstance(value, str) else None
        wanted = key == param if journaled is None else journaled.get(key) == copy
        return copy if copy is not None and wanted else value

    def _asks(self, name: str, info: ToolInfo, args: _Obj) -> bool:
        """A delete, a save over an original, an always-ask tool, or any write in `approve_each_write`."""
        return (
            info.action == "delete" or info.overwrites_original(args) or name in self._always
            or (self._mode == _EACH and info.effect == "write")
        )  # fmt: skip

    async def _state(self, key: str) -> HostModelState | None:
        instance = await self._host.locate(key)
        state = None if instance is None else await self._host.model_state(key, instance.instance_id)
        return state if state is not None and state.loaded else None

    async def _copy(self, ctx: _Step, path: str, origin: str, host_key: str | None) -> None:
        """Take, or replay, the working copy of `origin` as `<path>~pre.working_copy.<origin>` (spec 4.7)."""
        step, args = inserted_path(path, "pre", "working_copy", path_key(origin)), _Obj(model=origin)
        recorded = ctx._look(step, "read", "working_copy", args)
        done = None if recorded is None else ctx._replayed(recorded)
        if done is None and host_key is not None:
            await self._leases.acquire(host_key)
            done = await self._take(ctx, step, origin, args)
        if done is not None:
            kept = done.summary
            self.copies[origin], self.records[str(kept["copy"])] = str(kept["copy"]), kept
            self.approvals.rebase(origin, cast(_Obj, kept["before"]), cast(_Obj, kept["after"]))

    async def _take(self, ctx: _Step, step: str, origin: str, args: _Obj) -> ev.StepResult | None:
        before = await self._state(origin)
        if before is None:  # not open: the step on it is refused later (`model_open`)
            return None
        began = ctx._begin(step, 1, "read", "working_copy", args, effect="read", model_key=origin)
        (folder := self.run_dir / "copies").mkdir(parents=True, exist_ok=True)
        copy = await self._host.working_copy(origin, folder)
        after = await self._state(copy)
        if after is None:
            message = f"the working copy {copy} of {origin} is not open"
            raise ContractError(ErrorCode.PRECONDITION_FAILED, message, precondition=Precondition.model_open)
        kept: _Obj = {
            "model": origin, "copy": copy, "before": before.model_dump(include=set(_STATE), mode="json"),
            "after": after.model_dump(include=set(_STATE), mode="json"),
        }  # fmt: skip
        names = [file.name for file in self._host.model_files(copy)]
        origins = [file.name for file in self._host.model_files(origin)]
        saved = {**cast(_Obj, kept["after"]), "model_key": copy, "file_name": names[0], "role": "working_copy"}
        saved |= {"origin_sha256": before.file_sha256, "origin_file_names": cast(JsonValue, origins)}
        self._writer.append(EventType.MODEL_SAVED, saved, path=step)
        stored = self._store.put("harness.journal_blob/1", {"value": kept}, self._producer())
        done = ev.StepResult(ref=stored.result_id, summary=kept, warnings=[], complete=True)
        ctx._done(step, 1, began, done)
        return done


class _Leases(Protocol):
    async def acquire(self, host_key: str) -> None: ...
