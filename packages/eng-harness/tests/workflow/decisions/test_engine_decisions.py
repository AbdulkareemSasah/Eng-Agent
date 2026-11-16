"""The real engine over the real cascade and fake ports (plan 0005 T10; spec 0005 AC16, AC17, AC30, AC43).

The decision point is a test double that `engine._decide.points` is made to return; the cascade is built as the command
line will build it (phase 1: rules and the engineer, no provider), over a label store in the test's temporary folder.
Rules and workflow code keep their I/O outside block code (the runtime guard of engine AC18 refuses it there).
"""

import asyncio
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
from eng_contract.ids import FixedClock, SeededIdSource
from fakes.ports import FakeBasisPort, FakeCalcPort
from pydantic import BaseModel, ConfigDict, JsonValue
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
from eng_harness.journal import _events as ev
from eng_harness.ports import InputAnswer

T = EventType


class Action(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


class State(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    failing: bool


ACTION = decision_point(name="pick_action", version=1, title="Pick an action", options=Action, state=State)(object)


@rule(id="pick_action.enlarge", version=1, point="pick_action", rationale="Enlarge when the check fails.")
def enlarge(state: State, basis: RuleBasis) -> Pick[Action] | None:
    return Pick(Action.ENLARGE) if state.failing else None


@pytest.fixture(autouse=True)
def registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(decide_module, "points", lambda: PointRegistry([ACTION]))


@pytest.fixture
def stores() -> Iterator[list[LabelStore]]:
    opened: list[LabelStore] = []
    yield opened
    for store in opened:
        store.close()


def _engine(
    rig: Rig, workflow: BlockDef[Any, Any], stores: list[LabelStore], runtime: dict[str, JsonValue] | None = None
) -> tuple[Engine, Cascade]:
    settings, decisions = EngineSettings(), DecisionSettings()
    clock = FixedClock(1_767_225_600_000, 1)
    labels = LabelStore(rig.workspace.root.parent, decisions, clock, SeededIdSource(b"labels", clock))
    stores.append(labels)
    cascade = Cascade(
        PointRegistry([ACTION]), decisions, labels, clock=rig.clock, monotonic=lambda: 0.0, rule_guard=rule_guard,
        max_concurrent_decisions=settings.max_concurrent_decisions, runtime=runtime,
    )  # fmt: skip
    ports = EnginePorts(
        tool=rig.host, host=rig.host, calc=FakeCalcPort(rig.run_class, rig.calc_infos),
        basis=FakeBasisPort(rig.bases), approvals=rig.approvals, inputs=rig.inputs, decision=cascade,
    )  # fmt: skip
    return Engine(rig.workspace, Registry([workflow]), ports, rig.store, settings, rig.clock, rig.ids), cascade


async def _ask_engineer(ctx: Any) -> list[str]:
    await ctx.decide("pick_action", Action, State(failing=False), [enlarge], DecisionPolicy())
    return []


def _answer(rig: Rig, option: str) -> None:
    """The engineer's answer: `option` for each question of the request presented last."""
    shown = rig.inputs.presented[-1]
    choices = dict.fromkeys(shown.fields_schema["properties"], option)
    answer = InputAnswer(
        request_id=shown.request_id, shown_sha256=shown.fields_schema_sha256, choices=choices, by="engineer:ada"
    )
    rig.inputs.script(shown.request_id, answer)


def test_runtime_summary_in_run_header(tmp_path: Path, stores: list[LabelStore]) -> None:
    """AC43: the cascade's summary is `run_started.decision_runtime`; a resume with the same one records no change."""
    summary: dict[str, JsonValue] = {"providers": {"local": {"tier": "advisory"}}, "points": {"pick_action": 1}}
    rig = make_rig(tmp_path)
    engine, cascade = _engine(rig, flow(_ask_engineer), stores, summary)
    paused = asyncio.run(engine.start(request()))
    assert paused.status is RunStatus.PAUSED
    assert rig.header(paused.run_id).decision_runtime == summary
    _answer(rig, "rebar")
    assert asyncio.run(engine.resume(paused.run_id)).status is RunStatus.COMPLETED
    resumes = [e.payload for e in rig.events(paused.run_id) if isinstance(e.payload, ev.RunResumed)]
    assert [r.decision_runtime for r in resumes] == [None]  # the same object as the header's: nothing recorded
    assert cascade.runtime_summary() == summary
    bare = make_rig(tmp_path / "bare")  # built without a summary (phase 1, tests): the record is empty
    engine, cascade = _engine(bare, flow(_ask_engineer), stores)
    started = asyncio.run(engine.start(request()))
    assert bare.header(started.run_id).decision_runtime == {}
    assert cascade.runtime_summary() == {}
