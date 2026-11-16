"""The runtime guard of block and rule code (spec 0001 4.3.4 rule 1, AC18).

Purpose: one `sys.addaudithook` hook per process refuses file, process, socket, SQLite, `ctypes` and `import` events
while the context variable `in_block_code` is true. It is true whenever control is in block or rule code and false only
while the engine does its own step work, so each ctx call is wrapped in `engine_work`, and the places that hand control
back to block code (the root block, a child block's function, a child of `ctx.parallel`, `rule_guard()`) set it true.
Units: none. Errors: `BlockRuleViolation` from the hook; the operation does not happen.
"""

import functools
import sys
from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar

from eng_harness import errors

__all__ = ["block_code", "blocked", "engine_work", "enter_block_code", "in_block_code", "rule_guard"]

_IN_BLOCK_CODE: ContextVar[bool] = ContextVar("eng_harness_in_block_code", default=False)
_EVENTS = frozenset(
    {
        "open", "os.remove", "os.rename", "os.mkdir", "os.listdir", "os.scandir", "os.system", "os.exec",
        "os.posix_spawn", "os.spawn", "os.startfile", "subprocess.Popen", "sqlite3.connect", "import",
    }
)  # fmt: skip
_PREFIXES = ("socket.", "ctypes.")


def blocked(event: str) -> bool:
    """True for an audit event that block and rule code may not cause (spec 4.3.4 rule 1)."""
    return event in _EVENTS or event.startswith(_PREFIXES)


def _hook(event: str, _args: tuple[object, ...]) -> None:
    if _IN_BLOCK_CODE.get() and blocked(event):
        raise errors.BlockRuleViolation(f"block and rule code may not do I/O: the audit event {event}")


@functools.cache
def _install() -> None:
    """Install the hook once per process; an audit hook cannot be removed (spec 4.3.4, risk R2)."""
    sys.addaudithook(_hook)


def in_block_code() -> bool:
    """True while control is in block or rule code in this task."""
    return _IN_BLOCK_CODE.get()


def enter_block_code() -> None:
    """Make this task's context block code for good: for a task of its own, such as a child of `ctx.parallel`."""
    _install()
    _IN_BLOCK_CODE.set(True)


@contextmanager
def block_code() -> Iterator[None]:
    """Run the body as block code, and restore the earlier state after it, also when the body raises."""
    _install()
    token = _IN_BLOCK_CODE.set(True)
    try:
        yield
    finally:
        _IN_BLOCK_CODE.reset(token)


def rule_guard() -> AbstractContextManager[None]:
    """The context manager the decision layer runs rules in: it installs the hook if needed and guards the body."""
    return block_code()


def engine_work[**P, T](call: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Wrap a ctx call: its own work is not block code; the earlier state is back when it returns or raises."""

    @functools.wraps(call)
    async def run(*args: P.args, **kwargs: P.kwargs) -> T:
        token = _IN_BLOCK_CODE.set(False)
        try:
            return await call(*args, **kwargs)
        finally:
            _IN_BLOCK_CODE.reset(token)

    return run
