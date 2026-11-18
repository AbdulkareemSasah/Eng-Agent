"""Replay of decisions over a resume (plan 0005 T10; spec 0005 AC20; process/05 section 1).

A run is stopped after its decision (a read fails), and resumed by a new engine over a new cascade and label store in
the same folders, as a restarted process would; a decision pending at the stop is presented again.
"""

import asyncio
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from fakes.decision_providers import FakeDecisionProvider
from fakes.ports import FakeBasisPort, FakeCalcPort, failure
from pydantic import BaseModel, ConfigDict
from workflows.ctx_flows import flow
from workflows.rig import Rig, make_rig, request

from eng_harness.block import BlockDef, Registry
from eng_harness.decisions import Cascade, LabelStore
from eng_harness.decisions._points import PointRegistry, decision_point
from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings
from eng_harness.decisions.types import Pick, RuleBasis, rule
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunStatus, rule_guard
from eng_harness.engine import _decide as decide_module
from eng_harness.journal import EventType
from eng_harness.ports import InputAnswer

T = EventType


class Action(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


class State(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    failing: bool


ACTION = decision_point(name="pick_action", version=1, title="Pick an action", options=Action, state=State)(object)
RULED: list[str] = []


@rule(id="pick_action.enlarge", version=1, point="pick_action", rationale="Enlarge when the check fails.")
def enlarge(state: State, basis: RuleBasis) -> Pick[Action] | None:
    RULED.append("enlarge")
    return Pick(Action.ENLARGE) if state.failing else None


@pytest.fixture(autouse=True)
def registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(decide_module, "points", lambda: PointRegistry([ACTION]))
    RULED.clear()


@pytest.fixture
def stores() -> Iterator[list[LabelStore]]:
    opened: list[LabelStore] = []
    yield opened
    for store in opened:
        store.close()


def _engine(
    rig: Rig, workflow: BlockDef[Any, Any], stores: list[LabelStore], model: FakeDecisionProvider | None = None
) -> Engine:
    """An engine over a new cascade and label store in the rig's folder: a restarted process."""
    settings, decisions = EngineSettings(), DecisionSettings()
    clock = FixedClock(1_767_225_600_000, 1)
    labels = LabelStore(rig.workspace.root.parent, decisions, clock, SeededIdSource(b"labels", clock))
    stores.append(labels)
    providers: dict[str, Any] = {} if model is None else {"model": model}
    cascade = Cascade(
        PointRegistry([ACTION]), decisions, labels, clock=rig.clock, monotonic=lambda: 0.0, rule_guard=rule_guard,
        max_concurrent_decisions=settings.max_concurrent_decisions, **providers,
    )  # fmt: skip
    ports = EnginePorts(
        tool=rig.host, host=rig.host, calc=FakeCalcPort(rig.run_class, rig.calc_infos),
        basis=FakeBasisPort(rig.bases), approvals=rig.approvals, inputs=rig.inputs, decision=cascade,
    )  # fmt: skip
    return Engine(rig.workspace, Registry([workflow]), ports, rig.store, settings, rig.clock, rig.ids)


def _answer(rig: Rig, option: str) -> None:
    shown = rig.inputs.presented[-1]
    props = cast(dict[str, Any], shown.fields_schema["properties"])
    choices = {name: option for name, prop in props.items() if "enum" in prop}
    answer = InputAnswer(
        request_id=shown.request_id, shown_sha256=shown.fields_schema_sha256, choices=choices, by="engineer:ada"
    )
    rig.inputs.script(shown.request_id, answer)


def _made(rig: Rig, run_id: str) -> list[Any]:
    return [e.payload for e in rig.events(run_id) if e.type is T.DECISION_MADE]


async def _decide_then_read(ctx: Any) -> list[str]:
    decided = await ctx.decide("pick_action", Action, State(failing=True), [enlarge], DecisionPolicy())
    assert decided.choice is Action.ENLARGE
    return [(await ctx.tool("read_c", {"n": 0})).ref.ref]


def test_replay_does_not_requery(tmp_path: Path, stores: list[LabelStore]) -> None:
    """AC20: a recorded decision is returned at the resume without running a rule or asking a provider."""
    rig, provider = make_rig(tmp_path), FakeDecisionProvider()
    rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))  # the run stops after the decision
    workflow = flow(_decide_then_read)
    stopped = asyncio.run(_engine(rig, workflow, stores, provider).start(request()))
    assert stopped.status is not RunStatus.COMPLETED
    assert RULED == ["enlarge"]
    done = asyncio.run(_engine(rig, workflow, stores, provider).resume(stopped.run_id))
    assert done.status is RunStatus.COMPLETED
    assert RULED == ["enlarge"]  # the rule did not run again
    assert provider.requests == []  # and no provider was asked, before or after the resume
    made = _made(rig, stopped.run_id)
    assert [(m.choice, m.decided_by) for m in made] == [("enlarge", "rule:pick_action.enlarge")]  # recorded once


def test_crash_while_pending(tmp_path: Path, stores: list[LabelStore]) -> None:
    """AC20: an engineer decision pending at a crash is presented again, with the same request id, at the resume."""

    async def ask(ctx: Any) -> list[str]:
        await ctx.decide("pick_action", Action, State(failing=False), [enlarge], DecisionPolicy())
        return []

    rig, workflow = make_rig(tmp_path), flow(ask)
    paused = asyncio.run(_engine(rig, workflow, stores).start(request()))
    assert paused.status is RunStatus.PAUSED
    first = rig.inputs.presented[-1]
    again = asyncio.run(_engine(rig, workflow, stores).resume(paused.run_id))  # the process died; nothing was answered
    assert again.status is RunStatus.PAUSED
    assert [r.request_id for r in rig.inputs.presented] == [first.request_id, first.request_id]
    assert again.pending == paused.pending == (first.request_id,)
    assert [e.type for e in rig.events(paused.run_id)].count(T.INPUT_REQUESTED) == 1  # journaled once
    _answer(rig, "rebar")
    done = asyncio.run(_engine(rig, workflow, stores).resume(paused.run_id))
    assert done.status is RunStatus.COMPLETED
    made = _made(rig, paused.run_id)
    assert [(m.choice, m.decided_by, m.request_id) for m in made] == [("rebar", "engineer:ada", first.request_id)]
    assert len(stores[-1].read("pick_action")) == 1  # one label, written at the answer
