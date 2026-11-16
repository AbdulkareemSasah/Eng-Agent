"""Invariants 1, 2, 3, 5, 7 and 8 through the engine (plan 0001 T12, T13; spec 0001 4.6, AC37-AC39, AC41, AC43, AC44).

A write is checked before the next read of that model, any calc and the block's return. An engineering parameter
rejects a literal before the port call. A stale reference is refused unless the calc's rule says `stale_ok`. An
analysis or design tool is preceded by a save. An incomplete design basis or a failing server check refuses the run
before its folder exists.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import pytest
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.ids import new_model_id, new_result_id
from eng_contract.kinds.basis import BasisField, DesignBasis
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref, RefRule
from fakes.ports import Raise, failure
from workflows.chain import ORIGINAL, ChainInput, ChainOutput, chain
from workflows.ctx_flows import flow, need_approval, success
from workflows.rig import Host, make_rig, request, watch_closing

from eng_harness.block import workflow
from eng_harness.calc import CalcStatus
from eng_harness.engine import RunStatus
from eng_harness.errors import HarnessCode, ModelIntegrityError, RunRefused, ToolFailed
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import CalcInfo, HostInstance, HostLease, LoadedBasis, ServerCheck, ToolInfo, UnitsState

_SHA = "ab" * 32
Body = Callable[[Any], Awaitable[Sequence[str]]]
_DIFFER = UnitsState(loaded=True, ok=False, present="unit-system-b", expected="unit-system-a")


def _tool(
    host: Any,
    name: str,
    effect: Literal["read", "write"],
    action: Literal["plain", "analysis", "design"],
    model: str | None,
    params: tuple[str, ...] = (),
) -> None:
    """Register one tool on the fake host."""
    host._tools[name] = ToolInfo(
        name=name, effect=effect, action=action, host_key="csi", model_param=model, engineering_params=params
    )


def _tools(host: Any) -> None:
    """Model-addressed tools and one tool with an engineering parameter, on the fake host."""
    _tool(host, "write_m", "write", "plain", "model")
    _tool(host, "read_m", "read", "plain", "model")
    _tool(host, "analyze", "read", "analysis", "model")
    _tool(host, "design", "write", "design", "model")
    _tool(host, "size_it", "read", "plain", None, ("span",))


def _open(rig: Any, *keys: str) -> None:
    """Open `keys` so a save has a loaded model."""
    instance = HostInstance(instance_id="i-1", pid=7, process_started_at=rig.clock.now(), program="csi")
    for key in keys:
        rig.host.add_model(key, instance)


def _calc(rig: Any, rules: Mapping[str, RefRule] | None = None, *, params: tuple[str, ...] = ()) -> None:
    """Register calc `c` and a success result for it."""
    rig.calc_infos.append(
        CalcInfo(
            id="c", version=1, content_sha256=_SHA, status=CalcStatus.APPROVED, engineering_params=params,
            basis_fields=(), ref_rules=dict(rules or {}),
        )
    )  # fmt: skip
    rig.calc_results["c"] = success(rig, {"ok": True})


def _paths(rig: Any, run_id: str) -> list[str]:
    return [e.path for e in rig.events(run_id) if e.path and e.type is EventType.STEP_STARTED]


def test_check_after_write(tmp_path: Path) -> None:
    """A dirty model is checked before a read, before a parallel, after it, and before the block returns (AC37)."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    _calc(rig)

    async def read_after_write(ctx: Any) -> list[str]:
        await ctx.tool("write_m", {"model": "m1"})
        await ctx.tool("read_m", {"model": "m1"})
        await ctx.calc("c", {})
        return []

    done = asyncio.run(rig.engine(flow(read_after_write)).start(request()))
    assert done.status is RunStatus.COMPLETED
    paths = _paths(rig, done.run_id)
    assert "1~pre.check_model.m1" in paths
    assert paths.index("1~pre.check_model.m1") < paths.index("1")
    enforced = [e.payload for e in rig.events(done.run_id) if isinstance(e.payload, ev.CheckEnforced)]
    assert enforced == [
        ev.CheckEnforced(invariant=9, model_key="m1", outcome="pass"),
        ev.CheckEnforced(invariant=1, model_key="m1", outcome="pass"),
    ]  # the units of the first use, then the check
    # the read's call is after the check; nothing turns the check off (no argument was passed to disable it)
    assert rig.log.index("host.check_model") < rig.log.index("tool.call", rig.log.index("host.check_model"))

    async def returns(ctx: Any) -> list[str]:
        await ctx.tool("write_m", {"model": "m1"})
        return []

    end = asyncio.run(rig.engine(flow(returns)).start(request()))
    assert "~end.check_model.m1" in _paths(rig, end.run_id)

    async def across(ctx: Any) -> list[str]:
        await ctx.tool("write_m", {"model": "m1"})

        async def read() -> str:
            await ctx.tool("read_m", {"model": "m1"})
            return "ok"

        await ctx.parallel(read())
        return []

    pre = asyncio.run(rig.engine(flow(across)).start(request()))
    pre_paths = _paths(rig, pre.run_id)
    assert "1~pre.check_model.m1" in pre_paths
    assert "1/0~pre.check_model.m1" not in pre_paths  # the child did not inherit the parent's dirty flag

    async def both(ctx: Any) -> list[str]:
        async def write(model: str) -> str:
            await ctx.tool("write_m", {"model": model})
            return model

        await ctx.parallel(write("m2"), write("m1"))
        return []

    post = asyncio.run(rig.engine(flow(both)).start(request()))
    post_paths = _paths(rig, post.run_id)
    assert post_paths.index("0~post.check_model.m1") < post_paths.index("0~post.check_model.m2")

    rig.host.script_check("m1", failure(ErrorCode.INVALID_ARGUMENT, "the model check failed"))
    failed = asyncio.run(rig.engine(flow(returns)).start(request()))
    assert failed.status is RunStatus.NEEDS_ENGINEER
    assert failed.escalation is not None
    assert failed.escalation.reason == "unhandled_error"
    assert "m1" in failed.escalation.detail
    bad = [e.payload for e in rig.events(failed.run_id) if isinstance(e.payload, ev.CheckEnforced)]
    assert bad[-1] == ev.CheckEnforced(invariant=1, model_key="m1", outcome="fail")


def test_unclean_check_stops_run(tmp_path: Path) -> None:
    """A check whose summary is not clean stops the run like a failed check; the evidence is the stored check (AC37)."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    unclean = rig.host._success("check_model").model_copy(
        update={"summary": {"errors": 1, "warnings": 0, "infos": 0, "clean": False}}
    )
    rig.host.script_check("m1", unclean)
    caught: list[ModelIntegrityError] = []

    async def read_after_write(ctx: Any) -> list[str]:
        await ctx.tool("write_m", {"model": "m1"})
        try:
            await ctx.tool("read_m", {"model": "m1"})
        except ModelIntegrityError as exc:
            caught.append(exc)
            raise
        return []

    done = asyncio.run(rig.engine(flow(read_after_write)).start(request()))
    assert done.status is RunStatus.NEEDS_ENGINEER
    assert [exc.evidence for exc in caught] == [(unclean.result_id,)]
    assert [entry.tool for entry in rig.host.ledger] == ["write_m"]  # no port call follows the unclean check
    events = rig.events(done.run_id)
    failed = [e for e in events if e.type is EventType.STEP_FAILED and e.path == "1~pre.check_model.m1"]
    assert len(failed) == 1
    assert isinstance(failed[0].payload, ev.StepFailed)
    error = failed[0].payload.error
    assert isinstance(error, ev.HarnessError)
    assert error.harness_code is HarnessCode.MODEL_INTEGRITY
    assert error.message == "the check of m1 failed: the summary reports 1 errors"
    enforced = [e.payload for e in events if isinstance(e.payload, ev.CheckEnforced)]
    assert enforced[-1] == ev.CheckEnforced(invariant=1, model_key="m1", outcome="fail")
    assert ev.CheckEnforced(invariant=1, model_key="m1", outcome="pass") not in enforced


def test_other_summary_shape_counts_as_not_clean(tmp_path: Path) -> None:
    """A summary that is not an `issues.model_check/1` summary is not clean either (AC37)."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    rig.host.script_check("m1", rig.host._success("check_model"))  # the summary is {"tool": "check_model"}

    async def read_after_write(ctx: Any) -> list[str]:
        await ctx.tool("write_m", {"model": "m1"})
        await ctx.tool("read_m", {"model": "m1"})
        return []

    done = asyncio.run(rig.engine(flow(read_after_write)).start(request()))
    assert done.status is RunStatus.NEEDS_ENGINEER
    assert done.escalation is not None
    assert "the summary is not a model check summary" in done.escalation.detail
    assert [entry.tool for entry in rig.host.ledger] == ["write_m"]


def test_engineering_literal_rejected(tmp_path: Path) -> None:
    """A number, a quantity object or a Quantity for an engineering parameter never reaches the port (AC38)."""
    literals: tuple[object, ...] = (3, 1.5, Quantity(450.0, "mm"), {"value": 450.0, "unit": "mm"})
    for literal in literals:
        rig = make_rig(tmp_path / str(type(literal).__name__))
        _tools(rig.host)

        async def body(ctx: Any, value: object = literal) -> list[str]:
            await ctx.tool("size_it", {"span": value})
            return []

        with pytest.raises(ContractError) as caught:
            asyncio.run(rig.engine(flow(body)).start(request()))
        assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
        assert caught.value.detail.field == "span"
        assert rig.host.ledger == []

    rig = make_rig(tmp_path / "calc")
    _calc(rig, params=("span",))

    async def calc_body(ctx: Any) -> list[str]:
        await ctx.calc("c", {"span": 3})
        return []

    with pytest.raises(ContractError) as caught:
        asyncio.run(rig.engine(flow(calc_body)).start(request()))
    assert caught.value.detail.field == "span"
    assert rig.calc_runs == []


def test_engineering_ref_is_accepted(tmp_path: Path) -> None:
    """An engineering parameter that is a reference reaches the port (AC38)."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    span = Ref.model_validate({"$ref": "res_" + "1" * 26})

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("size_it", {"span": span})
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.COMPLETED
    assert [entry.tool for entry in rig.host.ledger] == ["size_it"]


def _hosted(rig: Any, model_id: str, revision: int) -> Provenance:
    host = HostInfo(program="csi", version="1", model_id=model_id, model_revision=revision)
    return Provenance(tool="harness", tool_version="t", host=host, inputs={}, started_at=rig.clock.now(), duration_ms=0)


def _stale_rig(tmp: Path, rules: Mapping[str, RefRule], *, payload: dict[str, Any] | None = None) -> tuple[Any, str]:
    rig = make_rig(tmp)
    _tools(rig.host)
    _calc(rig, rules)
    model_id = new_model_id(rig.ids)
    stored = rig.store.put("harness.run_output/1", payload or {"value": 1}, _hosted(rig, model_id, 1))
    newer = SuccessEnvelope(
        contract="eng-contract/1", ok=True, result_id=new_result_id(rig.ids), kind="harness.run_output/1",
        summary={}, complete=True, provenance=_hosted(rig, model_id, 2),
    )  # fmt: skip
    rig.host.script("write_m", newer)
    return rig, stored.result_id


def _calc_of(ref: str) -> Body:
    async def body(ctx: Any) -> list[str]:
        await ctx.tool("write_m", {"model": "m1"})
        await ctx.calc("c", {"span": Ref.model_validate({"$ref": ref})})
        return []

    return body


def test_stale_ref(tmp_path: Path) -> None:
    """A reference older than the model is REF_STALE unless the calc declares stale_ok; kind and unit too (AC39)."""
    rig, ref = _stale_rig(tmp_path / "stale", {})
    with pytest.raises(ContractError) as caught:
        asyncio.run(rig.engine(flow(_calc_of(ref))).start(request()))
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.REF_STALE, "span")
    assert rig.calc_runs == []

    allowed, ref_ok = _stale_rig(tmp_path / "ok", {"span": RefRule(stale_ok=True, field="span")})
    ran = asyncio.run(allowed.engine(flow(_calc_of(ref_ok))).start(request()))
    assert ran.status is RunStatus.COMPLETED
    assert len(allowed.calc_runs) == 1

    mismatched, ref_kind = _stale_rig(tmp_path / "kind", {"span": RefRule(kinds=frozenset({"other.thing/1"}))})
    with pytest.raises(ContractError) as kind:
        asyncio.run(mismatched.engine(flow(_calc_of(ref_kind))).start(request()))
    assert kind.value.detail.code is ErrorCode.REF_KIND_MISMATCH
    assert mismatched.calc_runs == []

    unit_payload: dict[str, Any] = {"value": {"value": 12.0, "unit": "mm"}}
    units, ref_unit = _stale_rig(tmp_path / "unit", {"span": RefRule(unit="m", field="span")}, payload=unit_payload)
    pointer = f"{ref_unit}#/value"

    async def unit_body(ctx: Any) -> list[str]:
        await ctx.tool("write_m", {"model": "m1"})
        await ctx.calc("c", {"span": Ref.model_validate({"$ref": pointer})})
        return []

    with pytest.raises(ContractError) as unit:
        asyncio.run(units.engine(flow(unit_body)).start(request()))
    assert unit.value.detail.code is ErrorCode.REF_UNIT_MISMATCH
    assert units.calc_runs == []


def test_save_before_analysis(tmp_path: Path) -> None:
    """A tool whose action is analysis or design is preceded by a save, and that save is journaled (AC43)."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    _open(rig, "m1")

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("analyze", {"model": "m1"})
        await ctx.tool("design", {"model": "m1"})
        return []

    done = asyncio.run(rig.engine(flow(body)).start(request()))
    assert done.status is RunStatus.COMPLETED
    events = rig.events(done.run_id)
    saves = [e.payload for e in events if isinstance(e.payload, ev.StepStarted) and e.payload.name == "save"]
    assert [e.path for e in events if isinstance(e.payload, ev.StepStarted) and e.payload.name == "save"] == [
        "0~pre.save.m1", "1~pre.save.m1",
    ]  # fmt: skip
    assert [(s.kind, s.effect, s.op_id) for s in saves] == [("read", "read", None)] * 2
    recorded = [e.payload for e in events if isinstance(e.payload, ev.ModelSaved)]
    assert [s.role for s in recorded] == ["pre_analysis", "pre_analysis"]
    assert {s.model_key for s in recorded} == {"m1"}
    started = [e.payload for e in events if isinstance(e.payload, ev.StepStarted) and e.payload.kind == "tool"]
    assert [s.action for s in started] == ["analysis", "design"]


@workflow(
    name="needs_basis", version=1, description="needs two basis fields",
    required_basis=("code.edition", "loads.risk_category", "site.seismic_class"),
)  # fmt: skip
async def _needs_basis(ctx: Any, inp: ChainInput) -> ChainOutput:
    return ChainOutput(refs=[(await ctx.tool("read_a", {"n": 0})).ref.ref])


@workflow(name="checked", version=1, description="needs a server build", min_server_builds={"csi": "build-1"})
async def _checked(ctx: Any, inp: ChainInput) -> ChainOutput:
    return ChainOutput(refs=[(await ctx.tool("read_a", {"n": 0})).ref.ref])


def _field(confirmed: bool) -> BasisField:
    source = "engineer:t@2026-01-01T00:00:00.000Z"
    return BasisField(value="x", unit=None, source=source, confirmed=confirmed, citation=None)


def test_basis_incomplete_refused(tmp_path: Path) -> None:
    """A required basis field that is absent or unconfirmed refuses the run before any folder or port call (AC41)."""
    ref = "res_" + "2" * 26
    fields = {"code.edition": _field(True), "loads.risk_category": _field(False)}
    basis = LoadedBasis(result_id=ref, basis=DesignBasis(template=None, fields=fields))
    rig = make_rig(tmp_path, bases={ref: basis})
    with pytest.raises(RunRefused) as refused:
        asyncio.run(rig.engine(_needs_basis).start(request(workflow="needs_basis", basis_ref=ref)))
    assert refused.value.code is HarnessCode.BASIS_INCOMPLETE
    assert refused.value.evidence == ("loads.risk_category", "site.seismic_class")  # in the workflow's order
    assert rig.run_ids() == []
    assert not [line for line in rig.log if line.startswith(("tool.", "host."))]
    fields["loads.risk_category"] = _field(True)
    fields["site.seismic_class"] = _field(True)
    complete = LoadedBasis(result_id=ref, basis=DesignBasis(template=None, fields=fields))
    rig = make_rig(tmp_path / "complete", bases={ref: complete})
    done = asyncio.run(rig.engine(_needs_basis).start(request(workflow="needs_basis", basis_ref=ref)))
    assert done.status is RunStatus.COMPLETED


def test_server_check(tmp_path: Path) -> None:
    """A failing server check refuses the run at start, before the run folder and any tool call (AC44)."""
    fail = ServerCheck(
        server="csi", build="old", min_build="build-1", fingerprint="a", expected_fingerprint="b", ok=False,
        reason="build below the minimum",
    )  # fmt: skip
    rig = make_rig(tmp_path)
    rig.host.preflight_checks = [fail]
    with pytest.raises(RunRefused) as refused:
        asyncio.run(rig.engine(_checked).start(request(workflow="checked")))
    assert refused.value.code is HarnessCode.SERVER_CHECK_FAILED
    assert rig.run_ids() == []
    assert "host.preflight" in rig.log
    assert rig.host.ledger == []
    rig.host.preflight_checks = None  # every check passes: the checks are recorded in the header
    done = asyncio.run(rig.engine(_checked).start(request(workflow="checked")))
    assert done.status is RunStatus.COMPLETED
    servers = rig.header(done.run_id).servers
    assert [(s["server"], s["min_build"], s["ok"]) for s in servers] == [("csi", "build-1", True)]
    unchecked = make_rig(tmp_path / "unchecked")  # a workflow that names no minimum build has no server to check
    asyncio.run(unchecked.engine(_needs_nothing).start(request(workflow="needs_nothing")))
    assert "host.preflight" not in unchecked.log


@workflow(name="needs_nothing", version=1, description="no basis field, no server build")
async def _needs_nothing(ctx: Any, inp: ChainInput) -> ChainOutput:
    return ChainOutput(refs=[(await ctx.tool("read_a", {"n": 0})).ref.ref])


def test_refusal_messages_name_what_failed(tmp_path: Path) -> None:
    """The refusals name the missing basis fields and each failed server with its reason (AC41, AC44)."""
    ref = "res_" + "3" * 26
    empty = LoadedBasis(result_id=ref, basis=DesignBasis(template=None, fields={}))
    rig = make_rig(tmp_path, bases={ref: empty})
    with pytest.raises(RunRefused) as basis:
        asyncio.run(rig.engine(_needs_basis).start(request(workflow="needs_basis", basis_ref=ref)))
    assert basis.value.message == (
        "the design basis lacks or has not confirmed code.edition, loads.risk_category, site.seismic_class"
    )
    good, old, wrong = (
        ServerCheck(
            server=name, build="b", min_build="b", fingerprint="f", expected_fingerprint="f", ok=ok, reason=reason
        )
        for name, ok, reason in (
            ("csi", True, None),
            ("etabs", False, "build below the minimum"),
            ("safe", False, None),
        )
    )
    rig = make_rig(tmp_path / "servers")
    rig.host.preflight_checks = [good, old, wrong]
    with pytest.raises(RunRefused) as servers:
        asyncio.run(rig.engine(_checked).start(request(workflow="checked")))
    assert servers.value.evidence == ("etabs", "safe")  # the failed checks only, in the order of the port
    assert servers.value.message == "server check failed: etabs (build below the minimum); safe (not ok)"


def test_no_basis_read_when_nothing_is_required(tmp_path: Path) -> None:
    """A workflow that requires no basis field does not load the basis, so an unknown reference does not stop it."""
    rig = make_rig(tmp_path)
    done = asyncio.run(rig.engine(_needs_nothing).start(request(workflow="needs_nothing", basis_ref="res_" + "1" * 26)))
    assert done.status is RunStatus.COMPLETED
    assert "basis.load" not in rig.log
    assert rig.header(done.run_id).servers == []


def _trail(rig: Any, run_id: str, *types: EventType) -> list[tuple[str, str | None]]:
    """(type, path) of the events of the given types, in journal order."""
    return [(e.type.value, e.path) for e in rig.events(run_id) if e.type in types]


def _read_twice(rig: Any, between: Callable[[], None]) -> Body:
    """A block that reads m1, runs `between` (the host changes), and reads m1 again."""

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_m", {"model": "m1"})
        between()
        await ctx.tool("read_m", {"model": "m1"})
        return []

    return body


def test_units_after_reconnect(tmp_path: Path) -> None:
    """Units are read at the first use, at a resume, and after a reconnect or a timeout; a mismatch stops (AC45)."""
    marks = (EventType.MODEL_BOUND, EventType.STEP_STARTED, EventType.CHECK_ENFORCED)
    rig = make_rig(tmp_path / "first")
    _tools(rig.host)
    _open(rig, "m1")
    rig.host.epochs["csi"] = 7  # the epoch is compared with the one this process saw first, whatever its value
    rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))  # the run stops at its last step

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_m", {"model": "m1"})
        await ctx.tool("read_m", {"model": "m1"})
        await ctx.tool("read_c", {"n": 0})
        return []

    stopped = asyncio.run(rig.engine(flow(body)).start(request()))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert _trail(rig, stopped.run_id, *marks)[:5] == [
        ("model_bound", None), ("step_started", "0~pre.units.m1"), ("check_enforced", "0~pre.units.m1"),
        ("step_started", "0"), ("step_started", "1"),
    ]  # fmt: skip  # once, right after the binding and before the step; the second read of m1 reads no units
    enforced = [e.payload for e in rig.events(stopped.run_id) if isinstance(e.payload, ev.CheckEnforced)]
    assert enforced == [ev.CheckEnforced(invariant=9, model_key="m1", outcome="pass")]
    assert rig.log.count("host.read_units") == 1
    (units,) = [
        e.payload.result.summary
        for e in rig.events(stopped.run_id)
        if e.path == "0~pre.units.m1" and isinstance(e.payload, ev.StepCompleted) and e.payload.result
    ]
    assert units == {"loaded": True, "instance_id": "i-1"}
    again = asyncio.run(rig.engine(flow(body)).resume(stopped.run_id))
    assert again.status is RunStatus.COMPLETED
    paths = [e.path for e in rig.events(stopped.run_id) if e.type is EventType.STEP_STARTED]
    assert paths.count("0~pre.units.m1") == 1  # replayed, not read again
    assert "@resume1.units.m1" in paths  # a model the journal only addressed (read) has its units read at a resume
    assert rig.log.count("host.read_units") == 2

    differ = make_rig(tmp_path / "differ")
    _tools(differ.host)
    _open(differ, "m1")
    differ.host.units["m1"] = _DIFFER
    first = asyncio.run(differ.engine(flow(_read_twice(differ, lambda: None))).start(request()))
    assert first.status is RunStatus.NEEDS_ENGINEER  # the run stops (spec 6): it does not raise to the block
    assert first.escalation is not None
    assert first.escalation.reason == "units_mismatch"
    assert differ.host.ledger == []
    run_id = first.run_id
    assert _trail(differ, run_id, EventType.RUN_ESCALATED, EventType.STEP_STARTED) == [("run_escalated", None)]
    escalated = [e.payload for e in differ.events(run_id) if isinstance(e.payload, ev.RunEscalated)]
    assert [p.reason for p in escalated] == ["units_mismatch"]

    reconnect = make_rig(tmp_path / "reconnect")
    _tools(reconnect.host)
    _open(reconnect, "m1")
    host = reconnect.host

    def reconnected() -> None:
        host.epochs["csi"] += 1

    done = asyncio.run(reconnect.engine(flow(_read_twice(reconnect, reconnected))).start(request()))
    assert done.status is RunStatus.COMPLETED
    assert _trail(reconnect, done.run_id, EventType.STEP_STARTED) == [
        ("step_started", "0~pre.units.m1"), ("step_started", "0"), ("step_started", "1~host.units.m1"),
        ("step_started", "1"),
    ]  # fmt: skip  # the epoch changed before the second step: its units are read first, as an audit record
    assert reconnect.log.count("host.read_units") == 2

    def reconnected_and_changed() -> None:
        host.epochs["csi"] += 1
        host.units["m1"] = _DIFFER

    changed = make_rig(tmp_path / "changed")
    _tools(changed.host)
    _open(changed, "m1")
    host = changed.host
    second = asyncio.run(changed.engine(flow(_read_twice(changed, reconnected_and_changed))).start(request()))
    assert second.status is RunStatus.NEEDS_ENGINEER
    assert second.escalation is not None
    assert second.escalation.reason == "units_mismatch"
    assert [entry.tool for entry in changed.host.ledger] == ["read_m"]  # the second read never reached the host
    assert "1" not in [e.path for e in changed.events(second.run_id) if e.type is EventType.STEP_STARTED]


def test_units_mismatch_cannot_be_caught_by_the_block(tmp_path: Path) -> None:
    """A block that catches an error around the step after a reconnect cannot go on with the wrong units (AC45)."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    _open(rig, "m1")
    host = rig.host

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_m", {"model": "m1"})
        host.epochs["csi"] += 1
        host.units["m1"] = _DIFFER
        with contextlib.suppress(Exception):  # a block that swallows every error of the step
            await ctx.tool("read_m", {"model": "m1"})
        await ctx.tool("read_m", {"model": "m1"})
        return []

    stopped = asyncio.run(rig.engine(flow(body)).start(request()))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "units_mismatch"
    assert [entry.tool for entry in host.ledger] == ["read_m"]  # neither later read reached the host
    types = [e.type for e in rig.events(stopped.run_id)]
    assert EventType.RUN_COMPLETED not in types
    assert types.count(EventType.RUN_ESCALATED) == 1


@pytest.mark.parametrize(
    "code", [ErrorCode.TIMEOUT_NO_EFFECT, ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, ErrorCode.HOST_WEDGED]
)
def test_units_are_read_after_a_read_timed_out(tmp_path: Path, code: ErrorCode) -> None:
    """A read that timed out on a host makes the units of its models be read again before the retry (AC45 c)."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    _open(rig, "m1")
    host = rig.host

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_m", {"model": "m1"})
        host.units["m1"] = _DIFFER
        host.script("read_m", failure(code))  # the second read times out once; a code that is retried is retried
        with contextlib.suppress(ToolFailed):  # a code that is not retried ends the step; the next reads units first
            await ctx.tool("read_m", {"model": "m1"})
        await ctx.tool("read_m", {"model": "m1"})
        return []

    stopped = asyncio.run(rig.engine(flow(body)).start(request()))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "units_mismatch"
    assert [entry.tool for entry in host.ledger] == ["read_m", "read_m"]  # no retry after the changed units


@pytest.mark.parametrize("units_ok", [True, False])
def test_units_are_read_after_a_timeout_before_reconciliation(tmp_path: Path, units_ok: bool) -> None:
    """A write that timed out is reconciled only after the units of its host's models are read again (AC45 c)."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    _open(rig, "m1")
    rig.host.script("write_m", failure(ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, "the reply was lost"))
    host = rig.host

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_m", {"model": "m1"})
        host.units["m1"] = host.units["m1"] if units_ok else _DIFFER
        await ctx.tool("write_m", {"model": "m1"})
        return []

    if units_ok:
        done = asyncio.run(rig.engine(flow(body)).start(request()))
        assert done.status is RunStatus.COMPLETED
        reads = [i for i, line in enumerate(rig.log) if line == "host.read_units"]
        assert len(reads) == 2
        assert reads[1] < rig.log.index("tool.reconcile")  # the units are read again before the reconciliation
        assert "1~host.units.m1" in [e.path for e in rig.events(done.run_id) if e.type is EventType.STEP_STARTED]
        return
    stopped = asyncio.run(rig.engine(flow(body)).start(request()))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "units_mismatch"
    assert "tool.reconcile" not in rig.log  # the write stays in flight for the next resume
    run_id = stopped.run_id
    assert [e.attempt for e in rig.events(run_id) if e.path == "1" and e.type is EventType.STEP_STARTED] == [1]
    assert not [e for e in rig.events(run_id) if e.path == "1" and e.type is EventType.STEP_RECONCILED]


@pytest.mark.parametrize("outcome", ["unknown", "wedged", "raised"])
def test_units_steps_after_a_reconnect_and_a_write_timeout_have_distinct_keys(tmp_path: Path, outcome: str) -> None:
    """The units read at the reconnect and the one after the write timed out are two steps with their own keys."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    _open(rig, "m1")
    host = rig.host
    scripted: dict[str, Any] = {
        "unknown": failure(ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, "the reply was lost"),
        "wedged": failure(ErrorCode.HOST_WEDGED, "the host does not answer"),
        "raised": Raise(TimeoutError("the call timed out")),
    }
    host.script("write_m", scripted[outcome])

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_m", {"model": "m1"})
        host.epochs["csi"] += 1  # the session changed before the write
        await ctx.tool("write_m", {"model": "m1"})
        return []

    done = asyncio.run(rig.engine(flow(body)).start(request()))
    assert done.status is RunStatus.COMPLETED
    started = [(e.path, e.attempt) for e in rig.events(done.run_id) if e.type is EventType.STEP_STARTED]
    assert len(started) == len(set(started))  # one view per path and attempt (spec 0001 section 6)
    units = [key for key in started if key[0] == "1~host.units.m1"]
    assert len(units) == 2  # 4.6 #9 (c): after the new session, and again after the timeout, before the reconciliation


class _Opening(Host):
    """The rig's host where the tool `open_m` opens the model `m9`."""

    async def call(self, tool: str, args: Mapping[str, Any], *, op_id: str, model: str | None) -> Any:
        """As the rig's host; `open_m` then opens its model."""
        reply = await super().call(tool, args, op_id=op_id, model=model)
        if tool == "open_m":
            opened = HostInstance(instance_id="i-9", pid=9, process_started_at=self._clock.now(), program="csi")
            self.add_model("m9", opened)
        return reply


def test_model_not_open_refused(tmp_path: Path) -> None:
    """A step addressed to a model no instance holds is refused before its step and its host call (spec 4.8, Q29)."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    _open(rig, "m1")

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_m", {"model": "m9"})
        return []

    with pytest.raises(ContractError) as refused:
        asyncio.run(rig.engine(flow(body)).start(request()))
    detail = refused.value.detail
    assert (detail.code, detail.precondition) == (ErrorCode.PRECONDITION_FAILED, Precondition.model_open)
    assert "m9" in detail.message
    assert rig.host.ledger == []
    (run_id,) = rig.run_ids()
    assert _trail(rig, run_id, EventType.MODEL_BOUND, EventType.STEP_STARTED) == []
    assert rig.log.count("host.locate") == 1

    base = make_rig(tmp_path / "open")
    host = _Opening(base.ids, base.clock, base.workspace.root / "runs")
    _tools(host)
    host._tools["open_m"] = ToolInfo(name="open_m", effect="write", action="open", host_key="csi", model_param="model")
    opening = replace(base, host=host)

    async def open_then_read(ctx: Any) -> list[str]:
        await ctx.tool("open_m", {"model": "m9"})  # the model is not open before this step: it is bound after it
        await ctx.tool("read_m", {"model": "m9"})
        return []

    host.script("read_c", failure(ErrorCode.HOST_BUSY))  # the run stops at its last step

    async def open_read_stop(ctx: Any) -> list[str]:
        await open_then_read(ctx)
        await ctx.tool("read_c", {"n": 0})
        return []

    done = asyncio.run(opening.engine(flow(open_read_stop)).start(request()))
    assert done.status is RunStatus.NEEDS_ENGINEER
    assert _trail(opening, done.run_id, EventType.MODEL_BOUND, EventType.STEP_STARTED)[:5] == [
        ("step_started", "0"), ("model_bound", None), ("step_started", "0~post.units.m9"),
        ("step_started", "1~pre.check_model.m9"), ("step_started", "1"),
    ]  # fmt: skip  # the open step wrote the model, so the read that follows is preceded by its check
    (bound,) = [e.payload for e in opening.events(done.run_id) if isinstance(e.payload, ev.ModelBound)]
    assert (bound.model_key, bound.instance_id, bound.reason) == ("m9", "i-9", "first_use")
    again = asyncio.run(opening.engine(flow(open_read_stop)).resume(done.run_id))
    assert again.status is RunStatus.COMPLETED  # the recorded `~post.units` step is replayed, not diverged from
    started = [e.path for e in opening.events(done.run_id) if e.type is EventType.STEP_STARTED]
    assert started.count("0~post.units.m9") == 1
    assert opening.log.count("host.locate") == 1  # the binding is journaled: a resume does not locate the model again


def test_open_tool_that_leaves_nothing_open_binds_nothing(tmp_path: Path) -> None:
    """After an `open` tool no instance holds the model: nothing is bound, and the next step on it is refused."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    rig.host._tools["open_m"] = ToolInfo(
        name="open_m", effect="read", action="open", host_key="csi", model_param="model"
    )

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("open_m", {"model": "m9"})
        await ctx.tool("read_m", {"model": "m9"})
        return []

    with pytest.raises(ContractError) as refused:
        asyncio.run(rig.engine(flow(body)).start(request()))
    assert refused.value.detail.precondition is Precondition.model_open
    (run_id,) = rig.run_ids()
    assert _trail(rig, run_id, EventType.MODEL_BOUND, EventType.STEP_STARTED) == [("step_started", "0")]
    assert rig.log.count("host.locate") == 2  # after the open tool, and before the step that was refused


def test_reconnect_reads_the_units_of_that_hosts_models_only(tmp_path: Path) -> None:
    """A new session of the host `other` does not make the engine read the units of m1, which `csi` holds (4.6 #9)."""
    rig = make_rig(tmp_path)
    _tools(rig.host)
    _open(rig, "m1")
    rig.host._tools["read_other"] = ToolInfo(name="read_other", effect="read", action="plain", host_key="other")
    host = rig.host

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_m", {"model": "m1"})
        await ctx.tool("read_other", {"n": 1})
        host.epochs["other"] += 1
        await ctx.tool("read_other", {"n": 2})
        return []

    done = asyncio.run(rig.engine(flow(body)).start(request()))
    assert done.status is RunStatus.COMPLETED
    assert rig.log.count("host.read_units") == 1  # the first use of m1 only
    assert not [e for e in rig.events(done.run_id) if "~host." in (e.path or "")]


def _types(rig: Any, run_id: str) -> list[EventType]:
    return [e.type for e in rig.events(run_id)]


def test_host_lease_and_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each host is leased before its first step and released at return; instances are journaled and closed (AC46)."""
    rig = make_rig(tmp_path / "done")
    closing = watch_closing(rig, monkeypatch)
    rig.host._tools["read_s"] = ToolInfo(name="read_s", effect="read", action="plain", host_key="safe")
    rig_instance = HostInstance(instance_id="started-1", pid=2, process_started_at=rig.clock.now(), program="csi")
    rig.host.started.append(rig_instance)  # the servers of the first step start an instance
    done = asyncio.run(rig.engine(chain([*ORIGINAL, ("read_s", {"n": 3})])).start(request()))
    assert done.status is RunStatus.COMPLETED
    leases = [line for line in rig.log if line == "host.acquire"]
    assert len(leases) == 2  # one lease for each host (csi, safe), however many steps it serves
    assert rig.log.index("host.acquire") < rig.log.index("tool.call")  # before the first step on the first host
    assert rig.log.count("host.release") == 2
    assert rig.host.leases == {}  # released when the engine returned
    assert rig.log.count("host.started_instances") == 4  # after every live step, none for the inserted steps
    started = [(e.path, e.payload) for e in rig.events(done.run_id) if isinstance(e.payload, ev.HostStarted)]
    assert [p for _, p in started] == [ev.HostStarted(host_key="csi", **rig_instance.model_dump(mode="json"))]
    first = _types(rig, done.run_id).index(EventType.HOST_STARTED)
    assert rig.events(done.run_id)[first - 1].path == "0"  # right after the step that started it, before the next
    assert rig.host.closed == [rig_instance]  # exactly the journaled instances
    assert len(closing) == 1  # one host key has instances
    assert closing[0][-1] is EventType.RUN_COMPLETED  # after `run_completed` is appended

    refused = make_rig(tmp_path / "refused")  # a refused lease raises HOST_LOCKED before any step or call on the host
    held = HostLease(host_key="csi", lease_id="other-run")
    refused.host.leases["csi"] = held
    with pytest.raises(ContractError) as locked:
        asyncio.run(refused.engine(chain(ORIGINAL)).start(request()))
    assert locked.value.detail.code is ErrorCode.HOST_LOCKED
    assert refused.host.ledger == []
    assert refused.host.leases == {"csi": held}  # the other holder's lease is not touched
    assert not [line for line in refused.log if line in ("host.close_started", "host.release")]
    assert EventType.RUN_COMPLETED not in _types(refused, refused.run_ids()[0])
    _stops_without_closing(tmp_path, monkeypatch)


async def _two_reads(ctx: Any) -> list[str]:
    refs = await ctx.parallel(ctx.tool("read_a", {"n": 0}), ctx.tool("read_c", {"n": 1}))
    return [r.ref.ref for r in refs]


def _pauses(rig: Any) -> Body:
    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_a", {"n": 0})
        await need_approval(rig.approvals, "apr_x")  # never answered: the run pauses
        return []

    return body


async def _escalates(ctx: Any) -> list[str]:
    await ctx.tool("read_a", {"n": 0})
    await ctx.escalate("an engineer must look", [])
    return []


def _stops_without_closing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A pause or an escalation releases the lease but closes nothing; parallel steps share one lease (AC46)."""
    rig = make_rig(tmp_path / "parallel")
    asyncio.run(rig.engine(flow(_two_reads)).start(request()))  # both children want the host at once
    assert rig.log.count("host.acquire") == 1
    assert rig.host.leases == {}
    for name in ("paused", "escalated"):
        rig = make_rig(tmp_path / name)
        rig.host.started.append(
            HostInstance(instance_id="started-1", pid=2, process_started_at=rig.clock.now(), program="csi")
        )
        closing = watch_closing(rig, monkeypatch)
        stopped = asyncio.run(rig.engine(flow(_pauses(rig) if name == "paused" else _escalates)).start(request()))
        assert stopped.status in (RunStatus.PAUSED, RunStatus.NEEDS_ENGINEER)
        assert EventType.HOST_STARTED in _types(rig, stopped.run_id)  # the instance is journaled for a later resume
        assert (closing, rig.host.closed, rig.host.leases) == ([], [], {})
        assert "host.close_started" not in rig.log
        assert rig.log.count("host.release") == 1


def test_host_started_when_a_read_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An instance started during a read whose port raised is journaled, so the run end can close it (4.6 #10)."""
    rig = make_rig(tmp_path)
    closing = watch_closing(rig, monkeypatch)
    instance = HostInstance(instance_id="started-1", pid=2, process_started_at=rig.clock.now(), program="csi")
    rig.host.started.append(instance)  # the servers started it during the call that then raised
    rig.host.script("read_a", Raise(ConnectionResetError("the connection dropped")))

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_a", {"n": 0})
        return []

    with pytest.raises(ConnectionResetError):
        asyncio.run(rig.engine(flow(body)).start(request()))
    run_id = rig.run_ids()[0]
    started = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.HostStarted)]
    assert started == [ev.HostStarted(host_key="csi", **instance.model_dump(mode="json"))]
    assert rig.log.count("host.release") == 1  # the lease is released as the raise leaves the run
    assert closing == []  # a run that did not end closes nothing; the journal lets a later resume do it
