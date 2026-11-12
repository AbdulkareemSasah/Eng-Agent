"""Invariants 1, 2, 3 and 7 through the engine (plan 0001 T12; spec 0001 4.6, AC37, AC38, AC39, AC43).

A write is checked before the next read of that model, any calc and the block's return. An engineering parameter
rejects a literal before the port call. A stale reference is refused unless the calc's rule says `stale_ok`. An
analysis or design tool is preceded by a save.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import pytest
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import new_model_id, new_result_id
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref, RefRule
from fakes.ports import failure
from workflows.chain import ChainInput, ChainOutput
from workflows.ctx_flows import flow, need_approval, success
from workflows.rig import make_rig, request

from eng_harness.calc import CalcStatus
from eng_harness.engine import RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import CalcInfo, HostInstance, ToolInfo

_SHA = "ab" * 32
Body = Callable[[Any], Awaitable[Sequence[str]]]


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
    assert enforced == [ev.CheckEnforced(invariant=1, model_key="m1", outcome="pass")]
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


def test_basis_incomplete_refused(tmp_path: Path) -> None:
    """A required basis field that is missing or unconfirmed refuses the run before any port call (AC41)."""
    from eng_contract.kinds.basis import BasisField, DesignBasis

    from eng_harness.block import workflow
    from eng_harness.errors import HarnessCode, RunRefused
    from eng_harness.ports import LoadedBasis

    ref = "res_" + "0" * 26
    basis = LoadedBasis(result_id=ref, basis=DesignBasis(template=None, fields={}))

    @workflow(name="needs_basis", version=1, description="x", required_basis=("limits.drift_ratio",))
    async def needs_basis(ctx: Any, inp: ChainInput) -> ChainOutput:
        await ctx.tool("read_a", {"n": 0})
        return ChainOutput(refs=[])

    workflow_def = needs_basis
    rig = make_rig(tmp_path, bases={ref: basis})
    with pytest.raises(RunRefused) as refused:
        asyncio.run(rig.engine(workflow_def).start(request(workflow="needs_basis", basis_ref=ref)))
    assert refused.value.code is HarnessCode.BASIS_INCOMPLETE
    assert refused.value.evidence == ("limits.drift_ratio",)
    assert rig.run_ids() == []
    assert rig.host.ledger == []


def test_server_check(tmp_path: Path) -> None:
    """A failing server preflight refuses the run at start and at resume (AC44)."""
    from eng_harness.block import workflow
    from eng_harness.errors import HarnessCode, RunRefused
    from eng_harness.ports import ServerCheck

    @workflow(name="checked", version=1, description="x", min_server_builds={"csi": "build-1"})
    async def checked(ctx: Any, inp: ChainInput) -> ChainOutput:
        return ChainOutput(refs=[(await ctx.tool("read_a", {"n": 0})).ref.ref])

    fail = ServerCheck(
        server="csi", build="old", min_build="build-1", fingerprint="a", expected_fingerprint="b", ok=False, reason="old"
    )
    rig = make_rig(tmp_path)
    rig.host.preflight_checks = [fail]
    with pytest.raises(RunRefused) as start:
        asyncio.run(rig.engine(checked).start(request(workflow="checked")))
    assert start.value.code is HarnessCode.SERVER_CHECK_FAILED
    assert rig.run_ids() == []


def test_units_after_reconnect(tmp_path: Path) -> None:
    """Differing units stop the run before the next step on that host (AC45)."""
    from eng_harness.ports import HostInstance, UnitsState

    inst = HostInstance(instance_id="csi-1", pid=1, process_started_at="2026-01-01T00:00:00.000Z", program="csi")
    rig = make_rig(tmp_path)
    rig.host.add_model("m1", inst)
    rig.host.units["m1"] = UnitsState(loaded=True, ok=False, present="b", expected="a")

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("write_b", {"n": 0, "model": "m1"})
        return []

    workflow = flow(body, name="units")
    with pytest.raises(ContractError) as failed:
        asyncio.run(rig.engine(workflow).start(request(workflow="units")))
    assert failed.value.detail.code is ErrorCode.PRECONDITION_FAILED
    assert failed.value.detail.precondition is not None
    assert failed.value.detail.precondition.value == "units_verified"
    assert rig.host.ledger == []


def test_host_lease_and_close(tmp_path: Path) -> None:
    """The engine acquires a host lease before the first step and closes instances only at run end (AC46)."""
    from eng_harness.ports import HostInstance

    inst = HostInstance(instance_id="csi-1", pid=9, process_started_at="2026-01-01T00:00:00.000Z", program="csi")
    rig = make_rig(tmp_path)
    rig.host.instances["csi"].append(inst)

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("read_a", {"n": 0})
        await need_approval(rig.approvals, "apr_1")
        return [(await ctx.tool("read_c", {"n": 1})).ref.ref]

    workflow = flow(body, name="lease")
    paused = asyncio.run(rig.engine(workflow).start(request(workflow="lease")))
    assert paused.status is RunStatus.PAUSED
    assert "host.acquire" in rig.log
    assert "host.close_started" not in rig.log
    assert any(e.type is EventType.HOST_STARTED for e in rig.events(paused.run_id))
    from workflows.ctx_flows import answer

    rig.approvals.script("apr_1", answer("apr_1"))
    mark = len(rig.log)
    done = asyncio.run(rig.engine(workflow).resume(paused.run_id))
    assert done.status is RunStatus.COMPLETED
    assert any(e.type is EventType.HOST_STARTED for e in rig.events(done.run_id))
    assert rig.log.count("host.close_started") == 1
    assert rig.host.closed == [inst]
    assert "host.close_started" not in rig.log[:mark]
