"""The calc step through the real engine and the real CalcPort (plan 0003 T5, T8; spec 0003 AC17, AC48)."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource, new_model_id, new_result_id
from eng_contract.refs import Ref
from eng_contract.store import ResultStore
from pydantic import JsonValue
from workflows.calc_test_blocks import calc_step, diff_step, engine
from workflows.chain import ChainOutput
from workflows.rig import make_rig, request

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import CalcRegistry
from eng_harness.calcs import REGISTRY
from eng_harness.engine import RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import RunClass, ToolInfo

HASH = "cd" * 32
_PATH = Path(__file__).resolve().parents[1] / "data" / "calcs" / "port_calcs.py"


def _fixtures() -> ModuleType:
    spec = importlib.util.spec_from_file_location("port_calcs", _PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["port_calcs"] = module
    spec.loader.exec_module(module)
    return module


def test_calc_step_end_to_end(tmp_path: Path) -> None:
    fx = _fixtures()
    rig = make_rig(tmp_path, run_class=RunClass.TRIAL)
    kinds = fx.kinds()
    rig.store = ResultStore(rig.workspace, kinds, rig.ids, rig.clock)
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=rig.clock.now(), duration_ms=0)
    source = rig.store.put(fx.SOURCE_KIND, {"value": {"span_mm": 500.0}}, producer)
    rig.host.script(
        "read_a",
        SuccessEnvelope(
            contract="eng-contract/1", ok=True, result_id=source.result_id, kind=fx.SOURCE_KIND, summary={},
            complete=True, provenance=producer,
        ),
    )  # fmt: skip
    registry = CalcRegistry(kinds, [fx.port_sum], hasher=lambda _: HASH)
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(
        registry, approvals, rig.store, CalcSettings(max_items=100), RunClass.TRIAL, rig.clock, rig.ids
    )

    outcome = asyncio.run(engine(rig, port, calc_step(fx.CALC_ID, 2.5)).start(request(run_class=RunClass.TRIAL)))

    assert outcome.status is RunStatus.COMPLETED
    done = [e.payload for e in rig.events(outcome.run_id) if isinstance(e.payload, ev.StepCompleted) and e.payload.calc]
    assert [p.calc for p in done] == [ev.CalcRef(id=fx.CALC_ID, version="2", content_sha256=HASH, status="draft")]
    result = done[0].result
    assert result is not None
    assert isinstance(outcome.output, ChainOutput)
    assert outcome.output.refs[1] == repr(502.5)
    stored = rig.store.get(result.ref)
    assert stored.kind == fx.OUTPUT_KIND
    assert stored.parents == [source.result_id]
    assert rig.store.payload(stored.result_id)["total"] == 502.5
    finished = rig.events(outcome.run_id)[-1]
    assert finished.type is EventType.RUN_COMPLETED
    assert isinstance(finished.payload, ev.RunCompleted)
    assert finished.payload.draft is True


def _basis_payload() -> dict[str, Any]:
    return {
        "template": {"name": "synthetic", "version": "0.1.0", "sha256": "a" * 64},
        "fields": {
            path: {
                "value": 1.0,
                "unit": unit,
                "source": "engineer:synthetic@2026-01-01T00:00:00.000Z",
                "confirmed": True,
                "citation": None,
            }
            for path, unit in (
                ("compare.length", "mm"),
                ("compare.angle", "deg"),
                ("compare.stress", "MPa"),
                ("compare.unit_weight", "kN/m3"),
                ("compare.line_load", "kN/m"),
                ("compare.area_load", "kPa"),
                ("compare.ratio", "1"),
            )
        },
    }


def test_older_revision_inputs(tmp_path: Path) -> None:
    """AC48: stale `before_*` resolves; stale `after_*` is `REF_STALE` before the port runs."""
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"harness", clock)
    rig = make_rig(tmp_path, run_class=RunClass.TRIAL)
    rig.store = ResultStore(rig.workspace, HARNESS_KINDS, ids, clock)
    rig.host._tools["write_m"] = ToolInfo(
        name="write_m", effect="write", action="plain", host_key="csi", model_param="model"
    )
    model_id = new_model_id(ids)
    host1 = HostInfo(program="csi", version="1", model_id=model_id, model_revision=1)
    producer1 = Provenance(
        tool="fake-host/read", tool_version="1", host=host1, inputs={}, started_at=clock.now(), duration_ms=0
    )
    frames = {
        "frames": [
            {
                "id": "F1",
                "kind": "column",
                "section": "S1",
                "i": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0},
                "j": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 3000.0},
                "rotation_deg": 0.0,
            }
        ]
    }
    frames_value = cast(dict[str, JsonValue], frames)
    before_id = rig.store.put("model.frame_placements/1", frames_value, producer1).result_id
    host2 = host1.model_copy(update={"model_revision": 2})
    after_id = rig.store.put(
        "model.frame_placements/1",
        frames_value,
        producer1.model_copy(update={"host": host2}),
    ).result_id
    basis_id = rig.store.put(
        "basis.design_basis/1",
        _basis_payload(),
        Provenance(tool="harness", tool_version="t", inputs={}, started_at=clock.now(), duration_ms=0),
    ).result_id
    rig.host.script(
        "write_m",
        SuccessEnvelope(
            contract="eng-contract/1",
            ok=True,
            result_id=new_result_id(ids),
            kind="model.frame_placements/1",
            summary={},
            complete=True,
            provenance=producer1.model_copy(update={"host": host2}),
        ),
    )
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(REGISTRY, approvals, rig.store, CalcSettings(max_items=500), RunClass.TRIAL, clock, ids)

    async def ok(ctx: Any) -> list[str]:
        await ctx.tool("write_m", {"model": "m1"})
        result = await ctx.calc(
            "harness.model_diff",
            {
                "before_frames": Ref.model_validate({"$ref": before_id}),
                "after_frames": Ref.model_validate({"$ref": after_id}),
                "basis": Ref.model_validate({"$ref": basis_id}),
            },
        )
        return [result.ref.ref]

    outcome = asyncio.run(engine(rig, port, diff_step(ok)).start(request(run_class=RunClass.TRIAL)))
    assert outcome.status is RunStatus.COMPLETED

    from eng_contract.refs import resolve_ref

    info = port.describe("harness.model_diff")
    assert info.ref_rules["before_frames"].stale_ok is True
    assert info.ref_rules["after_frames"].stale_ok is False

    def revision(model: str) -> int | None:
        return 2 if model == model_id else None

    resolve_ref(
        Ref.model_validate({"$ref": before_id}),
        info.ref_rules["before_frames"],
        rig.store,
        revision,
    )
    with pytest.raises(ContractError) as caught:
        resolve_ref(
            Ref.model_validate({"$ref": before_id}),
            info.ref_rules["after_frames"],
            rig.store,
            revision,
        )
    assert caught.value.detail.code is ErrorCode.REF_STALE
