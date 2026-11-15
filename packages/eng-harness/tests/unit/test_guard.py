"""The runtime guard of block and rule code (plan 0001 T17; spec 0001 4.3.4, AC18)."""

import asyncio
import ctypes
import importlib
import os
import socket
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workflows.ctx_flows import ChildInput, ChildOutput, flow
from workflows.rig import make_rig, request

from eng_harness.block import block
from eng_harness.ctx import BasisCount
from eng_harness.engine import RunStatus
from eng_harness.errors import BlockRuleViolation

_MODULE = "colorsys"  # a stdlib module that nothing else in the tests imports


def _write(path: Path) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("made")


def _import() -> object:
    sys.modules.pop(_MODULE, None)  # so the import statement runs, and raises the audit event `import`
    return importlib.import_module(_MODULE)


def _operations(folder: Path) -> dict[str, Callable[[], object]]:
    """One operation of each family that spec 4.3.4 lists, each of which would leave a trace if it ran."""
    keep = folder / "keep.txt"
    shared = "kernel32" if sys.platform == "win32" else None
    return {
        "open": lambda: _write(folder / "made.txt"),
        "mkdir": lambda: os.mkdir(folder / "made_dir"),
        "listdir": lambda: os.listdir(folder),
        "scandir": lambda: os.scandir(folder),
        "rename": lambda: os.rename(keep, folder / "moved.txt"),
        "remove": lambda: os.remove(keep),
        "popen": lambda: subprocess.Popen([sys.executable, "-c", "pass"]),
        "socket": lambda: socket.socket(),
        "sqlite": lambda: sqlite3.connect(folder / "made.db"),
        "ctypes": lambda: ctypes.CDLL(shared),
        "import": _import,
    }  # fmt: skip


def _try(name: str, operation: Callable[[], object], seen: list[str], done: list[str]) -> None:
    """Block code: run `operation`; a refusal is noted in `seen`, an operation that went through in `done`."""
    try:
        operation()
    except BlockRuleViolation:
        seen.append(name)
    except Exception:  # B-116: the operation was not refused, whatever it then raised
        done.append(name)
    else:
        done.append(name)


def test_guard_blocks_io_in_block_code(tmp_path: Path) -> None:
    rig = make_rig(tmp_path / "run")
    folder = tmp_path / "work"
    folder.mkdir()
    (folder / "keep.txt").write_text("kept", encoding="utf-8")
    operations = _operations(folder)
    seen: list[str] = []
    done: list[str] = []

    async def body(ctx: Any) -> list[str]:
        _try("direct:open", operations["open"], seen, done)  # before any ctx call: the root block is block code
        await ctx.tool("read_a", {"n": 0})  # the engine's work in the call is not refused
        for name, operation in operations.items():  # and the guard is back on after the call
            _try(name, operation, seen, done)
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.COMPLETED  # the engine's own I/O (journal, store) was not refused
    assert done == []
    assert seen == ["direct:open", *operations]
    assert sorted(p.name for p in folder.iterdir()) == ["keep.txt"]  # nothing was opened, made, moved or removed
    (folder / "after.txt").write_text("a", encoding="utf-8")  # outside block code the process may do I/O again


def test_guard_covers_parallel_children_and_child_blocks(tmp_path: Path) -> None:
    rig = make_rig(tmp_path / "run")
    seen: list[str] = []
    done: list[str] = []
    target = tmp_path / "never.txt"

    def attempt(name: str) -> None:
        _try(name, lambda: _write(target), seen, done)

    async def leg(ctx: Any, name: str) -> str:
        attempt(name + ":before")
        result = await ctx.tool("read_a", {"n": 1})  # the engine's work in a child is not refused
        attempt(name + ":after")
        return str(result.ref.ref)

    @block(name="inner", version=1)
    async def inner(ctx: Any, inp: ChildInput) -> ChildOutput:
        attempt("block:start")
        await ctx.tool("read_c", {"n": 2})
        attempt("block:after")
        return ChildOutput(refs=[])

    async def body(ctx: Any) -> list[str]:
        refs = await ctx.parallel(leg(ctx, "first"), leg(ctx, "second"))
        await ctx.block(inner, ChildInput(n=3))
        async for _ in ctx.attempts(BasisCount(2)):
            attempt("attempts:body")
            await ctx.tool("read_a", {"n": 4})
            attempt("attempts:after")
            break
        return [str(ref) for ref in refs]

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.COMPLETED
    assert done == []
    assert sorted(seen) == sorted(
        [f"{leg}:{when}" for leg in ("first", "second") for when in ("before", "after")]
        + ["block:start", "block:after", "attempts:body", "attempts:after"]
    )
    assert not target.exists()


def test_rule_guard_factory(tmp_path: Path) -> None:
    from eng_harness.engine import rule_guard

    target = tmp_path / "rule.txt"
    with rule_guard():
        with pytest.raises(BlockRuleViolation, match="open"):
            _write(target)
        with pytest.raises(BlockRuleViolation, match=r"subprocess\.Popen"):
            subprocess.Popen([sys.executable, "-c", "pass"])
    assert not target.exists()
    target.write_text("outside", encoding="utf-8")  # the guard ends with the `with`
    assert target.read_text(encoding="utf-8") == "outside"
    with pytest.raises(ZeroDivisionError), rule_guard():
        raise ZeroDivisionError  # an error of the body leaves the guard too
    target.write_text("again", encoding="utf-8")


def test_blocked_events_are_the_ones_of_the_spec() -> None:
    from eng_harness.engine._guard import blocked

    listed = [
        "open", "os.remove", "os.rename", "os.mkdir", "os.listdir", "os.scandir", "os.system", "os.exec",
        "os.posix_spawn", "os.spawn", "os.startfile", "subprocess.Popen", "sqlite3.connect", "import",
        "socket.connect", "socket.bind", "socket.__new__", "ctypes.dlopen", "ctypes.dlsym",
    ]  # fmt: skip
    assert [event for event in listed if not blocked(event)] == []
    others = ["os.getcwd", "os.chmod", "sys.addaudithook", "exec", "compile", "socketserver", "sqlite3.execute"]
    others += ["ctypesx", "opened"]
    assert [event for event in others if blocked(event)] == []


def test_the_guard_state_follows_the_calls() -> None:
    from eng_harness.engine._guard import block_code, engine_work, in_block_code

    @engine_work
    async def inside() -> bool:
        return in_block_code()

    async def states() -> list[bool]:
        outside = in_block_code()
        with block_code():
            guarded = in_block_code()
            during = await inside()
            after = in_block_code()
        return [outside, guarded, during, after, in_block_code()]

    assert asyncio.run(states()) == [False, True, False, True, False]
