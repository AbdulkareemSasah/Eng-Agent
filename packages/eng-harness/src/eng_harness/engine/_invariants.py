"""Invariants 1, 2, 3 and 7: check after write, engineering references, staleness, save before analysis (spec 4.6).

Purpose: a write marks its model dirty; a read of that model, any calc and the block's return run `check_model` first.
An engineering parameter accepts only a reference. References passed to a calc are resolved, with that argument's
`RefRule`. A tool whose action is analysis or design is preceded by a save. Units: none. Errors: `ModelIntegrityError`,
`ContractError` (`INVALID_ARGUMENT`, `REF_*`), `ToolFailed` for a save the host refuses, `BlockRuleViolation` when
parallel siblings conflict on a model.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextvars import ContextVar
from typing import Literal, Protocol

from eng_contract.envelope import FailureEnvelope, HostInfo, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode, ErrorDetail
from eng_contract.refs import Ref, RefRule, resolve_ref
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness import errors
from eng_harness.ctx import CalcResult, ReadResult, ToolResult
from eng_harness.engine._replay import Recorded
from eng_harness.engine._steps import inserted_path
from eng_harness.journal import EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import HostPort

_Obj = dict[str, JsonValue]
_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")  # spec 4.3.1 grammar of a path key
_ANALYSE = ("analysis", "design")  # spec 4.6 invariant 7
_REF = Ref | ToolResult | CalcResult | ReadResult
_Phase = Literal["pre", "post", "end"]
_DIRTY: ContextVar[dict[str, bool] | None] = ContextVar("eng_harness_dirty_models", default=None)
_BOARD: ContextVar[tuple[SiblingBoard, int] | None] = ContextVar("eng_harness_sibling_board", default=None)


def path_key(model: str) -> str:
    """Itself when it fits the path grammar, else `h` plus 12 hex digits of its SHA-256 (spec 4.3.1)."""
    if _KEY.fullmatch(model):
        return model
    return "h" + hashlib.sha256(model.encode()).hexdigest()[:12]  # spec 4.3.1: the first 12 hex characters


def dirty_flags() -> dict[str, bool]:
    """The dirty flags of the current block or parallel child; `BlockRuleViolation` when no run installed them."""
    flags = _DIRTY.get()
    if flags is None:
        raise errors.BlockRuleViolation("a step was requested outside a running block")
    return flags


class _Ctx(Protocol):
    """The journal and replay operations an inserted step uses."""

    def _begin(self, path: str, attempt: int, kind: str, name: str, args: _Obj, **fields: object) -> int: ...

    def _done(self, path: str, attempt: int, began: int, done: ev.StepResult, **fields: object) -> None: ...

    def _fail(self, path: str, attempt: int, began: int, error: ErrorDetail | ev.HarnessError, retry: bool) -> None: ...

    def _look(
        self, path: str, kind: str, name: str, args: _Obj, child: tuple[str, str] | None = None
    ) -> Recorded | None: ...

    def _replayed(self, recorded: Recorded, *, calc: bool = False) -> ev.StepResult | None: ...


class SiblingBoard:
    """Models one parallel's children have touched, so a conflicting sibling stops before its port call (spec 4.3.1)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._touched: dict[str, list[tuple[int, bool]]] = {}

    async def admit(self, child: int, model: str, write: bool) -> None:
        """`BlockRuleViolation` when `child` reads or writes what a sibling wrote, or writes what a sibling read."""
        async with self._lock:
            others = [item for item in self._touched.get(model, ()) if item[0] != child]
            if any(wrote or write for _, wrote in others):
                raise errors.BlockRuleViolation(f"parallel siblings conflict on model {model}")
            self._touched.setdefault(model, []).append((child, write))


def _stored(envelope: SuccessEnvelope) -> ev.StepResult:
    warned = [w.model_dump(mode="json") for w in envelope.warnings]
    return ev.StepResult(ref=envelope.result_id, summary=envelope.summary, warnings=warned, complete=envelope.complete)


def _walk(value: object, path: str = "") -> Iterator[tuple[str, _REF]]:
    """References in `value`, each with its field path (spec 4.6 invariant 3)."""
    if isinstance(value, _REF):
        if path:
            yield path, value
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, Sequence) and not isinstance(value, str):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")


class Guard:
    """The invariant checks of one run. `install` runs in the block's task; each parallel child calls `enter`."""

    def __init__(
        self, host: HostPort, store: ResultStore, writer: JournalWriter, producer: Callable[[], Provenance]
    ) -> None:
        self._host, self._store, self._writer, self._producer = host, store, writer, producer
        self._revision: dict[str, int] = {}

    def install(self) -> None:
        """The root block's dirty flags, in the task that runs it."""
        _DIRTY.set({})

    def enter(self, board: SiblingBoard, index: int) -> None:
        """A parallel child's own dirty flags and the shared sibling board (spec 4.3.1)."""
        _DIRTY.set({})
        _BOARD.set((board, index))

    def dirty_models(self) -> list[str]:
        """The models the current child left dirty, in model-key order."""
        return sorted(key for key, dirty in dirty_flags().items() if dirty)

    def note(self, host: HostInfo | None) -> None:
        """A model's revision from a result's `provenance.host` (spec 4.6)."""
        if host is not None:
            self._revision[host.model_id] = host.model_revision

    def note_stored(self, ref: str) -> None:
        """The revision of a stored result, when the store still has it."""
        try:
            record = self._store.get(ref)
        except ContractError as exc:
            if exc.detail.code is not ErrorCode.REF_NOT_FOUND:
                raise
            return
        self.note(record.producer.host)

    def mark(self, model: str | None) -> None:
        """A successful write leaves `model` dirty (spec 4.6 invariant 1)."""
        if model:
            dirty_flags()[model] = True

    async def touch(self, model: str | None, write: bool) -> None:
        """Before a port call in a parallel child, refuse a sibling conflict (spec 4.3.1)."""
        board = _BOARD.get()
        if board is None or not model:
            return
        await board[0].admit(board[1], model, write)

    def literals(self, args: Mapping[str, object], params: Sequence[str]) -> None:
        """`INVALID_ARGUMENT` when an engineering parameter is not a reference, before the port call (spec 4.6 #2)."""
        for field in params:
            if field not in args or isinstance(args[field], _REF):
                continue
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, "an engineering quantity must be a reference to a result", field=field
            )

    def refs(self, args: Mapping[str, object], rules: Mapping[str, RefRule]) -> None:
        """Resolve every reference with the calc's rule for that path, or the default rule (spec 4.6 #3)."""
        for path, value in _walk(args):
            rule = rules[path] if path in rules else RefRule()
            if rule.field is None:
                rule = rule.model_copy(update={"field": path})
            target = value if isinstance(value, Ref) else value.ref
            resolve_ref(target, rule, self._store, self._revision.get)

    async def prepare(self, ctx: _Ctx, path: str, model: str | None, effect: str, action: str | None) -> None:
        """The inserted steps before a tool: a check for a dirty read, then a save before analysis or design."""
        if model and effect == "read" and dirty_flags().get(model):
            await self.check(ctx, path, "pre", model)
        if model and action in _ANALYSE:
            await self.save(ctx, path, model)

    async def sweep(self, ctx: _Ctx, base: str, phase: _Phase, *, live: bool = True) -> None:
        """Check every dirty model in key order. `live` false only replays a recorded check (spec 4.5.2, 4.6 #1)."""
        pending = sorted(key for key, dirty in dirty_flags().items() if dirty)
        for model in pending:
            await self.check(ctx, base, phase, model, live=live)

    async def check(self, ctx: _Ctx, base: str, phase: _Phase, model: str, *, live: bool = True) -> None:
        """Run or replay `check_model` for `model`; a failure is `ModelIntegrityError` (spec 4.6 invariant 1)."""
        path = inserted_path(base, phase, "check_model", path_key(model))
        args: _Obj = {"model": model}
        recorded = ctx._look(path, "read", "check_model", args)
        if recorded is not None and ctx._replayed(recorded) is not None:
            dirty_flags()[model] = False
            return
        if not live:
            return
        began = ctx._begin(path, 1, "read", "check_model", args, effect="read", model_key=model)
        try:
            envelope = await self._host.check_model(model)
        except ContractError as exc:
            self._failed(ctx, path, began, model, exc.detail.message)
            raise errors.ModelIntegrityError(f"the check of {model} failed: {exc.detail.message}") from exc
        if isinstance(envelope, FailureEnvelope):
            self._failed(ctx, path, began, model, envelope.error.message)
            raise errors.ModelIntegrityError(f"the check of {model} failed: {envelope.error.message}")
        ctx._done(path, 1, began, _stored(envelope))
        self._enforced(path, 1, model, "pass")
        dirty_flags()[model] = False

    def _failed(self, ctx: _Ctx, path: str, began: int, model: str, message: str) -> None:
        text = f"the check of {model} failed: {message}"
        error = ev.HarnessError(harness_code=errors.HarnessCode.MODEL_INTEGRITY, message=text)
        ctx._fail(path, 1, began, error, False)
        self._enforced(path, 1, model, "fail")

    async def save(self, ctx: _Ctx, base: str, model: str) -> None:
        """Save `model` before analysis or design and journal `model_saved` with role `pre_analysis` (spec 4.6 #7)."""
        path = inserted_path(base, "pre", "save", path_key(model))
        args: _Obj = {"model": model, "role": "pre_analysis"}
        recorded = ctx._look(path, "read", "save", args)
        if recorded is not None and ctx._replayed(recorded) is not None:
            return
        began = ctx._begin(path, 1, "read", "save", args, effect="read", model_key=model)
        try:
            saved = await self._host.save(model, "pre_analysis")
        except ContractError as exc:
            ctx._fail(path, 1, began, exc.detail, False)
            raise errors.ToolFailed(exc.detail) from exc
        stored = self._store.put("harness.run_output/1", {"value": saved.model_dump(mode="json")}, self._producer())
        done = ev.StepResult(ref=stored.result_id, summary={"role": "pre_analysis"}, warnings=[], complete=True)
        ctx._done(path, 1, began, done)
        saved_body = {"model_key": model, "role": "pre_analysis", **saved.model_dump(mode="json")}
        self._writer.append(EventType.MODEL_SAVED, saved_body, path=path)
        self._enforced(path, 7, model, "pass")

    def _enforced(self, path: str, invariant: int, model: str, outcome: str) -> None:
        body = {"invariant": invariant, "model_key": model, "outcome": outcome}
        self._writer.append(EventType.CHECK_ENFORCED, body, path=path)
