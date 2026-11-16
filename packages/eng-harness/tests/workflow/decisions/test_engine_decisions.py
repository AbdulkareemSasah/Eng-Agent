"""The real engine over the real cascade and fake ports (plan 0005 T10; spec 0005 AC16, AC17, AC30, AC43).

The decision point is a test double that `engine._decide.points` is made to return; the cascade is built as the command
line will build it (phase 1: rules and the engineer, no provider), over a label store in the test's temporary folder.
Rules and workflow code keep their I/O outside block code (the runtime guard of engine AC18 refuses it there).
"""

import asyncio
import json
import socket
import sys
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.ids import FixedClock, SeededIdSource
from fakes.ports import FakeBasisPort, FakeCalcPort
from pydantic import BaseModel, ConfigDict, JsonValue
from workflows.ctx_flows import flow
from workflows.rig import Rig, make_rig, request

from eng_harness.block import BlockDef, Registry
from eng_harness.decisions import Cascade, LabelStore
from eng_harness.decisions._points import Label, PointRegistry, decision_point
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
    member: Label = "Column C7"


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
    props = cast(dict[str, Any], shown.fields_schema["properties"])
    choices = {name: option for name, prop in props.items() if "enum" in prop}  # the questions, not the evidence
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


def _props(shown: Any) -> dict[str, Any]:
    return cast(dict[str, Any], shown.fields_schema["properties"])


def _decision_events(rig: Rig, run_id: str) -> list[Any]:
    return [e.payload for e in rig.events(run_id) if e.type is T.DECISION_MADE]


def _bodies(rule_body: Any) -> list[Any]:
    """The decision rule `rule_body` registered as a rule of the point, for a workflow that decides with it."""
    return [rule(id="pick_action.io", version=1, point="pick_action", rationale="Does I/O.")(rule_body)]


def test_rules_run_under_the_guard(tmp_path: Path, stores: list[LabelStore]) -> None:
    """AC16: a rule that opens a file, opens a socket or imports a module is `BlockRuleViolation` under the engine."""
    target = tmp_path / "made_by_rule.txt"

    def opens(state: State, basis: RuleBasis) -> Pick[Action] | None:
        target.write_text("x")
        return None

    def connects(state: State, basis: RuleBasis) -> Pick[Action] | None:
        socket.socket().close()
        return None

    def imports(state: State, basis: RuleBasis) -> Pick[Action] | None:
        __import__("colorsys")
        return None

    for n, body in enumerate((opens, connects, imports)):
        sys.modules.pop("colorsys", None)  # an import of a loaded module raises no audit event
        rules = _bodies(body)

        async def decide(ctx: Any, rules: list[Any] = rules) -> list[str]:
            await ctx.decide("pick_action", Action, State(failing=True), rules, DecisionPolicy())
            return []

        rig = make_rig(tmp_path / f"r{n}")
        engine, _ = _engine(rig, flow(decide), stores)
        stopped = asyncio.run(engine.start(request()))
        assert stopped.status is RunStatus.NEEDS_ENGINEER
        assert stopped.escalation is not None
        assert stopped.escalation.reason == "block_rule_violation"
        assert _decision_events(rig, stopped.run_id) == []
    assert not target.exists()  # the open did not happen


def test_engineer_decision_pauses_and_resumes(tmp_path: Path, stores: list[LabelStore]) -> None:
    """AC17: with no rule match and no provider, the run pauses on an `engine.decision` request, then answers."""
    rig = make_rig(tmp_path)
    engine, _ = _engine(rig, flow(_ask_engineer), stores)
    paused = asyncio.run(engine.start(request()))
    assert paused.status is RunStatus.PAUSED
    shown = rig.inputs.presented[-1]
    assert (shown.kind, paused.pending) == ("engine.decision", (shown.request_id,))
    options = [p["enum"] for p in _props(shown).values() if "enum" in p]
    assert options == [["enlarge", "rebar"]]
    assert _decision_events(rig, paused.run_id) == []
    _answer(rig, "rebar")
    done = asyncio.run(engine.resume(paused.run_id))
    assert done.status is RunStatus.COMPLETED
    (made,) = _decision_events(rig, paused.run_id)
    assert (made.choice, made.decided_by, made.request_id) == ("rebar", "engineer:ada", shown.request_id)
    assert made.suggestions == []  # no provider was asked, so there are no suggestions
    assert [e.type for e in rig.events(paused.run_id)].count(T.INPUT_REQUESTED) == 1
    labels = stores[0].read("pick_action")
    assert [(x.label, x.engineer, x.source) for x in labels] == [("rebar", "ada", "engineer_decision")]


def test_decision_made_record(tmp_path: Path, stores: list[LabelStore]) -> None:
    """AC30: the `decision_made` payload is complete for a rule and for an engineer decision, with no state value."""
    state = State(failing=True)

    async def both(ctx: Any) -> list[str]:
        await ctx.decide("pick_action", Action, state, [enlarge], DecisionPolicy())
        await ctx.decide("pick_action", Action, State(failing=False), [enlarge], DecisionPolicy())
        return []

    rig = make_rig(tmp_path)
    engine, _ = _engine(rig, flow(both), stores)
    paused = asyncio.run(engine.start(request()))
    _answer(rig, "rebar")
    assert asyncio.run(engine.resume(paused.run_id)).status is RunStatus.COMPLETED
    by_rule, by_engineer = _decision_events(rig, paused.run_id)
    assert (by_rule.point, by_rule.options, by_rule.choice) == ("pick_action", ["enlarge", "rebar"], "enlarge")
    assert (by_rule.decided_by, by_rule.confidence) == ("rule:pick_action.enlarge", None)
    assert by_rule.state_sha256 == payload_sha256(state.model_dump(mode="json"))
    assert by_rule.request_id is None  # only the engineer's tier has a request
    assert by_rule.latency_ms >= 0
    assert [(s["tier"], s["by"], s["outcome"]) for s in by_rule.suggestions] == [
        (1, "rule:pick_action.enlarge", "accepted")
    ]
    assert (by_engineer.decided_by, by_engineer.options) == ("engineer:ada", ["enlarge", "rebar"])
    assert by_engineer.state_sha256 == payload_sha256(State(failing=False).model_dump(mode="json"))
    assert by_engineer.request_id is not None
    for made in (by_rule, by_engineer):
        assert "Column C7" not in json.dumps(made.model_dump(mode="json"))  # no state value is journaled
