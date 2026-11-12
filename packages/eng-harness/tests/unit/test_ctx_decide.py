"""`ctx.decide` and `ctx.decide_many` over the DecisionPort and the engineer tier (plan 0001 T14; AC40, AC66).

The decision points are test doubles registered through `engine._decide.points`; the port is the fake of
`tests/fakes/ports.py`, whose handler stands for the cascade of spec 0005.
"""

import asyncio
import hashlib
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.envelope import Provenance
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.refs import Ref
from fakes.ports import FakeBasisPort, FakeCalcPort, FakeDecisionPort
from pydantic import BaseModel, ConfigDict
from workflows.ctx_flows import flow
from workflows.rig import Rig, make_rig, request

from eng_harness.block import BlockDef, Registry
from eng_harness.ctx import DecisionRequest
from eng_harness.decisions._points import Label, PointRegistry, Refs, decision_point
from eng_harness.decisions._policy import DecisionPolicy
from eng_harness.decisions._record import ScreenField, ScreenItem
from eng_harness.decisions.interfaces import DecisionAnswer, DecisionCall, DecisionScreen, PendingAnswer, ProviderOption
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunStatus
from eng_harness.engine import _decide as decide_module
from eng_harness.errors import DecisionInvalid
from eng_harness.journal import EventType, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.ports import InputAnswer

T = EventType
SHA = "c" * 64
BATCH = "dec_" + "b" * 32


class Action(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


class State(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    failing: bool


class Members(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    members: tuple[Label, ...]
    result: Ref


ACTION = decision_point(name="pick_action", version=1, title="Pick an action", options=Action, state=State)(object)
MEMBER = decision_point(name="pick_member", version=1, title="Pick a member", options=Refs("members"), state=Members)(
    object
)


@pytest.fixture(autouse=True)
def registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(decide_module, "points", lambda: PointRegistry([ACTION, MEMBER]))


def _engine(rig: Rig, workflow: BlockDef[Any, Any], port: FakeDecisionPort | None) -> Engine:
    ports = EnginePorts(
        tool=rig.host, host=rig.host, calc=FakeCalcPort(rig.run_class, rig.calc_infos),
        basis=FakeBasisPort(rig.bases), approvals=rig.approvals, inputs=rig.inputs, decision=port,
    )  # fmt: skip
    return Engine(rig.workspace, Registry([workflow]), ports, rig.store, EngineSettings(), rig.clock, rig.ids)


def _run(rig: Rig, workflow: BlockDef[Any, Any], port: FakeDecisionPort | None) -> Any:
    return asyncio.run(_engine(rig, workflow, port).start(request()))


def _rid(run_id: str, path: str) -> str:
    return "dec_" + hashlib.sha256(f"{run_id}\n{path}".encode()).hexdigest()[:32]


def _options(call: DecisionCall) -> tuple[str, ...]:
    return tuple(str(m.value) for m in call.options) if isinstance(call.options, type) else call.options


def _pending(call: DecisionCall, *, batch: str | None = None, rejected: Any = None) -> PendingAnswer:
    shown = tuple(ProviderOption(value=v, label=f"Option {v}") for v in _options(call))
    item = ScreenItem(
        request_id=call.request_id,
        title=call.point.title,
        options=shown,
        fields=(ScreenField(label="Failing", value=True),),
    )
    return PendingAnswer(
        request_id=call.request_id, batch_id=batch, screen=DecisionScreen(items=(item,)), rejected=rejected
    )


def _decided(call: DecisionCall, choice: str, by: str) -> DecisionAnswer:
    return DecisionAnswer(choice=choice, decided_by=by, latency_ms=0, options=_options(call), state_sha256=SHA)


def _engineer(call: DecisionCall) -> DecisionAnswer | PendingAnswer:
    if (given := call.engineer_choice) is None:
        return _pending(call)
    return _decided(call, given.choice, "engineer:" + given.by)


def _answer(rig: Rig, request_id: str, choices: dict[str, str]) -> None:
    shown = rig.inputs.presented[-1]
    answer = InputAnswer(
        request_id=request_id, shown_sha256=shown.fields_schema_sha256, choices=choices, by="engineer:ada"
    )
    rig.inputs.script(request_id, answer)


def _decide(question: str = "pick_action", failing: bool = True) -> DecisionRequest:
    return DecisionRequest(question, Action, State(failing=failing), [], DecisionPolicy())


def _events(rig: Rig, run_id: str, kind: EventType) -> list[Any]:
    return [e.payload for e in rig.events(run_id) if e.type is kind]


def _stored(rig: Rig, n: int) -> Ref:
    """A reference to a result in the rig's store (a fake tool's result is not stored there)."""
    producer = Provenance(tool="harness", tool_version="fake", inputs={}, started_at=rig.clock.now(), duration_ms=0)
    stored = rig.store.put("harness.run_output/1", {"value": {"n": n}}, producer)
    return Ref.model_validate({"$ref": stored.result_id})


def _started(rig: Rig, run_id: str, path: str) -> list[Any]:
    return [e.payload for e in rig.events(run_id) if e.type is T.STEP_STARTED and e.path == path]


def _props(shown: Any) -> dict[str, Any]:
    return cast(dict[str, Any], shown.fields_schema["properties"])


def _refs(outcome: Any) -> list[str]:
    assert outcome.output is not None
    return cast(list[str], outcome.output.refs)


def test_decisions_cannot_produce_numbers(tmp_path: Path) -> None:
    """AC40: options that are no `StrEnum` or references, and an answer that is none of them, reach no block."""
    for n, options in enumerate(([1, 2], int, "enlarge", Action.ENLARGE, ["res_x"], None)):
        rig, port = make_rig(tmp_path / f"o{n}"), FakeDecisionPort()

        async def bad(ctx: Any, options: Any = options) -> list[str]:
            await ctx.decide("pick_action", options, State(failing=True), [], DecisionPolicy())
            return []

        stopped = _run(rig, flow(bad), port)
        assert stopped.status is RunStatus.NEEDS_ENGINEER
        assert stopped.escalation is not None
        assert stopped.escalation.reason == "block_rule_violation"
        assert port.calls == []  # nothing is sent to the port

    def number(call: DecisionCall) -> DecisionAnswer:
        return _decided(call, "2", "rule:fake")

    rig, port = make_rig(tmp_path / "answer"), FakeDecisionPort(number)
    seen: list[BaseException] = []

    async def body(ctx: Any) -> list[str]:
        try:
            await ctx.decide("pick_action", Action, State(failing=True), [], DecisionPolicy())
        except DecisionInvalid as invalid:
            seen.append(invalid)
        return ["handled"]

    outcome = _run(rig, flow(body), port)
    assert outcome.status is RunStatus.COMPLETED
    assert str(seen[0]) == "'2' is not an option of Action"
    failed = _events(rig, outcome.run_id, T.STEP_FAILED)
    assert [f.error.harness_code.value for f in failed] == ["DECISION_INVALID"]
    assert _events(rig, outcome.run_id, T.DECISION_MADE) == []


def test_answer_outside_the_references(tmp_path: Path) -> None:
    """An index at or beyond the count, a negative one, a padded one and a word are `DecisionInvalid`."""
    for choice in ("2", "-1", "01", "1.0", "a"):
        rig = make_rig(tmp_path / f"c{choice}")

        def answer(call: DecisionCall, choice: str = choice) -> DecisionAnswer:
            return _decided(call, choice, "rule:fake")

        port = FakeDecisionPort(answer)
        caught: list[str] = []

        async def body(ctx: Any, caught: list[str] = caught, rig: Rig = rig) -> list[str]:
            first = _stored(rig, 0)
            state = Members(members=("column c1", "column c2"), result=first)
            try:
                await ctx.decide("pick_member", [first, first], state, [], DecisionPolicy())
            except DecisionInvalid as invalid:
                caught.append(str(invalid))
            return []

        assert _run(rig, flow(body), port).status is RunStatus.COMPLETED
        assert caught == [f"{choice!r} is not an index into 2 references"]


def test_rule_decision_and_replay(tmp_path: Path) -> None:
    """A decided call journals `decision_made` (no request) and a resume returns it with no port call."""
    rig, port = make_rig(tmp_path), FakeDecisionPort()

    async def body(ctx: Any) -> list[str]:
        decision = await ctx.decide("pick_action", Action, State(failing=True), [], DecisionPolicy())
        assert decision.choice is Action.ENLARGE
        assert (decision.decided_by, decision.confidence) == ("rule:fake", None)
        await ctx.escalate("stop here", [])
        return []

    workflow = flow(body)
    stopped = _run(rig, workflow, port)
    (call,) = port.calls
    assert (call.request_id, call.step_path, call.point, call.options) == (
        _rid(stopped.run_id, "0"),
        "0",
        ACTION,
        Action,
    )
    assert (call.engineer_choice, call.sensitive_values) == (None, ())
    (made,) = _events(rig, stopped.run_id, T.DECISION_MADE)
    assert (made.point, made.options, made.choice, made.decided_by) == (
        "pick_action",
        ["enlarge", "rebar"],
        "enlarge",
        "rule:fake",
    )
    assert (made.request_id, made.confidence, made.latency_ms, made.state_sha256) == (None, None, 0, "0" * 64)
    started = _started(rig, stopped.run_id, "0")
    assert [(s.kind, s.name, s.effect) for s in started] == [("decide", "pick_action", "none")]
    again = asyncio.run(_engine(rig, workflow, port).resume(stopped.run_id))
    assert again.status is RunStatus.NEEDS_ENGINEER
    assert len(port.calls) == 1  # replayed from the journal
    assert len(_events(rig, stopped.run_id, T.DECISION_MADE)) == 1


def test_references_as_options(tmp_path: Path) -> None:
    """References are answered by index and the block receives the reference; the port gets their strings."""
    rig, port = make_rig(tmp_path), FakeDecisionPort(lambda call: _decided(call, "1", "rule:fake"))

    async def body(ctx: Any) -> list[str]:
        first, second = _stored(rig, 0), _stored(rig, 1)
        state = Members(members=("column c1", "column c2"), result=first)
        decision = await ctx.decide("pick_member", [first, second], state, [], DecisionPolicy())
        assert isinstance(decision.choice, Ref)
        return [decision.choice.ref, first.ref, second.ref]

    outcome = _run(rig, flow(body), port)
    chosen, first, second = _refs(outcome)
    assert chosen == second != first
    (call,) = port.calls
    assert call.options == (first, second)


def test_unknown_point_and_missing_port(tmp_path: Path) -> None:
    """A question that is no registered point is a block rule violation; no port is an internal error."""
    rig, port = make_rig(tmp_path / "a"), FakeDecisionPort()

    async def unknown(ctx: Any) -> list[str]:
        await ctx.decide("pick_nothing", Action, State(failing=True), [], DecisionPolicy())
        return []

    stopped = _run(rig, flow(unknown), port)
    assert stopped.escalation is not None
    assert "'pick_nothing' is not a registered decision point" in stopped.escalation.detail
    assert port.calls == []

    async def plain(ctx: Any) -> list[str]:
        await ctx.decide("pick_action", Action, State(failing=True), [], DecisionPolicy())
        return []

    with pytest.raises(ContractError) as refused:
        _run(make_rig(tmp_path / "b"), flow(plain), None)
    assert refused.value.detail.code is ErrorCode.INTERNAL
    assert "no DecisionPort is configured" in refused.value.detail.message

    async def bad_rules(ctx: Any) -> list[str]:
        await ctx.decide("pick_action", Action, State(failing=True), ["not a rule"], DecisionPolicy())
        return []

    stopped = _run(make_rig(tmp_path / "c"), flow(bad_rules), FakeDecisionPort())
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "block_rule_violation"


def test_stale_reference_stops_before_the_port(tmp_path: Path) -> None:
    """Invariant 3: a reference in the state that no stored result answers is refused before the port call."""
    rig, port = make_rig(tmp_path), FakeDecisionPort()
    missing = Ref.model_validate({"$ref": "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"})

    async def body(ctx: Any) -> list[str]:
        state = Members(members=("column c1",), result=missing)
        await ctx.decide("pick_member", [missing], state, [], DecisionPolicy())
        return []

    with pytest.raises(ContractError) as refused:
        _run(rig, flow(body), port)
    assert refused.value.detail.code is ErrorCode.REF_NOT_FOUND
    assert port.calls == []


def test_engineer_tier_through_input_port(tmp_path: Path) -> None:
    """AC66: a pending call is a request, the answer is an `EngineerChoice`, and `decision_made` closes the request."""
    rig, port = make_rig(tmp_path), FakeDecisionPort(_engineer)

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("write_b", {"n": 0, "model": "m1"})  # binds the model: its file name is a sensitive value
        decision = await ctx.decide("pick_action", Action, State(failing=True), [], DecisionPolicy())
        return [decision.choice.value, decision.decided_by]

    workflow = flow(body)
    paused = _run(rig, workflow, port)
    rid = _rid(paused.run_id, "1")
    assert (paused.status, paused.pending) == (RunStatus.PAUSED, (rid,))
    (asked,) = _events(rig, paused.run_id, T.INPUT_REQUESTED)
    assert (asked.request_id, asked.kind, asked.title) == (rid, "engine.decision", "Pick an action")
    shown = rig.inputs.presented[-1]
    assert (shown.request_id, shown.kind) == (rid, "engine.decision")
    assert shown.fields_schema["x-eng-input"] == "choice"
    assert asked.fields_schema_sha256 == shown.fields_schema_sha256
    props = _props(shown)
    assert props[rid] == {"type": "string", "enum": ["enlarge", "rebar"], "title": "Pick an action"}
    assert props[rid + "_0"]["x-eng-evidence"] is True
    assert props[rid + "_0"]["default"] == "true"
    last = rig.events(paused.run_id)[-1]
    assert last.type is T.RUN_PAUSED
    assert last.payload == ev.RunPaused(reason="awaiting_input", request_ids=[rid])
    (first,) = port.calls
    assert (first.request_id, first.step_path, first.engineer_choice) == (rid, "1", None)
    assert first.sensitive_values == ("m1.edb",)

    _answer(rig, rid, {rid: "rebar"})
    done = asyncio.run(_engine(rig, workflow, port).resume(paused.run_id))
    assert done.status is RunStatus.COMPLETED
    assert _refs(done) == ["rebar", "engineer:ada"]
    assert [c.engineer_choice is None for c in port.calls] == [True, True, False]
    choice = port.calls[2].engineer_choice
    assert choice is not None
    assert (choice.choice, choice.by) == ("rebar", "ada")
    (made,) = _events(rig, paused.run_id, T.DECISION_MADE)
    assert (made.choice, made.decided_by, made.request_id) == ("rebar", "engineer:ada", rid)
    assert _events(rig, paused.run_id, T.INPUT_PROVIDED) == []  # the answer is journaled only as `decision_made`
    assert len(_events(rig, paused.run_id, T.INPUT_REQUESTED)) == 1  # a resume does not ask again
    reader = JournalReader(rig.run_dir(paused.run_id))
    (view,) = reader.requests()
    reader.close()
    assert (view.request_id, view.kind) == (rid, "engine.decision")
    assert isinstance(view.resolution, ev.DecisionMade)


def test_no_answer_pauses_again_and_a_refused_one_keeps_the_request_open(tmp_path: Path) -> None:
    """A resume without an answer pauses at the same request; an answer that fits no option is not passed on."""
    rig, port = make_rig(tmp_path), FakeDecisionPort(_engineer)

    async def body(ctx: Any) -> list[str]:
        return [(await ctx.decide("pick_action", Action, State(failing=True), [], DecisionPolicy())).choice.value]

    workflow = flow(body)
    paused = _run(rig, workflow, port)
    rid = _rid(paused.run_id, "0")
    _answer(rig, rid, {rid: "demolish"})
    again = asyncio.run(_engine(rig, workflow, port).resume(paused.run_id))
    assert (again.status, again.pending) == (RunStatus.PAUSED, (rid,))
    assert all(c.engineer_choice is None for c in port.calls)
    assert len(rig.inputs.presented) == 2
    assert {r.request_id for r in rig.inputs.presented} == {rid}
    assert [p.reason for p in _events(rig, paused.run_id, T.RUN_PAUSED)] == ["awaiting_input", "awaiting_input"]


def test_choice_the_cascade_rejects_is_presented_again(tmp_path: Path) -> None:
    """A `PendingAnswer` that carries `rejected` presents the same request id again and the run pauses."""

    def refuse(call: DecisionCall) -> DecisionAnswer | PendingAnswer:
        if call.engineer_choice is None:
            return _pending(call)
        return _pending(call, rejected="not_an_option")

    rig, port = make_rig(tmp_path), FakeDecisionPort(refuse)

    async def body(ctx: Any) -> list[str]:
        return [(await ctx.decide("pick_action", Action, State(failing=True), [], DecisionPolicy())).choice.value]

    workflow = flow(body)
    paused = _run(rig, workflow, port)
    rid = _rid(paused.run_id, "0")
    _answer(rig, rid, {rid: "rebar"})
    again = asyncio.run(_engine(rig, workflow, port).resume(paused.run_id))
    assert (again.status, again.pending) == (RunStatus.PAUSED, (rid,))
    assert [r.request_id for r in rig.inputs.presented] == [rid, rid, rid]
    assert len(_events(rig, paused.run_id, T.INPUT_REQUESTED)) == 1
    assert _events(rig, paused.run_id, T.DECISION_MADE) == []


def test_decide_many_asks_one_request_for_the_batch(tmp_path: Path) -> None:
    """`decide_many`: the pending calls are one request (id the batch id); each `decision_made` names its own source."""

    def mixed(call: DecisionCall) -> DecisionAnswer | PendingAnswer:
        if call.engineer_choice is not None:
            return _decided(call, call.engineer_choice.choice, "engineer:" + call.engineer_choice.by)
        if isinstance(call.state, State) and call.state.failing:
            return _pending(call, batch=BATCH)
        return _decided(call, "enlarge", "rule:fake")

    rig, port = make_rig(tmp_path), FakeDecisionPort(mixed)

    async def body(ctx: Any) -> list[str]:
        out = await ctx.decide_many([_decide(failing=True), _decide(failing=False), _decide(failing=True)])
        return [d.choice.value for d in out]

    workflow = flow(body)
    paused = _run(rig, workflow, port)
    assert (paused.status, paused.pending) == (RunStatus.PAUSED, (BATCH,))
    assert port.batches == [3]
    assert [c.request_id for c in port.calls] == [_rid(paused.run_id, f"0/{n}") for n in range(3)]
    assert {c.step_path for c in port.calls} == {"0"}
    (asked,) = _events(rig, paused.run_id, T.INPUT_REQUESTED)
    assert (asked.request_id, asked.title) == (BATCH, "2 decisions")
    shown = rig.inputs.presented[-1]
    names = [n for n, p in _props(shown).items() if "enum" in p]
    assert names == [_rid(paused.run_id, "0/0"), _rid(paused.run_id, "0/2")]

    _answer(rig, BATCH, {names[0]: "rebar", names[1]: "enlarge"})
    done = asyncio.run(_engine(rig, workflow, port).resume(paused.run_id))
    assert _refs(done) == ["rebar", "enlarge", "enlarge"]
    made = _events(rig, paused.run_id, T.DECISION_MADE)
    assert [(m.choice, m.decided_by, m.request_id) for m in made] == [
        ("rebar", "engineer:ada", BATCH), ("enlarge", "rule:fake", None), ("enlarge", "engineer:ada", BATCH),
    ]  # fmt: skip
    assert {e.path for e in rig.events(paused.run_id) if e.type is T.DECISION_MADE} == {"0"}
    started = _started(rig, paused.run_id, "0")
    assert [(s.kind, s.name) for s in started] == [("decide_many", "decide_many")]


def test_decide_many_of_decided_calls_needs_no_request(tmp_path: Path) -> None:
    """A batch the cascade decides alone is journaled and returned in order, without a request."""
    rig, port = make_rig(tmp_path), FakeDecisionPort()

    async def body(ctx: Any) -> list[str]:
        out = await ctx.decide_many([_decide(failing=True), _decide(failing=False)])
        return [d.choice.value for d in out]

    outcome = _run(rig, flow(body), port)
    assert _refs(outcome) == ["enlarge", "enlarge"]
    assert rig.inputs.presented == []
    assert _events(rig, outcome.run_id, T.INPUT_REQUESTED) == []
    assert [m.request_id for m in _events(rig, outcome.run_id, T.DECISION_MADE)] == [None, None]


def test_pending_without_a_screen_item_is_internal(tmp_path: Path) -> None:
    """A pending call that its own screen does not show cannot be asked: `INTERNAL`, no request journaled."""

    def blind(call: DecisionCall) -> PendingAnswer:
        return PendingAnswer(request_id=call.request_id, screen=DecisionScreen(items=()))

    rig = make_rig(tmp_path)

    async def body(ctx: Any) -> list[str]:
        await ctx.decide("pick_action", Action, State(failing=True), [], DecisionPolicy())
        return []

    with pytest.raises(ContractError) as refused:
        _run(rig, flow(body), FakeDecisionPort(blind))
    assert refused.value.detail.code is ErrorCode.INTERNAL
    assert rig.inputs.presented == []


def test_sensitive_values_are_the_file_names_the_run_touches(tmp_path: Path) -> None:
    """Bound file names, the original names of a working copy and its own file name; once each, in journal order."""
    rig = make_rig(tmp_path)

    async def body(ctx: Any) -> list[str]:
        return []

    bound = {"model_key": "m1", "host_key": "csi", "instance_id": "i1", "reason": "first_use", "file_names": ["a.edb"]}
    saved = {
        "model_key": "m1", "model_id": "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", "revision": 1, "fingerprint": "f",
        "file_sha256": "1" * 64, "file_name": "copy.edb", "role": "working_copy", "origin_sha256": "2" * 64,
        "origin_file_names": ["client.edb", "a.edb"],
    }  # fmt: skip
    run_id = rig.forge(
        flow(body), (T.MODEL_BOUND, None, bound), (T.MODEL_SAVED, None, saved), (T.MODEL_BOUND, None, bound)
    )
    events = rig.events(run_id)
    no_writer: Any = None  # `_sensitive` only reads the journal
    decider = decide_module.Decider(
        None, rig.inputs, lambda: pytest.fail("no basis"), lambda: events, no_writer, rig.clock, rig.ids, run_id, []
    )
    assert decider._sensitive() == ("a.edb", "client.edb", "copy.edb")
