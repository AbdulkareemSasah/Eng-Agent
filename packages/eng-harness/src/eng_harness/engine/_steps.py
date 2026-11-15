"""Step paths, scopes, `op_id`, overlap detection, and the parallel and attempts drivers (spec 0001 4.3.1).

Purpose: a step's identity is its path, which depends only on argument position and call order, never on completion
order (S-10 "parallel determinism"). A `Scope` holds the counter of one block, parallel child or attempts iteration;
the current scope is a context variable, so each task of `parallel` has its own. The helpers take an `execute(path)`
callable, so the ctx implementation (plan task T10) and the tests share them before a runner exists.
Errors: `BlockRuleViolation` for a step outside a run, a second step in progress in one scope, or a path that grows
past the limit; `ValueError` for a path, key or attempt number that breaks the grammar (an engine bug, not block code).
"""

import asyncio
import hashlib
import inspect
import re
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal, Self

from eng_harness import errors
from eng_harness.ctx import Attempt

__all__ = [
    "MAX_PATH_LENGTH",
    "AttemptIterator",
    "Scope",
    "attempts",
    "block_step",
    "current_scope",
    "inserted_path",
    "op_id",
    "parallel",
    "resume_path",
    "root_scope",
    "step",
    "validate_path",
]

MAX_PATH_LENGTH = 1024  # spec 4.3.1: at most 1024 characters

_INDEX = r"(?:0|[1-9][0-9]*)"
_KIND = r"[a-z][a-z0-9_]*"
_KEY = r"[A-Za-z0-9_.:-]{1,200}"
_SUFFIX = rf"~(?:pre|post|end|host)\.{_KIND}(?:\.{_KEY})?"
_PATH = re.compile(rf"{_INDEX}(?:/{_INDEX})*(?:{_SUFFIX})?|~end\.{_KIND}(?:\.{_KEY})?|@resume{_INDEX}\.{_KIND}\.{_KEY}")

# Class rank of the error `parallel` raises (spec 4.3.2): the first class wins, then the lowest child index.
_RANK: tuple[type[BaseException], ...] = (
    errors.ReplayDivergence,
    errors.NeedsReconciliation,
    errors.BlockRuleViolation,
    errors.Escalation,
    errors.Pause,
    errors.StepError,
)

_CURRENT: ContextVar[Scope | None] = ContextVar("eng_harness_step_scope", default=None)


def validate_path(path: str) -> str:
    """Return `path` when it fits the grammar of spec 4.3.1 and `MAX_PATH_LENGTH`.

    Raises:
        ValueError: the path does not match the grammar or is too long.
    """
    if len(path) > MAX_PATH_LENGTH or _PATH.fullmatch(path) is None:
        raise ValueError(f"invalid step path {path[:80]!r}")
    return path


def inserted_path(base: str, phase: Literal["pre", "post", "end", "host"], kind: str, key: str | None = None) -> str:
    """Path of an engine-inserted step: `base~phase.kind[.key]`; `base` is empty only for the root block's `end`.

    Raises:
        ValueError: the result does not fit the grammar.
    """
    return validate_path(f"{base}~{phase}.{kind}" + (f".{key}" if key is not None else ""))


def resume_path(number: int, kind: str, key: str) -> str:
    """Path `@resume<number>.<kind>.<key>` of a housekeeping step of a resume (never replayed).

    A `key` outside the grammar of a path key (a model key that is a file path) takes its hash form, spec 4.3.1.

    Raises:
        ValueError: the result does not fit the grammar.
    """
    if re.fullmatch(_KEY, key) is None:
        key = "h" + hashlib.sha256(key.encode()).hexdigest()[:12]
    return validate_path(f"@resume{number}.{kind}.{key}")


def op_id(run_id: str, path: str, attempt: int) -> str:
    """The idempotency id of a write: `"op_"` and the first 32 hex digits of sha256 of `run_id\\npath\\nattempt` (AC6).

    Raises:
        ValueError: `attempt` is below 1 (attempts start at 1) or `path` breaks the grammar.
    """
    if attempt < 1:
        raise ValueError(f"attempt must be at least 1, got {attempt}")
    digest = hashlib.sha256(f"{run_id}\n{validate_path(path)}\n{attempt}".encode()).hexdigest()
    return "op_" + digest[:32]


class Scope:
    """The counter of one scope and its one step in progress; `prefix` is the path of the scope ("" for the root)."""

    def __init__(self, prefix: str) -> None:
        """Start a scope whose first step is `prefix/0` (`0` for the root)."""
        self._prefix = prefix
        self._next = 0
        self._busy = False
        self._inner: Scope | None = None  # the current iteration of an attempts loop in progress

    def begin(self) -> str:
        """Take the next path and mark a step in progress. A refused call takes no index.

        Raises:
            BlockRuleViolation: a step is already in progress here (overlap outside `parallel`) or the path is too long.
        """
        if self._busy:
            raise errors.BlockRuleViolation(f"a second step started in scope {self._prefix!r} while one is in progress")
        path = f"{self._prefix}/{self._next}" if self._prefix else str(self._next)
        if len(path) > MAX_PATH_LENGTH:
            raise errors.BlockRuleViolation(f"step path longer than {MAX_PATH_LENGTH} characters")
        self._busy = True
        self._next += 1
        return path

    def end(self) -> None:
        """Mark the step in progress as finished."""
        self._busy = False

    def innermost(self) -> Scope:
        """The scope that takes the next step: follows the attempts iterations in progress."""
        scope: Scope = self
        while scope._inner is not None:
            scope = scope._inner
        return scope


@contextmanager
def root_scope() -> Iterator[Scope]:
    """Run with a fresh root scope (paths `0`, `1`, ...), restoring the previous scope after."""
    scope = Scope("")
    token = _CURRENT.set(scope)
    try:
        yield scope
    finally:
        _CURRENT.reset(token)


def current_scope() -> Scope:
    """The scope that takes the next step of the running task.

    Raises:
        BlockRuleViolation: no run is active in this task.
    """
    scope = _CURRENT.get()
    if scope is None:
        raise errors.BlockRuleViolation("a step was requested outside a running block")
    return scope.innermost()


async def step[T](execute: Callable[[str], Awaitable[T]]) -> T:
    """Take the next path of the current scope and run `execute(path)` as its one step in progress.

    Raises:
        BlockRuleViolation: see `Scope.begin`; `execute` is not called then.
    """
    scope = current_scope()
    path = scope.begin()
    try:
        return await execute(path)
    finally:
        scope.end()


async def block_step[T](execute: Callable[[str], Awaitable[T]]) -> T:
    """Like `step`, for a child block: its own steps run in the scope `path`, so they get `path/0`, `path/1`.

    Raises:
        BlockRuleViolation: see `Scope.begin`.
    """
    scope = current_scope()
    path = scope.begin()
    token = _CURRENT.set(Scope(path))
    try:
        return await execute(path)
    finally:
        _CURRENT.reset(token)
        scope.end()


def _rank(error: BaseException) -> int:
    for rank, kind in enumerate(_RANK):
        if isinstance(error, kind):
            return rank
    return len(_RANK)


async def parallel[T](
    children: Sequence[Awaitable[T]],
    *,
    before: Callable[[str], Awaitable[None]] | None = None,
    after: Callable[[str, Sequence[str]], Awaitable[None]] | None = None,
    enter: Callable[[int], None] | None = None,
    leave: Callable[[], Sequence[str]] | None = None,
) -> list[T]:
    """Run `children` concurrently as one step: child `i` runs in scope `path/i`; results come in argument order.

    Every child runs to its end (none is cancelled). Then the error of the best class rank (`_RANK`; any other
    error ranks last) and the lowest child index is raised, never the first to fail in time (AC8).

    Raises:
        BlockRuleViolation: see `Scope.begin`; the children are not started and their coroutines are closed.
    """
    scope = current_scope()
    try:
        path = scope.begin()
    except errors.BlockRuleViolation:
        for child in children:
            if inspect.iscoroutine(child):
                child.close()
        raise
    if before is not None:  # a check before the children; on failure they are not started
        try:
            await before(path)
        except Exception:
            for child in children:
                if inspect.iscoroutine(child):
                    child.close()
            scope.end()
            raise
    values: dict[int, T] = {}
    failures: dict[int, BaseException] = {}
    reported: dict[int, Sequence[str]] = {}

    async def run_child(index: int, child: Awaitable[T]) -> None:
        _CURRENT.set(Scope(f"{path}/{index}"))  # this task's own context
        if enter is not None:
            enter(index)
        try:
            values[index] = await child
        except (errors.EngineStop, Exception) as error:  # kept in `failures` and raised below, never dropped
            failures[index] = error
        finally:
            if leave is not None:
                reported[index] = leave()

    try:
        async with asyncio.TaskGroup() as group:
            for index, child in enumerate(children):
                group.create_task(run_child(index, child))
    finally:
        scope.end()
    caught: BaseException | None = None
    if after is not None:  # post-checks; a child's error outranks one from here (AC8)
        try:
            keys = sorted({key for names in reported.values() for key in names})
            await after(path, keys)
        except (errors.EngineStop, Exception) as error:
            caught = error
    if failures:
        raise failures[min(failures, key=lambda index: (_rank(failures[index]), index))]
    if caught is not None:
        raise caught
    return [values[index] for index in range(len(children))]


class AttemptIterator:
    """Async iterator of `ctx.attempts`: iteration `i` of the loop at `path` runs in scope `path/i`.

    The step stays in progress until the loop ends; `break` and an error are noticed when the iterator is dropped,
    so only the `async for` statement may hold it.
    """

    def __init__(self, limit: int) -> None:
        """Take the step path of the loop.

        Raises:
            ValueError: `limit` is below 1.
            errors.BlockRuleViolation: see `Scope.begin`.
        """
        if limit < 1:
            raise ValueError(f"attempts limit must be at least 1, got {limit}")
        self._done = True  # until the step is taken, so `__del__` has nothing to release
        self._parent = current_scope()
        self.path = self._parent.begin()
        self._done = False
        self._limit = limit
        self._count = 0
        self.exhausted = False  # True once every iteration ran without `break`: the caller escalates

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> Attempt:
        """Start the next iteration in its own scope, or end the loop after `limit` iterations."""
        self._parent._inner = None
        if self._count >= self._limit:
            self.exhausted = True
            self._finish()
            raise StopAsyncIteration
        index = self._count
        self._count += 1
        self._parent._inner = Scope(f"{self.path}/{index}")
        return Attempt(index=index, is_last=index == self._limit - 1)

    def _finish(self) -> None:
        if not self._done:
            self._done = True
            self._parent._inner = None
            self._parent.end()

    def __del__(self) -> None:
        self._finish()


def attempts(limit: int) -> AttemptIterator:
    """Start the attempts loop of `limit` iterations; the caller checks the `BasisCount` and the cap (AC9).

    Raises:
        ValueError: `limit` is below 1.
        BlockRuleViolation: see `Scope.begin`.
    """
    return AttemptIterator(limit)
