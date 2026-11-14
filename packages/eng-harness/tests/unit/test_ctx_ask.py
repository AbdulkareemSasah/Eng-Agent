"""`ctx.ask` and the `x-eng-input` marker of the requests the engine presents (plan 0001 T14b; AC61, AC67).

The fake input port stands for the page of spec 0006: it holds the request the engine presented and the answers the
test scripts. The block is a plain test body wrapped as a workflow.
"""

import asyncio
import hashlib
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.errors import ContractError, ErrorCode
from pydantic import BaseModel, ConfigDict
from workflows.ctx_flows import flow
from workflows.rig import Rig, make_rig, request

from eng_harness.engine import RunStatus
from eng_harness.engine._inputs import MARKER, Kind, build_request, data_schema
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import InputAnswer

T = EventType


class Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    width: str
    count: int


def _rid(run_id: str, path: str) -> str:
    return "ask_" + hashlib.sha256(f"{run_id}\n{path}".encode()).hexdigest()[:32]


def _answer(rig: Rig, rid: str, values: dict[str, Any], by: str = "ada") -> None:
    shown = rig.inputs.presented[-1]
    rig.inputs.script(
        rid, InputAnswer(request_id=rid, shown_sha256=shown.fields_schema_sha256, values=values, by=by)
    )


def _body(seen: list[Any]) -> Any:
    async def body(ctx: Any) -> list[str]:
        first = await ctx.ask(Section, title="Section sizes")
        second = await ctx.ask(Section, title="Check sizes")
        seen.extend([first, second])
        return [first.ref.ref, first.field_ref("width").ref, second.ref.ref]

    return body


def test_ask_stores_engineer_input(tmp_path: Path) -> None:
    """AC61: no answer pauses; an answer that fails the fields is refused; a valid one is stored and replayed."""
    rig = make_rig(tmp_path)
    seen: list[Any] = []
    engine = rig.engine(flow(_body(seen)))
    paused = asyncio.run(engine.start(request()))
    first, second = _rid(paused.run_id, "0"), _rid(paused.run_id, "1")
    assert (paused.status, paused.pending) == (RunStatus.PAUSED, (first,))
    requested = [e.payload for e in rig.events(paused.run_id) if isinstance(e.payload, ev.InputRequested)]
    assert [(r.request_id, r.kind, r.title) for r in requested] == [(first, "block", "Section sizes")]
    assert rig.events(paused.run_id)[-1].payload == ev.RunPaused(reason="awaiting_input", request_ids=[first])
    _answer(rig, first, {"width": "300", "count": "many"})  # an answer that fails `fields` is refused
    again = asyncio.run(engine.resume(paused.run_id))
    assert (again.status, again.pending) == (RunStatus.PAUSED, (first,))
    assert [r.request_id for r in rig.inputs.presented] == [first, first]  # presented again, journaled once
    assert len([e for e in rig.events(paused.run_id) if e.type is T.INPUT_REQUESTED]) == 1
    _answer(rig, first, {"width": "300", "count": 4})
    second_pause = asyncio.run(engine.resume(paused.run_id))  # the first ask is replayed, the second one waits
    assert (second_pause.status, second_pause.pending) == (RunStatus.PAUSED, (second,))
    assert [r.request_id for r in rig.inputs.presented] == [first, first, first, second]
    _answer(rig, second, {"width": "250", "count": 2}, by="engineer:ada")  # a port that prefixes `by`
    done = asyncio.run(engine.resume(paused.run_id))
    assert done.status is RunStatus.COMPLETED
    assert [r.request_id for r in rig.inputs.presented][-1] == second  # the answered first ask was not shown again
    assert seen[0].value == Section(width="300", count=4)
    provided = [e.payload for e in rig.events(done.run_id) if isinstance(e.payload, ev.InputProvided)]
    assert [(p.request_id, p.by) for p in provided] == [(first, "engineer:ada"), (second, "engineer:ada")]
    stored = cast(dict[str, Any], rig.store.payload(provided[0].answer_ref))
    assert stored["step"] == "0"  # the step path that asked, not the request id
    assert {k: v["value"] for k, v in stored["fields"].items()} == {"width": "300", "count": 4}
    assert {v["entered_by"] for v in stored["fields"].values()} == {"ada"}
    again_stored = cast(dict[str, Any], rig.store.payload(provided[1].answer_ref))
    assert again_stored["step"] == "1"
    assert {v["entered_by"] for v in again_stored["fields"].values()} == {"ada"}  # the prefix is not doubled
    assert done.output is not None
    refs = [provided[0].answer_ref, f"{provided[0].answer_ref}#/fields/width/value", provided[1].answer_ref]
    assert cast(Any, done.output).refs == refs
    kinds = [(e.type, e.path) for e in rig.events(done.run_id) if e.path in ("0", "1")]
    assert kinds[:2] == [(T.STEP_STARTED, "0"), (T.STEP_COMPLETED, "0")]


def test_ask_refuses_fields_that_are_no_model(tmp_path: Path) -> None:
    """Rule 6: `fields` must be a Pydantic model (AC16)."""
    rig = make_rig(tmp_path)

    async def body(ctx: Any) -> list[str]:
        await ctx.ask(int, title="A number")
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.NEEDS_ENGINEER
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "block_rule_violation"
    assert rig.inputs.presented == []


def test_input_request_markers(tmp_path: Path) -> None:
    """AC67: a data request for `ctx.ask`, no request without a marker, and the marker is in the schema hash."""
    rig = make_rig(tmp_path)
    paused = asyncio.run(rig.engine(flow(_body([]))).start(request()))
    shown = rig.inputs.presented[0]
    assert shown.kind == "block"
    assert shown.fields_schema[MARKER] == "data"
    assert shown.fields_schema["properties"] == Section.model_json_schema()["properties"]
    assert paused.status is RunStatus.PAUSED
    ids = rig.ids
    plain = Section.model_json_schema()
    for kind, schema in (
        ("block", plain),
        ("block", {**plain, MARKER: "choice"}),
        ("engine.decision", data_schema(plain)),
    ):
        with pytest.raises(ContractError) as refused:
            build_request(ids, "x", cast(Kind, kind), "t", schema)
        assert refused.value.detail.code is ErrorCode.INTERNAL
    marked, other = (
        build_request(ids, "x", "block", "t", data_schema(plain)),
        build_request(ids, "x", "block", "t", plain | {MARKER: "data", "title": "other"}),
    )
    assert marked.fields_schema_sha256 != other.fields_schema_sha256
