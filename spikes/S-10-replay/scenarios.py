"""S-10 spike: a fake host, tools and blocks used by check.py and worker.py. Throwaway.

The fake host is a non-idempotent writer (like the Sasaah servers): every call that reaches it appends to a ledger,
whatever its op_id. Duplicate frames in the ledger therefore prove a write ran twice. `reconcile_operation` looks the
op_id up in the ledger. A second file logs every call that reached a tool function.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from engine import Ctx, StepFailed, ToolError, ToolSpec


class FakeHost:
    def __init__(self, host_dir: Path) -> None:
        self.dir = host_dir
        host_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = host_dir / "ledger.jsonl"
        self.calls = host_dir / "calls.jsonl"
        self.pace = host_dir / "pace.json"  # per frame latency in ms, set by the test: host latency, not block input

    # -- files ---------------------------------------------------------------------------------------------

    def _append(self, p: Path, row: dict[str, Any]) -> None:
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()

    def ledger_rows(self) -> list[dict[str, Any]]:
        if not self.ledger.exists():
            return []
        return [json.loads(x) for x in self.ledger.read_text(encoding="utf-8").splitlines() if x]

    def call_rows(self) -> list[dict[str, Any]]:
        if not self.calls.exists():
            return []
        return [json.loads(x) for x in self.calls.read_text(encoding="utf-8").splitlines() if x]

    def _delay_ms(self, name: str) -> float:
        if not self.pace.exists():
            return 0.0
        return float(json.loads(self.pace.read_text(encoding="utf-8")).get(name, 0))

    # -- tools ---------------------------------------------------------------------------------------------

    def tools(self, reconciler: bool = True) -> dict[str, ToolSpec]:
        fast = os.environ.get("S10_FAST") == "1"

        async def read_model(op_id: str) -> Any:
            self._append(self.calls, {"pid": os.getpid(), "tool": "read_model", "args": {}})
            return {"frames": len(self.ledger_rows())}

        async def slow_read(op_id: str, ms: int) -> Any:
            self._append(self.calls, {"pid": os.getpid(), "tool": "slow_read", "args": {"ms": ms}})
            await asyncio.sleep(0 if fast else ms / 1000)
            return {"slept": ms}

        async def fail_read(op_id: str) -> Any:
            self._append(self.calls, {"pid": os.getpid(), "tool": "fail_read", "args": {}})
            raise ToolError("NOT_FOUND", "no such object")

        async def add_frame(op_id: str, name: str) -> Any:
            self._append(self.calls, {"pid": os.getpid(), "tool": "add_frame", "args": {"name": name}, "op_id": op_id})
            d = self._delay_ms(name)
            if d:
                await asyncio.sleep(d / 1000)
            result = {"frame": name, "n": len(self.ledger_rows()) + 1}
            self._append(self.ledger, {"op_id": op_id, "name": name, "result": result})
            return result

        async def slow_write(op_id: str, name: str, ms: int) -> Any:
            self._append(self.calls, {"pid": os.getpid(), "tool": "slow_write", "args": {"name": name, "ms": ms}, "op_id": op_id})
            await asyncio.sleep(0 if fast else ms / 1000)  # the host applies the edit at the end of the call
            result = {"frame": name, "n": len(self.ledger_rows()) + 1}
            self._append(self.ledger, {"op_id": op_id, "name": name, "result": result})
            return result

        async def reconcile(op_id: str, args: dict[str, Any]) -> dict[str, Any]:
            for row in self.ledger_rows():
                if row["op_id"] == op_id:
                    return {"outcome": "applied", "result": row["result"]}
            return {"outcome": "not_applied"}

        rc = reconcile if reconciler else None
        return {
            "read_model": ToolSpec(read_model, "read"),
            "slow_read": ToolSpec(slow_read, "read"),
            "fail_read": ToolSpec(fail_read, "read"),
            "add_frame": ToolSpec(add_frame, "write", rc),
            "slow_write": ToolSpec(slow_write, "write", rc),
        }


# --------------------------------------------------------------------------------------------------------------
# Blocks. VERSION is recorded in run_started. Variants differ from "footing" in one way each (divergence tests).
# --------------------------------------------------------------------------------------------------------------

VERSION = "1"


async def footing(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:
    """Reads, sequential writes, a parallel group, a failing read the block handles, an approval, a final write."""
    base = await ctx.tool("read_model")
    await ctx.tool("add_frame", name="F1")
    await ctx.tool("add_frame", name="F2")
    par = await ctx.parallel(
        lambda c: c.tool("add_frame", name="P1"),
        lambda c: c.tool("slow_read", ms=40),
        lambda c: c.tool("add_frame", name="P2"),
    )
    try:
        await ctx.tool("fail_read")
        failed = None
    except StepFailed as exc:  # replayed from step_failed
        failed = exc.code
    try:
        appr = await ctx.approve("Promote working copy", {"frames": ["F1", "F2", "P1", "P2"], "limit_ref": inp["limit_ref"]})
    except Exception:  # must NOT swallow the pause (EngineStop is a BaseException)
        raise AssertionError("broad except swallowed an engine stop") from None
    last = await ctx.tool("add_frame", name="F3" if appr.approved else "F3-rejected")
    return {"base": base, "par": par, "failed": failed, "approved": appr.approved, "last": last}


async def v_args(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:  # changed argument on a recorded step
    await ctx.tool("read_model")
    await ctx.tool("add_frame", name="F1")
    await ctx.tool("add_frame", name="F2-changed")
    return {}


async def v_tool(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:  # different tool at a recorded step
    await ctx.tool("read_model")
    await ctx.tool("add_frame", name="F1")
    await ctx.tool("slow_read", ms=1)
    return {}


async def v_insert(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:  # a new step inserted before the frontier
    await ctx.tool("read_model")
    await ctx.tool("read_model")
    await ctx.tool("add_frame", name="F1")
    return {}


async def v_remove(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:  # a recorded step removed
    await ctx.tool("read_model")
    await ctx.tool("add_frame", name="F1")
    await ctx.parallel(lambda c: c.tool("add_frame", name="P1"))
    return {}


async def v_arity(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:  # parallel group with a different size
    await ctx.tool("read_model")
    await ctx.tool("add_frame", name="F1")
    await ctx.tool("add_frame", name="F2")
    await ctx.parallel(lambda c: c.tool("add_frame", name="P1"), lambda c: c.tool("add_frame", name="P2"))
    return {}


async def v_preview(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:  # the approval shows something else
    await ctx.tool("read_model")
    await ctx.tool("add_frame", name="F1")
    await ctx.tool("add_frame", name="F2")
    await ctx.parallel(
        lambda c: c.tool("add_frame", name="P1"),
        lambda c: c.tool("slow_read", ms=40),
        lambda c: c.tool("add_frame", name="P2"),
    )
    try:
        await ctx.tool("fail_read")
    except StepFailed:
        pass
    await ctx.approve("Promote working copy", {"frames": ["F1", "F2", "P1", "P2", "P3"], "limit_ref": inp["limit_ref"]})
    return {}


async def v_short(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:  # ends before recorded steps (unconsumed journal)
    await ctx.tool("read_model")
    await ctx.tool("add_frame", name="F1")
    await ctx.tool("add_frame", name="F2")
    await ctx.parallel(
        lambda c: c.tool("add_frame", name="P1"),
        lambda c: c.tool("slow_read", ms=40),
        lambda c: c.tool("add_frame", name="P2"),
    )
    return {}


async def v_tail(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:  # same prefix, extra steps after the frontier
    out = await footing(ctx, inp)
    await ctx.tool("add_frame", name="EXTRA")
    return out


async def par_block(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:
    """Five concurrent children of two steps each. Completion order is set by the host's pace file."""
    res = await ctx.parallel(*[_child(i) for i in range(5)])
    return {"res": res}


def _child(i: int) -> Any:
    async def run(c: Ctx) -> Any:
        a = await c.tool("add_frame", name=f"P{i}")
        b = await c.tool("read_model")
        return [a, b]

    return run


async def slow_block(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:
    """A write that takes long, for the external-kill scenario."""
    await ctx.tool("add_frame", name="A")
    await ctx.tool("slow_write", name="B", ms=60000)
    await ctx.tool("add_frame", name="C")
    return {"done": True}


async def overlap_block(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:
    """Breaks the rule: two steps in flight in one scope."""
    await asyncio.gather(ctx.tool("slow_read", ms=20), ctx.tool("slow_read", ms=20))
    return {}


async def nested_inner(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:
    a = await ctx.tool("add_frame", name="N1")
    b = await ctx.tool("add_frame", name="N2")
    return {"a": a, "b": b}


async def nested_block(ctx: Ctx, inp: dict[str, Any]) -> dict[str, Any]:
    first = await ctx.block(nested_inner, {"k": 1})
    last = await ctx.tool("add_frame", name="N3")
    return {"first": first, "last": last}


BLOCKS = {
    "footing": footing,
    "v_args": v_args,
    "v_tool": v_tool,
    "v_insert": v_insert,
    "v_remove": v_remove,
    "v_arity": v_arity,
    "v_preview": v_preview,
    "v_short": v_short,
    "v_tail": v_tail,
    "par_block": par_block,
    "slow_block": slow_block,
    "overlap_block": overlap_block,
    "nested_block": nested_block,
}
FOOTING_INPUT = {"limit_ref": "limits.drift_ratio"}
