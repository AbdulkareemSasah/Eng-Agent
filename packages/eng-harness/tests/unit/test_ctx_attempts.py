"""`ctx.attempts`: limit rules, iteration scopes and the escalation on exhaustion (plan 0001 T10; spec 0001 AC9)."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ErrorCode
from fakes.ports import failure
from workflows.ctx_flows import flow
from workflows.rig import make_rig, request

from eng_harness.ctx import BasisCount
from eng_harness.engine import EngineSettings, RunStatus
from eng_harness.errors import ToolFailed
from eng_harness.journal import EventType

T = EventType


@pytest.mark.parametrize(
    ("limit", "cap"),
    [(3, 10), (BasisCount(11), 10), (BasisCount(3), 2), (BasisCount(0), 10)],
    ids=["a literal", "above the default cap", "above the set cap", "zero"],
)
def test_attempts_rules(tmp_path: Path, limit: Any, cap: int) -> None:
    rig = make_rig(tmp_path)

    async def body(ctx: Any) -> list[str]:
        async for _ in ctx.attempts(limit):
            await ctx.tool("read_a", {"n": 0})
        return []

    stopped = asyncio.run(rig.engine(flow(body), settings=EngineSettings(max_attempts_cap=cap)).start(request()))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "block_rule_violation"
    assert rig.host.ledger == []  # refused before the first iteration
    assert rig.types(stopped.run_id) == [T.RUN_STARTED, T.RUN_ESCALATED]


def test_attempts_exhausted_escalate(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.outcomes["read_c"].extend([failure(ErrorCode.NOT_FOUND, "no")] * 3)
    last: list[bool] = []

    async def body(ctx: Any) -> list[str]:
        async for attempt in ctx.attempts(BasisCount(3)):
            last.append(attempt.is_last)
            try:
                await ctx.tool("read_c", {"n": attempt.index})
            except ToolFailed:
                continue
            break
        return []

    workflow = flow(body)
    stopped = asyncio.run(rig.engine(workflow).start(request()))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "attempts_exhausted"
    assert last == [False, False, True]
    events = rig.events(stopped.run_id)
    assert [e.path for e in events if e.type is T.STEP_STARTED] == ["0/0/0", "0/1/0", "0/2/0"]  # scope p/i
    assert events[-1].type is T.RUN_ESCALATED
    ledger = len(rig.host.ledger)
    again = asyncio.run(rig.engine(workflow).resume(stopped.run_id))  # the recorded failures are replayed
    assert again.escalation is not None
    assert (again.status, again.escalation.reason) == (RunStatus.NEEDS_ENGINEER, "attempts_exhausted")
    assert len(rig.host.ledger) == ledger


def test_break_ends_the_loop_and_the_scope(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.outcomes["read_c"].append(failure(ErrorCode.NOT_FOUND, "no"))

    async def body(ctx: Any) -> list[str]:
        refs: list[str] = []
        async for attempt in ctx.attempts(BasisCount(3)):
            try:
                result = await ctx.tool("read_c", {"n": attempt.index})
            except ToolFailed:
                continue
            refs.append(result.ref.ref)
            break
        after = await ctx.tool("read_a", {"n": 7})  # the loop is finished: the scope takes the next index
        return [*refs, after.ref.ref]

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.COMPLETED
    paths = [e.path for e in rig.events(outcome.run_id) if e.type is T.STEP_STARTED]
    assert paths == ["0/0/0", "0/1/0", "1"]
