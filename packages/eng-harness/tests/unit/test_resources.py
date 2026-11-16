"""Resource limits of the engine: parallel children, hosts, decisions and one host at a time (plan 0001 T18; AC59).

A probe host counts the calls that are active at once, in total and on each host key; each call yields to the event
loop a few times, so calls that the engine lets run together do overlap. The block code only builds the steps.
"""

import asyncio
from collections import Counter
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
from fakes.ports import ENVELOPE, FakeBasisPort, FakeCalcPort, FakeDecisionPort, FakeHost
from pydantic import BaseModel, ConfigDict, JsonValue
from workflows.ctx_flows import flow
from workflows.rig import make_rig, request

from eng_harness.block import Registry
from eng_harness.decisions._points import PointRegistry, decision_point
from eng_harness.decisions._policy import DecisionPolicy
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunStatus
from eng_harness.engine import _decide as decide_module
from eng_harness.ports import DecisionAnswer, DecisionCall, ToolInfo

YIELDS = 3


class Action(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


class State(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    failing: bool


ACTION = decision_point(name="pick_action", version=1, title="Pick an action", options=Action, state=State)(object)


class Probe(FakeHost):
    """A fake host that records how many of its calls are active at once."""

    def __init__(self, keys: Sequence[str], rig: Any) -> None:
        tools = [ToolInfo(name=f"r{n}", effect="read", action="plain", host_key=key) for n, key in enumerate(keys)]
        super().__init__(tools, rig.ids, rig.clock)
        self.active: Counter[str] = Counter()
        self.peak_total, self.peak_host = 0, Counter[str]()

    async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> ENVELOPE:
        key = (await self.describe(tool)).host_key
        self.active[key] += 1
        self.peak_total = max(self.peak_total, sum(self.active.values()))
        self.peak_host[key] = max(self.peak_host[key], self.active[key])
        try:
            for _ in range(YIELDS):
                await asyncio.sleep(0)
            return await super().call(tool, args, op_id=op_id, model=model)
        finally:
            self.active[key] -= 1


class SlowDecisions(FakeDecisionPort):
    """A decision port that records how many `decide` calls are active at once."""

    def __init__(self) -> None:
        super().__init__()
        self.active = self.peak = 0

    async def decide(self, call: DecisionCall) -> DecisionAnswer | Any:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            for _ in range(YIELDS):
                await asyncio.sleep(0)
            return await super().decide(call)
        finally:
            self.active -= 1


def _run(tmp_path: Path, keys: Sequence[str], settings: EngineSettings, port: FakeDecisionPort | None = None) -> Probe:
    """Run a workflow that starts one tool step per key (or one decision per key) in `ctx.parallel`."""
    rig = make_rig(tmp_path)
    host = Probe(keys, rig)

    async def body(ctx: Any) -> list[str]:
        if port is not None:
            ask = (ctx.decide("pick_action", Action, State(failing=True), [], DecisionPolicy()) for _ in keys)
            return [str(d.choice) for d in await ctx.parallel(*ask)]
        return [r.ref.ref for r in await ctx.parallel(*(ctx.tool(f"r{n}") for n in range(len(keys))))]

    ports = EnginePorts(
        tool=host, host=host, calc=FakeCalcPort(rig.run_class, rig.calc_infos), basis=FakeBasisPort(rig.bases),
        approvals=rig.approvals, inputs=rig.inputs, decision=port,
    )  # fmt: skip
    engine = Engine(rig.workspace, Registry([flow(body)]), ports, rig.store, settings, rig.clock, rig.ids)
    assert asyncio.run(engine.start(request())).status is RunStatus.COMPLETED
    return host


def test_limits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC59: no more children, hosts or decisions than the settings allow, and one call at a time on a host."""
    monkeypatch.setattr(decide_module, "points", lambda: PointRegistry([ACTION]))
    distinct = [f"h{n}" for n in range(6)]
    wide = EngineSettings(max_parallel_children=8, max_concurrent_hosts=8, max_concurrent_decisions=8)
    assert _run(tmp_path / "free", distinct, wide).peak_total == 6  # the probe does see overlap when it is allowed
    children = _run(tmp_path / "children", distinct, wide.model_copy(update={"max_parallel_children": 2}))
    assert children.peak_total == 2
    hosts = _run(tmp_path / "hosts", distinct, wide.model_copy(update={"max_concurrent_hosts": 3}))
    assert hosts.peak_total == 3
    one = _run(tmp_path / "one", ["csi"] * 4, wide)  # four steps on one host: serialized in the engine (11 section 8)
    assert (one.peak_host["csi"], len(one.ledger)) == (1, 4)
    slow = SlowDecisions()
    _run(tmp_path / "decisions", distinct[:4], wide.model_copy(update={"max_concurrent_decisions": 2}), slow)
    assert (slow.peak, len(slow.calls)) == (2, 4)
    free = SlowDecisions()
    _run(tmp_path / "decisions-free", distinct[:4], wide, free)
    assert free.peak == 4
