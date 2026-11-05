"""`ctx.tool`: results, failures, retries and arguments (plan 0001 T10; spec 0001 AC11, 4.3.2, 4.3.3).

Fake ports and a real SQLite journal in a temporary workspace (the rig of `tests/workflows/rig.py`). Failures are queued
on `rig.host.outcomes` directly, so each queued failure is one call of the fake host.
"""

import asyncio
from enum import StrEnum
from pathlib import Path
from typing import Any

from eng_contract.errors import ErrorCode
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref
from fakes.ports import failure
from pydantic import JsonValue
from workflows.ctx_flows import flow, success
from workflows.rig import make_rig, request

from eng_harness.engine import EngineSettings, RunStatus
from eng_harness.engine._steps import op_id
from eng_harness.errors import Pause, ToolFailed
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev

T = EventType


async def _one(ctx: Any, tool: str) -> list[str]:
    result = await ctx.tool(tool, {"n": 0})
    return [result.ref.ref]


def test_tool_result_and_failure(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    load: dict[str, JsonValue] = {"value": 2.5, "unit": "kN"}
    rig.host.outcomes["read_a"].extend(
        [success(rig, {"load": load, "name": "B1"}), failure(ErrorCode.NOT_FOUND, "gone")]
    )
    seen: list[Any] = []
    caught: list[ToolFailed] = []
    gate = {"pause": True}

    async def body(ctx: Any) -> list[str]:
        first = await ctx.tool("read_a", {"n": 0})
        seen.append(first)
        try:
            await ctx.tool("read_a", {"n": 1})
        except ToolFailed as failed:
            caught.append(failed)
        if gate["pause"]:
            raise Pause("awaiting approval", evidence=["apr_1"])
        return [first.ref.ref]

    workflow = flow(body)
    paused = asyncio.run(rig.engine(workflow).start(request()))
    assert paused.status is RunStatus.PAUSED
    gate["pause"] = False
    done = asyncio.run(rig.engine(workflow).resume(paused.run_id))
    assert done.status is RunStatus.COMPLETED
    live, replayed = seen
    assert live == replayed  # a live and a replayed result are equal (AC11)
    assert live.summary["load"] == Quantity(2.5, "kN")
    assert isinstance(replayed.summary["load"], Quantity)
    assert live.summary["name"] == "B1"
    first, second = caught  # a failure envelope raises ToolFailed with the ErrorDetail, live and replayed
    assert second.detail == first.detail
    assert (first.detail.code, first.code) == (ErrorCode.NOT_FOUND, ErrorCode.NOT_FOUND)
    assert first.message == "gone"
    assert [c.tool for c in rig.host.ledger] == ["read_a", "read_a"]  # the resume made no tool call


def test_a_read_is_retried_as_new_attempts(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.outcomes["read_a"].extend([failure(ErrorCode.HOST_BUSY), failure(ErrorCode.TIMEOUT_NO_EFFECT)])
    outcome = asyncio.run(rig.engine(flow(lambda ctx: _one(ctx, "read_a"))).start(request()))
    assert outcome.status is RunStatus.COMPLETED
    run_id = outcome.run_id
    assert [c.op_id for c in rig.host.ledger] == [op_id(run_id, "0", n) for n in (1, 2, 3)]  # a new op_id per attempt
    steps = [(e.type, e.attempt) for e in rig.events(run_id)[1:-1]]
    assert steps == [
        (T.STEP_STARTED, 1), (T.STEP_FAILED, 1), (T.STEP_STARTED, 2), (T.STEP_FAILED, 2),
        (T.STEP_STARTED, 3), (T.STEP_COMPLETED, 3),
    ]  # fmt: skip
    failed = rig.events(run_id)[2].payload
    assert isinstance(failed, ev.StepFailed)
    assert failed.retryable is True


def test_retries_stop_at_the_limit(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.outcomes["read_a"].extend([failure(ErrorCode.HOST_BUSY)] * 3)
    workflow = flow(lambda ctx: _one(ctx, "read_a"))
    stopped = asyncio.run(rig.engine(workflow).start(request()))  # the default limit is two retries: three attempts
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "unhandled_error"
    assert len(rig.host.ledger) == 3
    resumed = asyncio.run(rig.engine(workflow).resume(stopped.run_id))  # the last failure was retryable: attempt 4
    assert resumed.status is RunStatus.COMPLETED
    assert rig.host.ledger[-1].op_id == op_id(stopped.run_id, "0", 4)
    small = make_rig(tmp_path / "small")
    small.host.outcomes["read_a"].extend([failure(ErrorCode.HOST_BUSY)] * 5)
    outcome = asyncio.run(small.engine(workflow, settings=EngineSettings(step_retry_limit=1)).start(request()))
    assert (outcome.status, len(small.host.ledger)) == (RunStatus.NEEDS_ENGINEER, 2)


def test_arguments_are_sent_as_json(tmp_path: Path) -> None:
    class Mode(StrEnum):
        FAST = "fast"

    rig = make_rig(tmp_path)
    ref = Ref.model_validate({"$ref": "res_" + "1" * 26 + "#/value"})
    refs: list[str] = []

    async def body(ctx: Any) -> list[str]:
        first = await ctx.tool("read_a", {"n": 0})
        refs.append(first.ref.ref)
        await ctx.tool("read_c", {"src": first, "ref": ref, "mode": Mode.FAST, "list": [first, None, 2.5], "ok": True})
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.COMPLETED
    pointer = {"$ref": refs[0]}  # a result passed as an argument is sent as its reference
    expected = {"src": pointer, "ref": {"$ref": ref.ref}, "mode": "fast", "list": [pointer, None, 2.5], "ok": True}
    assert rig.host.ledger[1].args == expected


def test_an_argument_that_is_not_json_is_a_rule_violation(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_a", {"n": object()})
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "block_rule_violation"
    assert rig.host.ledger == []
