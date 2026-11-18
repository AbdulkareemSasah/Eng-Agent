"""`ctx.block`: a child block as a scope of its own (plan 0001 T10; spec 0001 AC15)."""

import asyncio
from pathlib import Path
from typing import Any, cast

from eng_contract.canonical import payload_sha256
from workflows.chain import ChainInput, ChainOutput, Impostor
from workflows.ctx_flows import ChildInput, ChildOutput, answer, child, flow, need_approval
from workflows.rig import make_rig, request

from eng_harness.block import block
from eng_harness.engine import RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev

T = EventType


async def _two_reads(ctx: Any) -> list[str]:
    first = await ctx.tool("read_a", {"n": 0})
    second = await ctx.tool("read_c", {"n": 1})
    return [first.ref.ref, second.ref.ref]


def test_child_block(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    inner = child(_two_reads)

    async def body(ctx: Any) -> list[str]:
        out = await ctx.block(inner, ChildInput(n=2))
        last = await ctx.tool("read_a", {"n": 9})
        return [*out.refs, last.ref.ref]

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.COMPLETED
    events = rig.events(outcome.run_id)
    assert [(e.type, e.path) for e in events[1:-1]] == [
        (T.STEP_STARTED, "0"), (T.STEP_STARTED, "0/0"), (T.STEP_COMPLETED, "0/0"),
        (T.STEP_STARTED, "0/1"), (T.STEP_COMPLETED, "0/1"), (T.STEP_COMPLETED, "0"),
        (T.STEP_STARTED, "1"), (T.STEP_COMPLETED, "1"),
    ]  # fmt: skip
    started = events[1].payload
    assert isinstance(started, ev.StepStarted)
    assert (started.kind, started.name, started.effect, started.args) == ("block", "child", "none", {"n": 2})
    assert started.args_sha256 == payload_sha256({"n": 2})
    assert started.child == ev.BlockRef(name="child", version="1", code_sha256=inner.code_sha256)
    done = events[6].payload
    assert isinstance(done, ev.StepCompleted)
    assert done.output_ref is not None
    assert isinstance(outcome.output, ChainOutput)
    assert rig.store.payload(done.output_ref) == {"value": {"refs": outcome.output.refs[:2]}}
    assert [c.tool for c in rig.host.ledger] == ["read_a", "read_c", "read_a"]


def test_input_and_output_are_checked_against_the_models(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)

    inner = child(_two_reads)  # built outside block code: it reads its own source

    async def wrong_input(ctx: Any) -> list[str]:
        await ctx.block(inner, ChainInput())  # not a ChildInput
        return []

    refused = asyncio.run(rig.engine(flow(wrong_input)).start(request()))
    assert refused.escalation is not None
    assert refused.escalation.reason == "block_rule_violation"
    assert "ChildInput" in refused.escalation.detail
    assert rig.types(refused.run_id) == [T.RUN_STARTED, T.RUN_ESCALATED]  # nothing started

    @block(name="impostor", version=1)
    async def impostor(ctx: Any, inp: ChildInput) -> ChildOutput:
        return cast(ChildOutput, Impostor())  # a wrong return value is the case under test

    async def wrong_output(ctx: Any) -> list[str]:
        await ctx.block(impostor, ChildInput())
        return []

    bad = asyncio.run(rig.engine(flow(wrong_output)).start(request()))
    assert bad.escalation is not None
    assert (bad.escalation.reason, "ChildOutput" in bad.escalation.detail) == ("block_rule_violation", True)
    assert T.STEP_COMPLETED not in rig.types(bad.run_id)  # the output of the step was not stored


def test_a_resume_re_enters_a_block_that_was_paused_inside(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)

    async def inside(ctx: Any) -> list[str]:
        first = await ctx.tool("read_a", {"n": 0})
        await need_approval(rig.approvals, "apr_1")
        second = await ctx.tool("read_c", {"n": 1})
        return [first.ref.ref, second.ref.ref]

    inner = child(inside)

    async def body(ctx: Any) -> list[str]:
        out = await ctx.block(inner, ChildInput())
        await ctx.tool("read_a", {"n": 2})
        return list(out.refs)

    workflow = flow(body)
    paused = asyncio.run(rig.engine(workflow).start(request()))
    assert paused.status is RunStatus.PAUSED
    assert paused.pending == ("apr_1",)
    rig.approvals.script("apr_1", answer("apr_1"))
    mark, ledger = len(rig.log), len(rig.host.ledger)
    done = asyncio.run(rig.engine(workflow).resume(paused.run_id))
    assert done.status is RunStatus.COMPLETED
    assert [c.tool for c in rig.host.ledger[ledger:]] == ["read_c", "read_a"]  # the first step was not called again
    assert rig.log[mark:].count("tool.call") == 2
    types = [(e.type, e.path) for e in rig.events(paused.run_id) if e.path in ("0", "0/0")]
    assert types == [
        (T.STEP_STARTED, "0"),
        (T.STEP_STARTED, "0/0"),
        (T.STEP_COMPLETED, "0/0"),
        (T.STEP_COMPLETED, "0"),
    ]  # the block step is started once and completed once


def test_a_completed_block_is_replayed_without_a_second_record(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    inner = child(_two_reads)

    async def body(ctx: Any) -> list[str]:
        out = await ctx.block(inner, ChildInput(n=1))
        await need_approval(rig.approvals, "apr_2")
        return list(out.refs)

    workflow = flow(body)
    paused = asyncio.run(rig.engine(workflow).start(request()))
    before = rig.types(paused.run_id).count(T.STEP_COMPLETED)
    rig.approvals.script("apr_2", answer("apr_2"))
    mark = len(rig.log)
    done = asyncio.run(rig.engine(workflow).resume(paused.run_id))
    assert done.status is RunStatus.COMPLETED
    assert rig.log[mark:] == ["tool.unreleased_tools", "host.preflight"]  # no tool call: the block's steps replayed
    assert rig.types(paused.run_id).count(T.STEP_COMPLETED) == before == 3  # 0/0, 0/1 and 0
    recorded = [
        e.payload.result.ref
        for e in rig.events(paused.run_id)
        if isinstance(e.payload, ev.StepCompleted) and e.payload.result and e.path in ("0/0", "0/1")
    ]
    assert isinstance(done.output, ChainOutput)
    assert done.output.refs == recorded
