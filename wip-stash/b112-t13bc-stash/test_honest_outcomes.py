"""Invariant 6: honest outcomes on the host (plan 0001 T13; spec 0001 AC33, AC42).

A write whose outcome is unknown is reconciled before any further step on that host; other hosts may continue.
"""

import asyncio
from pathlib import Path
from typing import Any

from eng_contract.errors import ErrorCode
from fakes.ports import failure
from workflows.ctx_flows import flow, success
from workflows.rig import make_rig, request

from eng_harness.engine import RunStatus
from eng_harness.engine._steps import op_id
from eng_harness.ports import HostInstance, Reconciliation, ToolInfo


CSI = HostInstance(instance_id="csi-1", pid=42, process_started_at="2026-01-01T00:00:00.000Z", program="csi")
OTHER = HostInstance(instance_id="other-1", pid=43, process_started_at="2026-01-01T00:00:00.000Z", program="other")


def test_unknown_outcome_reconciled_first(tmp_path: Path) -> None:
    """A wedged write is reconciled before the next tool on that host (AC33)."""
    rig = make_rig(tmp_path)
    rig.host.add_model("m1", CSI)
    rig.host.script("write_b", failure(ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, "lost"))

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("write_b", {"n": 0, "model": "m1"})
        return [(await ctx.tool("read_c", {"n": 1})).ref.ref]

    workflow = flow(body, name="honest")
    stopped = asyncio.run(rig.engine(workflow).start(request(workflow="honest")))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    run_id, op = stopped.run_id, op_id(stopped.run_id, "0", 1)
    rig.host.reconciliations[op] = Reconciliation(outcome="applied", result=success(rig, {"ok": True}))
    done = asyncio.run(rig.engine(workflow).resume(run_id))
    assert done.status is RunStatus.COMPLETED
    log = rig.log
    got = log.index("tool.reconcile")
    nxt = log.index("tool.call", got)
    assert log[nxt:].count("tool.call") >= 1
    assert rig.host.ledger[-1].tool == "read_c"


def test_reconcile_before_next_step_on_host(tmp_path: Path) -> None:
    """While one host is wedged, a step on another host still runs (AC42)."""
    rig = make_rig(tmp_path)
    rig.host._tools["read_other"] = ToolInfo(name="read_other", effect="read", action="plain", host_key="other")
    rig.host.add_model("m1", CSI)
    rig.host.instances["other"].append(OTHER)
    rig.host.script("write_b", failure(ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, "lost"))
    rig.host.script("read_other", success(rig, {"ok": True}))

    async def body(ctx: Any) -> list[str]:
        async def write() -> None:
            await ctx.tool("write_b", {"n": 0, "model": "m1"})

        async def read() -> str:
            return (await ctx.tool("read_other", {"n": 1})).ref.ref

        refs = await ctx.parallel(write(), read())
        return [refs[1]]

    workflow = flow(body, name="dual")
    stopped = asyncio.run(rig.engine(workflow).start(request(workflow="dual")))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert any(entry.tool == "read_other" for entry in rig.host.ledger)
    assert any("reconcile" in line for line in rig.log)
