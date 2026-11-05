"""`ctx.read`: a value of a stored result at a pointer (plan 0001 T10; spec 0001 AC12, contract REF_* codes)."""

import asyncio
from pathlib import Path
from typing import Any

from eng_contract.envelope import Provenance
from eng_contract.errors import ErrorCode
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref
from pydantic import JsonValue
from workflows.ctx_flows import flow
from workflows.rig import Rig, make_rig, request

from eng_harness.ctx import ToolResult
from eng_harness.engine import RunStatus
from eng_harness.errors import Pause, ToolFailed
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev

T = EventType
PAYLOAD: dict[str, JsonValue] = {"load": {"value": 2.5, "unit": "kN"}, "items": [1, 2, 3]}


def _store(rig: Rig) -> str:
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=rig.clock.now(), duration_ms=0)
    return rig.store.put("harness.run_output/1", {"value": PAYLOAD}, producer).result_id


def _ref(text: str) -> Ref:
    return Ref.model_validate({"$ref": text})


def test_read(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    result_id = _store(rig)
    held = ToolResult(tool="read_a", ref=_ref(result_id), summary={}, warnings=(), complete=True, model=None)
    seen: list[Any] = []
    failures: list[ToolFailed] = []
    gate = {"pause": True}

    async def body(ctx: Any) -> list[str]:
        seen.append(await ctx.read(_ref(f"{result_id}#/value/load")))  # the pointer is part of the reference
        seen.append(await ctx.read(_ref(result_id), "/value/items/1"))  # or given apart
        seen.append(await ctx.read(held, "/value/load"))  # a result may stand for its reference
        for bad, pointer in ((f"{result_id}", "/value/missing"), ("res_" + "0" * 26, "/value")):
            try:
                await ctx.read(_ref(bad), pointer)
            except ToolFailed as failed:
                failures.append(failed)
        if gate["pause"]:
            raise Pause("awaiting approval", evidence=["apr_1"])
        return []

    workflow = flow(body)
    paused = asyncio.run(rig.engine(workflow).start(request()))
    assert paused.status is RunStatus.PAUSED
    gate["pause"] = False
    assert asyncio.run(rig.engine(workflow).resume(paused.run_id)).status is RunStatus.COMPLETED
    live, replayed = seen[:3], seen[3:]
    assert live == replayed  # the replayed values equal the live ones
    assert live[0].value == Quantity(2.5, "kN")  # a quantity object comes back as a Quantity
    assert (live[0].kind, live[0].ref.ref) == ("harness.run_output/1", f"{result_id}#/value/load")
    assert live[1].value == 2
    assert live[2].value == live[0].value
    codes = [f.code for f in failures]
    assert codes == [ErrorCode.REF_POINTER_INVALID, ErrorCode.REF_NOT_FOUND] * 2  # live, then replayed from the journal
    assert [f.detail for f in failures[:2]] == [f.detail for f in failures[2:]]
    assert rig.host.ledger == []  # a read is not a host call
    events = rig.events(paused.run_id)
    started = [e for e in events if e.type is T.STEP_STARTED]
    assert [(e.path, e.payload.kind, e.payload.effect) for e in started if isinstance(e.payload, ev.StepStarted)] == [
        ("0", "read", "none"), ("1", "read", "none"), ("2", "read", "none"), ("3", "read", "none"),
        ("4", "read", "none"),
    ]  # fmt: skip
    closing = [e for e in events if e.type in (T.STEP_COMPLETED, T.STEP_FAILED)]
    assert [e.type for e in closing] == [T.STEP_COMPLETED] * 3 + [T.STEP_FAILED] * 2
