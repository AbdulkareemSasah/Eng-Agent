"""`ctx.calc`: the calc step, the draft mark and a refusal of the CalcPort (plan 0001 T10; spec 0001 AC13)."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.quantity import Quantity
from fakes.ports import Raise, failure
from workflows.ctx_flows import flow, success
from workflows.rig import Rig, make_rig, request

from eng_harness.calc import CalcStatus
from eng_harness.engine import RunStatus
from eng_harness.errors import CalcRefused, HarnessCode, Pause, ToolFailed
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import CalcInfo

T = EventType
CALC = "harness.demo"
HASH = "c" * 64


def _rig(tmp_path: Path, status: CalcStatus) -> Rig:
    rig = make_rig(tmp_path)
    rig.calc_infos.append(
        CalcInfo(
            id=CALC,
            version=3,
            content_sha256=HASH,
            status=status,
            engineering_params=(),
            basis_fields=(),
            ref_rules={},
        )
    )
    rig.calc_results[CALC] = success(rig, {"y": {"value": 1.5, "unit": "mm"}})
    return rig


def _pausing(seen: list[Any], gate: dict[str, bool], args: dict[str, Any] | None = None) -> Any:
    async def body(ctx: Any) -> list[str]:
        try:
            seen.append(await ctx.calc(CALC, args or {"a": 1}))
        except CalcRefused as refused:
            seen.append(refused)
        if gate["pause"]:
            raise Pause("awaiting approval", evidence=["apr_1"])
        return []

    return flow(body)


@pytest.mark.parametrize(
    ("status", "draft"),
    [(CalcStatus.APPROVED, False), (CalcStatus.VERIFIED, True), (CalcStatus.DRAFT, True)],
)
def test_calc_step(tmp_path: Path, status: CalcStatus, draft: bool) -> None:
    rig = _rig(tmp_path, status)
    seen: list[Any] = []
    gate = {"pause": True}
    workflow = _pausing(seen, gate)
    paused = asyncio.run(rig.engine(workflow).start(request()))
    assert paused.status is RunStatus.PAUSED
    gate["pause"] = False
    rig.calc_infos[0] = rig.calc_infos[0].model_copy(update={"status": CalcStatus.WITHDRAWN})  # changed since
    done = asyncio.run(rig.engine(workflow).resume(paused.run_id))
    assert done.status is RunStatus.COMPLETED
    live, replayed = seen
    assert live == replayed  # replayed from the journal, with the status the step recorded
    assert (live.calc_id, live.calc_version, live.status, live.draft) == (CALC, 3, status, draft)
    assert live.summary["y"] == Quantity(1.5, "mm")
    assert len(rig.calc_runs) == 1  # the resume ran no calc
    assert rig.calc_runs[0] == (CALC, {"a": 1})
    events = rig.events(paused.run_id)
    started, completed = events[1].payload, events[2].payload
    assert isinstance(started, ev.StepStarted)
    assert (started.kind, started.name, started.effect, started.args) == ("calc", CALC, "none", {"a": 1})
    assert isinstance(completed, ev.StepCompleted)
    assert completed.calc == ev.CalcRef(id=CALC, version="3", content_sha256=HASH, status=status.value)
    assert completed.result is not None
    assert completed.result.ref == live.ref.ref
    finished = events[-1].payload
    assert isinstance(finished, ev.RunCompleted)
    assert finished.draft is draft  # a draft or verified calc marks the outputs DRAFT


@pytest.mark.parametrize("code", [HarnessCode.CALC_NOT_APPROVED, HarnessCode.CALC_WITHDRAWN])
def test_calc_refused(tmp_path: Path, code: HarnessCode) -> None:
    rig = _rig(tmp_path, CalcStatus.DRAFT)
    rig.calc_results[CALC] = Raise(CalcRefused(code, "refused"))
    seen: list[Any] = []
    gate = {"pause": True}
    workflow = _pausing(seen, gate)
    paused = asyncio.run(rig.engine(workflow).start(request()))
    gate["pause"] = False
    assert asyncio.run(rig.engine(workflow).resume(paused.run_id)).status is RunStatus.COMPLETED
    first, again = seen
    assert isinstance(first, CalcRefused)
    assert (first.code, first.message) == (code, "refused")
    assert (again.code, again.message) == (code, "refused")  # raised again from the journal
    assert len(rig.calc_runs) == 1
    failed = rig.events(paused.run_id)[2].payload
    assert isinstance(failed, ev.StepFailed)
    assert failed.error == ev.HarnessError(harness_code=code, message="refused")
    assert failed.retryable is False
    finished = rig.events(paused.run_id)[-1].payload
    assert isinstance(finished, ev.RunCompleted)
    assert finished.draft is False  # no calc ran


def test_an_unhandled_refusal_escalates(tmp_path: Path) -> None:
    rig = _rig(tmp_path, CalcStatus.DRAFT)
    rig.calc_results[CALC] = Raise(CalcRefused(HarnessCode.CALC_WITHDRAWN, "withdrawn"))

    async def body(ctx: Any) -> list[str]:
        await ctx.calc(CALC, {})
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.NEEDS_ENGINEER
    assert outcome.escalation is not None
    assert (outcome.escalation.reason, outcome.escalation.detail) == ("unhandled_error", "withdrawn")


def test_a_failure_envelope_of_a_calc_is_a_tool_failure(tmp_path: Path) -> None:
    rig = _rig(tmp_path, CalcStatus.APPROVED)
    rig.calc_results[CALC] = failure(ErrorCode.INVALID_ARGUMENT, "bad input")
    caught: list[ToolFailed] = []

    async def body(ctx: Any) -> list[str]:
        try:
            await ctx.calc(CALC, {})
        except ToolFailed as failed:
            caught.append(failed)
        return []

    assert asyncio.run(rig.engine(flow(body)).start(request())).status is RunStatus.COMPLETED
    assert caught[0].code is ErrorCode.INVALID_ARGUMENT


def test_an_unknown_calc_is_refused_before_a_step_starts(tmp_path: Path) -> None:
    rig = _rig(tmp_path, CalcStatus.APPROVED)

    async def body(ctx: Any) -> list[str]:
        await ctx.calc("harness.unknown", {})
        return []

    with pytest.raises(ContractError) as refused:
        asyncio.run(rig.engine(flow(body)).start(request()))
    assert refused.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert rig.calc_runs == []
    run_id = rig.run_ids()[0]
    assert rig.types(run_id) == [T.RUN_STARTED]
