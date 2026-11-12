"""The calc step through the real engine and the real CalcPort (plan 0003 T5, T8b; spec 0003 AC17, AC48)."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import new_model_id, new_result_id
from eng_contract.store import ResultStore
from pydantic import JsonValue
from workflows.calc_test_blocks import calc_step, engine, older_revision
from workflows.chain import ChainOutput
from workflows.rig import Rig, make_rig, request

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness.calc import CalcRegistry
from eng_harness.calcs import REGISTRY
from eng_harness.engine import RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import RunClass

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


def _frame(section: str) -> dict[str, Any]:
    point = {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0}
    return {
        "id": "F1",
        "kind": "column",
        "section": section,
        "i": point,
        "j": point | {"z_mm": 3000.0},
        "rotation_deg": 0.0,
    }


def _envelope(rig: Rig, result_id: str, kind: str, producer: Provenance) -> SuccessEnvelope:
    return SuccessEnvelope(
        contract="eng-contract/1", ok=True, result_id=result_id, kind=kind, summary={}, complete=True,
        provenance=producer,
    )  # fmt: skip


def _older_rig(root: Path) -> tuple[Rig, HarnessCalcPort, str]:
    """Frames read at revision 1, a write that makes the model revision 2, frames read again (section S1 -> S2)."""
    rig = make_rig(root, run_class=RunClass.TRIAL)
    model_id = new_model_id(rig.ids)

    def producer(revision: int, tool: str = "fake-host/read") -> Provenance:
        host = HostInfo(program="csi", version="1", model_id=model_id, model_revision=revision)
        return Provenance(tool=tool, tool_version="1", host=host, inputs={}, started_at=rig.clock.now(), duration_ms=0)

    kind = "model.frame_placements/1"
    first = rig.store.put(kind, {"frames": [_frame("S1")]}, producer(1))
    second = rig.store.put(kind, {"frames": [_frame("S2")]}, producer(2))
    source = "engineer:synthetic@2026-01-01T00:00:00.000Z"
    units = {"length": "mm", "angle": "deg", "stress": "MPa", "unit_weight": "kN/m3", "line_load": "kN/m",
             "area_load": "kPa", "ratio": "1"}  # fmt: skip
    fields: dict[str, JsonValue] = {
        f"compare.{name}": {"value": 1.0, "unit": unit, "source": source, "confirmed": True, "citation": None}
        for name, unit in units.items()
    }
    plain = Provenance(tool="harness", tool_version="t", inputs={}, started_at=rig.clock.now(), duration_ms=0)
    basis = rig.store.put("basis.design_basis/1", {"template": None, "fields": fields}, plain)
    rig.host.script("read_a", _envelope(rig, first.result_id, kind, producer(1)))
    rig.host.script(
        "write_b", _envelope(rig, new_result_id(rig.ids), "harness.run_output/1", producer(2, "fake-host/write"))
    )
    rig.host.script("read_c", _envelope(rig, second.result_id, kind, producer(2)))
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(
        REGISTRY, approvals, rig.store, CalcSettings(max_items=100), RunClass.TRIAL, rig.clock, rig.ids
    )
    return rig, port, basis.result_id


def test_older_revision_inputs(tmp_path: Path) -> None:
    """AC48: `before` at revision n is accepted (`stale_ok`); `after` at n while the model is at n+1 is `REF_STALE`."""
    rig, port, basis_id = _older_rig(tmp_path / "ok")
    info = port.describe("harness.model_diff")
    assert (info.ref_rules["before_frames"].stale_ok, info.ref_rules["after_frames"].stale_ok) == (True, False)
    assert info.ref_rules["basis"].stale_ok is False

    outcome = asyncio.run(
        engine(rig, port, older_revision(basis_id, stale_after=False)).start(request(run_class=RunClass.TRIAL))
    )

    assert outcome.status is RunStatus.COMPLETED
    assert isinstance(outcome.output, ChainOutput)
    report: Any = rig.store.payload(outcome.output.refs[0])
    assert (report["before"]["model_revision"], report["after"]["model_revision"]) == (1, 2)
    assert [(c["key"], c["properties"][0]["pointer"]) for c in report["changes"]] == [(["F1"], "/section")]
    assert rig.log.count("calc.run") == 1

    stale, stale_port, stale_basis = _older_rig(tmp_path / "stale")
    with pytest.raises(ContractError) as caught:
        asyncio.run(
            engine(stale, stale_port, older_revision(stale_basis, stale_after=True)).start(
                request(run_class=RunClass.TRIAL)
            )
        )
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.REF_STALE, "after_frames")
    assert "calc.run" not in stale.log  # the port, the only writer of a calc result, was never called
