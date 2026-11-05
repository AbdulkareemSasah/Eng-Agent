"""The calc step through the real engine and the real CalcPort (plan 0003 T5; spec 0003 AC17)."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from eng_contract.envelope import Provenance, SuccessEnvelope
from eng_contract.store import ResultStore
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from workflows.calc_test_blocks import calc_step, engine
from workflows.rig import make_rig, request

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness.calc import CalcRegistry
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
    stored = rig.store.get(done[0].result.ref)  # type: ignore[union-attr]  # B-144: a calc step has a result
    assert stored.kind == fx.OUTPUT_KIND
    assert stored.parents == [source.result_id]
    assert rig.store.payload(stored.result_id)["total"] == 502.5
    finished = rig.events(outcome.run_id)[-1]
    assert finished.type is EventType.RUN_COMPLETED
    assert isinstance(finished.payload, ev.RunCompleted)
    assert finished.payload.draft is True
