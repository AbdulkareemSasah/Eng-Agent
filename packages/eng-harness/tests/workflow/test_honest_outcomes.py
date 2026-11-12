"""Invariant 6: honest outcomes on the host (plan 0001 T13; spec 0001 4.5.3, 4.6 #6, AC33, AC42).

A write whose call raises, returns `TIMEOUT_UNKNOWN_OUTCOME` or returns `HOST_WEDGED` is in flight at once: it is
reconciled (spec 4.5.3) before any further step on its host, while steps on other hosts go on. `_Host` is the rig's
fake host with one scripted reconciliation for every operation and a reconciler that can be held on a gate, which
records how many tool calls had reached the host when it started and when it ended.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import pytest
from eng_contract.errors import ErrorCode
from fakes.ports import ENVELOPE, Raise, failure
from pydantic import JsonValue
from workflows.chain import ChainOutput
from workflows.ctx_flows import flow, success
from workflows.rig import Host, Rig, make_rig, request

from eng_harness.engine import RunStatus
from eng_harness.engine._steps import op_id
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import Reconciliation, ToolInfo

T = EventType
_CAUSES: dict[str, ENVELOPE | Raise] = {
    "timeout": failure(ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, "the reply was lost"),
    "wedged": failure(ErrorCode.HOST_WEDGED, "the host stopped answering"),
    "raised": Raise(ConnectionResetError("the connection dropped")),
}


class _Host(Host):
    """The rig's host; `reconcile` answers `found` for any operation, after `gate` is set when there is one."""

    def __init__(self, rig: Rig) -> None:
        super().__init__(rig.ids, rig.clock, rig.workspace.root / "runs")
        self.found = Reconciliation(outcome="not_applied")
        self.gate: asyncio.Event | None = None
        self.seen: list[tuple[str, int]] = []  # ("start" or "end", number of tool calls that had reached the host)
        self.ops: list[str] = []

    async def reconcile(self, tool: str, args: Mapping[str, JsonValue], op_id: str) -> Reconciliation:
        self.ops.append(op_id)
        self.seen.append(("start", len(self.ledger)))
        if self.gate is not None:
            await self.gate.wait()
        self.seen.append(("end", len(self.ledger)))
        return self.found


def _rig(root: Path) -> tuple[Rig, _Host]:
    rig = make_rig(root)
    host = _Host(rig)
    host._tools["read_other"] = ToolInfo(name="read_other", effect="read", action="plain", host_key="other")
    return replace(rig, host=host), host


async def _write_then_read(ctx: Any) -> list[str]:
    wrote = await ctx.tool("write_b", {"n": 0, "model": "m1"})
    return [wrote.ref.ref, (await ctx.tool("read_c", {"n": 1})).ref.ref]


def _closings(rig: Rig, run_id: str) -> list[tuple[EventType, int | None]]:
    """(type, attempt) of the events that close step `0`."""
    kinds = (T.STEP_COMPLETED, T.STEP_FAILED, T.STEP_RECONCILED)
    return [(e.type, e.attempt) for e in rig.events(run_id) if e.path == "0" and e.type in kinds]


@pytest.mark.parametrize("cause", sorted(_CAUSES))
@pytest.mark.parametrize("found", ["not_applied", "applied"])
def test_unknown_outcome_reconciled_first(tmp_path: Path, cause: str, found: Literal["applied", "not_applied"]) -> None:
    """The write is reconciled before the next step on its host; it runs again only when it was not applied (AC33)."""
    rig, host = _rig(tmp_path)
    host.outcomes["write_b"].append(_CAUSES[cause])
    result = success(rig, {"applied": True})
    host.found = Reconciliation(outcome=found, result=result if found == "applied" else None)
    outcome = asyncio.run(rig.engine(flow(_write_then_read, name="honest")).start(request(workflow="honest")))
    assert outcome.status is RunStatus.COMPLETED, outcome.escalation
    run_id = outcome.run_id
    assert host.ops == [op_id(run_id, "0", 1)]
    assert host.seen == [("start", 1), ("end", 1)]  # nothing reached the host between the write and its reconciliation
    (reconciled,) = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.StepReconciled)]
    assert (reconciled.op_id, reconciled.outcome, reconciled.decided_by) == (op_id(run_id, "0", 1), found, "adapter")
    if found == "applied":  # the write is not sent again: the block gets the reconciled result
        assert [(c.tool, c.op_id) for c in host.ledger] == [
            ("write_b", op_id(run_id, "0", 1)), ("read_c", op_id(run_id, "1", 1)),
        ]  # fmt: skip
        assert _closings(rig, run_id) == [(T.STEP_RECONCILED, 1)]
        assert isinstance(outcome.output, ChainOutput)
        assert outcome.output.refs[0] == result.result_id
        return
    assert [(c.tool, c.op_id) for c in host.ledger] == [
        ("write_b", op_id(run_id, "0", 1)), ("write_b", op_id(run_id, "0", 2)), ("read_c", op_id(run_id, "1", 1)),
    ]  # fmt: skip
    assert _closings(rig, run_id) == [(T.STEP_RECONCILED, 1), (T.STEP_COMPLETED, 2)]  # a new attempt, a new op_id


@pytest.mark.parametrize("cause", sorted(_CAUSES))
def test_unresolved_outcome_stops_the_run(tmp_path: Path, cause: str) -> None:
    """A reconciliation that cannot decide asks the engineer, and no further step reaches the host (AC33, 4.5.3)."""
    rig, host = _rig(tmp_path)
    host.outcomes["write_b"].append(_CAUSES[cause])
    host.found = Reconciliation(outcome="unknown")
    outcome = asyncio.run(rig.engine(flow(_write_then_read, name="honest")).start(request(workflow="honest")))
    assert outcome.status is RunStatus.NEEDS_ENGINEER
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "needs_reconciliation"
    assert [r.kind for r in rig.inputs.presented] == ["engine.in_flight"]
    assert outcome.escalation.request_id == rig.inputs.presented[0].request_id
    assert [c.tool for c in host.ledger] == ["write_b"]
    assert _closings(rig, outcome.run_id) == []  # still in flight: the next resume reconciles it
    assert [e.type for e in rig.events(outcome.run_id)][-2:] == [T.INPUT_REQUESTED, T.RUN_ESCALATED]


def test_reconcile_before_next_step_on_host(tmp_path: Path) -> None:
    """While a write on one host is reconciled, a step on another host runs and one on the same host waits (AC42)."""
    rig, host = _rig(tmp_path)
    host.outcomes["write_b"].append(failure(ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, "the reply was lost"))

    async def body(ctx: Any) -> list[str]:
        host.gate = asyncio.Event()

        async def write() -> str:
            return str((await ctx.tool("write_b", {"n": 0, "model": "m1"})).ref.ref)

        async def reads() -> str:
            other = await ctx.tool("read_other", {"n": 1})  # the other host goes on while csi is reconciled
            assert host.gate is not None
            host.gate.set()
            await ctx.tool("read_c", {"n": 2})  # csi: waits until the reconciliation has run
            return str(other.ref.ref)

        return list(await ctx.parallel(write(), reads()))

    outcome = asyncio.run(rig.engine(flow(body, name="dual")).start(request(workflow="dual")))
    assert outcome.status is RunStatus.COMPLETED, outcome.escalation
    assert host.seen == [("start", 1), ("end", 2)]  # read_other reached its host during the reconciliation
    tools = [c.tool for c in host.ledger]
    assert tools[:2] == ["write_b", "read_other"]
    assert sorted(tools[2:]) == ["read_c", "write_b"]  # both csi steps came after the reconciliation ended
