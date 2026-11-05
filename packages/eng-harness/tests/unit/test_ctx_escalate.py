"""`ctx.escalate` and `ctx.parallel` (plan 0001 T10; spec 0001 AC14, AC5)."""

import asyncio
from pathlib import Path
from typing import Any

from workflows.chain import ChainOutput
from workflows.ctx_flows import flow
from workflows.rig import make_rig, request

from eng_harness.engine import RunStatus
from eng_harness.journal import EventType, JournalReader
from eng_harness.journal import _events as ev

T = EventType


def test_escalate(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    refs: list[str] = []

    async def body(ctx: Any) -> list[str]:
        first = await ctx.tool("read_a", {"n": 0})
        refs.append(first.ref.ref)
        await ctx.escalate("the section is not covered", [first.ref])
        raise AssertionError("escalate does not return")  # pragma: no cover

    workflow = flow(body)
    stopped = asyncio.run(rig.engine(workflow).start(request()))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.output is None
    assert stopped.escalation is not None
    assert (stopped.escalation.reason, stopped.escalation.detail) == ("block_escalation", "the section is not covered")
    assert stopped.escalation.evidence == refs
    last = rig.events(stopped.run_id)[-1]
    assert last.type is T.RUN_ESCALATED
    assert last.payload == stopped.escalation
    reader = JournalReader(rig.run_dir(stopped.run_id))
    assert reader.run().status == "NEEDS_ENGINEER"
    reader.close()
    # not terminal: a resume replays the recorded step and escalates again, with no call of any port
    mark, ledger = len(rig.log), len(rig.host.ledger)
    again = asyncio.run(rig.engine(workflow).resume(stopped.run_id))
    assert (again.status, again.escalation) == (RunStatus.NEEDS_ENGINEER, stopped.escalation)
    assert rig.log[mark:] == ["tool.unreleased_tools"]
    assert len(rig.host.ledger) == ledger
    assert [e.type for e in rig.events(stopped.run_id)[-2:]] == [T.RUN_RESUMED, T.RUN_ESCALATED]


def test_parallel_children_run_in_their_own_scopes(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)

    async def child(ctx: Any, n: int) -> str:
        result = await ctx.tool("read_a", {"n": n})
        return str(result.ref.ref)

    async def body(ctx: Any) -> list[str]:
        return list(await ctx.parallel(child(ctx, 0), child(ctx, 1), child(ctx, 2)))

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.COMPLETED
    events = rig.events(outcome.run_id)
    assert sorted(e.path or "" for e in events if e.type is T.STEP_STARTED) == ["0/0/0", "0/1/0", "0/2/0"]
    done = {
        e.path: e.payload.result.ref for e in events if isinstance(e.payload, ev.StepCompleted) and e.payload.result
    }
    assert isinstance(outcome.output, ChainOutput)
    assert [done[f"0/{i}/0"] for i in range(3)] == outcome.output.refs  # results come in argument order
