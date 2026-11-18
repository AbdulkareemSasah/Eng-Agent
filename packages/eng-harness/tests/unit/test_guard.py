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
from eng_contract.envelope import Provenance
from eng_contract.errors import ErrorCode
from fakes.ports import FakeCalcPort, failure
from pydantic import JsonValue
from workflows.chain import ChainInput, ChainOutput
from workflows.ctx_flows import ChildInput, ChildOutput, child, flow
from workflows.rig import Rig, Spy, make_rig, request

from eng_harness.basis import StoreBasisPort
from eng_harness.block import BlockDef, Registry, block, workflow
from eng_harness.ctx import BasisCount
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunStatus
from eng_harness.errors import BlockRuleViolation, ToolFailed

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


def test_guard_is_back_after_a_failing_ctx_call(tmp_path: Path) -> None:
    """The state is restored on the exception paths of `engine_work`: a block that catches the error stays guarded."""
    rig = make_rig(tmp_path / "run")
    rig.host.outcomes["read_a"].append(failure(ErrorCode.NOT_FOUND, "gone"))
    target = tmp_path / "never.txt"
    seen: list[str] = []
    done: list[str] = []

    async def broken_child(ctx: Any) -> list[str]:
        raise ZeroDivisionError

    broken_block = child(broken_child)  # a block is built outside block code (its source is read for the hash)

    async def broken_leg(ctx: Any) -> str:
        raise KeyError("leg")

    async def ok_leg(ctx: Any) -> str:
        await ctx.tool("read_b", {"n": 9})
        return "ok"

    async def body(ctx: Any) -> list[str]:
        caught: list[type[Exception]] = []
        try:
            await ctx.tool("read_a", {"n": 0})  # the call raised ...
        except ToolFailed as failed:
            caught.append(type(failed))
        _try("after:tool", lambda: _write(target), seen, done)  # ... and the guard is on again
        try:
            await ctx.block(broken_block, ChildInput(n=1))
        except ZeroDivisionError as failed:
            caught.append(type(failed))
        _try("after:block", lambda: _write(target), seen, done)
        try:
            await ctx.parallel(broken_leg(ctx), ok_leg(ctx))
        except KeyError as failed:
            caught.append(type(failed))
        _try("after:parallel", lambda: _write(target), seen, done)
        assert caught == [ToolFailed, ZeroDivisionError, KeyError]
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.COMPLETED
    assert done == []
    assert seen == ["after:tool", "after:block", "after:parallel"]
    assert not target.exists()


def test_engine_work_restores_the_state_when_the_call_raises() -> None:
    from eng_harness.engine._guard import block_code, engine_work, in_block_code

    states: list[bool] = []

    @engine_work
    async def failing() -> None:
        states.append(in_block_code())  # the engine's own work is not block code
        raise ZeroDivisionError

    async def run() -> bool:
        with block_code():
            with pytest.raises(ZeroDivisionError):
                await failing()
            return in_block_code()

    assert asyncio.run(run()) is True  # block code again after the raise
    assert states == [False]


def test_engine_section_restores_the_state_when_the_body_raises() -> None:
    from eng_harness.engine._guard import block_code, engine_section, in_block_code

    states: list[bool] = []

    def failing() -> None:
        with engine_section():
            states.append(in_block_code())
            raise ZeroDivisionError

    with engine_section():
        states.append(in_block_code())
    assert in_block_code() is False
    with block_code():
        with engine_section():
            states.append(in_block_code())
        states.append(in_block_code())
        with pytest.raises(ZeroDivisionError):
            failing()
        states.append(in_block_code())
    assert states == [False, False, True, False, True]
    assert in_block_code() is False


def test_the_hook_is_installed_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    from eng_harness.engine import _guard

    calls: list[object] = []
    _guard._install.cache_clear()
    monkeypatch.setattr(sys, "addaudithook", calls.append)
    try:
        with _guard.block_code():
            pass
        with _guard.block_code():
            pass
        with _guard.rule_guard():
            pass
        assert calls == [_guard._hook]
    finally:
        _guard._install.cache_clear()  # the real hook is installed already (and cannot be removed): restore the cache
        monkeypatch.undo()
        _guard._install.cache_clear()
        _guard._install()


def _store_engine(rig: Rig, *workflows: BlockDef[Any, Any]) -> Engine:
    """An engine over `rig` whose basis port reads from `rig.store`."""
    calc = FakeCalcPort(rig.run_class, rig.calc_infos)
    calc.results, calc.runs = rig.calc_results, rig.calc_runs
    ports = EnginePorts(
        tool=Spy("tool", rig.host, rig.log),
        host=Spy("host", rig.host, rig.log),
        calc=Spy("calc", calc, rig.log),
        basis=Spy("basis", StoreBasisPort(rig.store), rig.log),
        approvals=Spy("approvals", rig.approvals, rig.log),
        inputs=Spy("inputs", rig.inputs, rig.log),
    )
    return Engine(rig.workspace, Registry(workflows), ports, rig.store, EngineSettings(), rig.clock, rig.ids)


def test_basis_load_is_engine_work(tmp_path: Path) -> None:
    """The first `ctx.basis` read loads via `StoreBasisPort` as engine work; the guard stays on around it (AC18)."""
    rig = make_rig(tmp_path / "run")
    path = "modeling.merge_tolerance_mm"
    fields: dict[str, JsonValue] = {
        path: {
            "value": 2.5, "unit": "mm", "source": "engineer:synthetic@2026-01-01T00:00:00.000Z",
            "confirmed": True, "citation": None,
        }
    }  # fmt: skip
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=rig.clock.now(), duration_ms=0)
    basis_ref = rig.store.put("basis.design_basis/1", {"template": None, "fields": fields}, producer).result_id

    @workflow(name="read_ref", version=1, description="Reads the basis record ref with no required_basis.")
    async def read_ref(ctx: Any, inp: ChainInput) -> ChainOutput:
        return ChainOutput(refs=[ctx.basis.record_ref().ref])

    @workflow(name="read_qty", version=1, description="Reads a declared basis quantity.", required_basis=(path,))
    async def read_qty(ctx: Any, inp: ChainInput) -> ChainOutput:
        qty = ctx.basis.quantity(path)
        assert (qty.value, qty.unit) == (2.5, "mm")
        return ChainOutput(refs=[ctx.basis.ref(path).ref])

    target = tmp_path / "after_basis.txt"

    async def read_then_open(ctx: Any) -> list[str]:
        _ = ctx.basis.record_ref()
        _write(target)
        return []

    first = asyncio.run(_store_engine(rig, read_ref).start(request(workflow="read_ref", basis_ref=basis_ref)))
    assert first.status is RunStatus.COMPLETED
    assert isinstance(first.output, ChainOutput)
    assert first.output.refs == [basis_ref]

    second = asyncio.run(_store_engine(rig, read_qty).start(request(workflow="read_qty", basis_ref=basis_ref)))
    assert second.status is RunStatus.COMPLETED
    assert isinstance(second.output, ChainOutput)
    assert second.output.refs == [f"{basis_ref}#/fields/{path}/value"]

    third = asyncio.run(
        _store_engine(rig, flow(read_then_open, name="read_then_open")).start(
            request(workflow="read_then_open", basis_ref=basis_ref)
        )
    )
    assert third.status is RunStatus.NEEDS_ENGINEER
    assert third.escalation is not None
    assert third.escalation.reason == "block_rule_violation"
    assert "open" in third.escalation.detail
    assert not target.exists()
