"""Copy calc golden cases and stored provenance (spec 0010 AC35, §4.4.7)."""

import json
from typing import Any

import pytest
from eng_contract.envelope import Provenance, RefInput, SuccessEnvelope
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore
from pydantic import Field

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness.calcs import REGISTRY
from eng_harness.kinds.calcs import CalcPayload
from eng_harness.ports import RunClass

from . import GOLDEN_DIR, FootingGoldenCase


class RowsGoldenCase(FootingGoldenCase):
    method_ref: str = Field(pattern=r"^§4\.4\.7\s+\S")
    refs: dict[str, str] = Field(default_factory=dict)  # CalcPort allocates the references during the test.


@pytest.mark.parametrize("name", ["dims", "design", "status", "subjects"])
def test_golden_cases(name: str, store: ResultStore, clock: FixedClock, ids: SeededIdSource) -> None:
    case = RowsGoldenCase.model_validate_json((GOLDEN_DIR / f"rows-{name}.json").read_bytes())
    template: dict[str, Any] = json.loads(
        (GOLDEN_DIR.parent.parent / "kinds" / "footing" / f"{name}.json").read_bytes()
    )
    metadata = {key: template[key] for key in CalcPayload.model_fields}
    kind = f"harness.footing_{name}/1"
    calc_id = f"harness.footing_rows_{name}"
    producer = Provenance(tool="fixture/footing", tool_version="1", inputs={}, started_at=clock.now(), duration_ms=0)
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(REGISTRY, approvals, store, CalcSettings(max_items=1000), RunClass.TRIAL, clock, ids)
    sources = {
        key: store.put(kind, metadata | case.input[key], producer).result_id
        for key in ("base", "extra", "later")
        if key in case.input
    }
    base = sources["base"]
    for extra_key, ids_key in [("extra", "ids"), ("later", "later_ids")]:
        if extra_key not in sources:
            break
        extra = sources[extra_key]
        out = port.run(calc_id, {"base": {"$ref": base}, "extra": {"$ref": extra}, "ids": case.input[ids_key]})
        assert isinstance(out, SuccessEnvelope), out
        assert out.kind == kind
        record = store.get(out.result_id)
        assert record.complete
        assert set(record.parents) == {base, extra}
        assert record.producer.tool == "harness"
        assert record.producer.inputs == {"base": RefInput(ref=base), "extra": RefInput(ref=extra)}
        payload = store.payload(out.result_id)
        built = CalcPayload.model_validate({key: payload[key] for key in CalcPayload.model_fields})
        assert (built.calc.id, built.calc.version, built.calc.status, built.draft) == (calc_id, 1, "draft", True)
        assert {base, extra} <= {entry.ref for entry in built.trace.inputs}
        assert any("4.4.7" in step.source for step in built.trace.steps)
        base = out.result_id
    assert {k: v for k, v in store.payload(base).items() if k not in metadata} == case.expected
