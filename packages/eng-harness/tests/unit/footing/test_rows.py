"""Copy calc refusals through CalcPort (spec 0010 AC35, §4.4.7 K1)."""

import json
from pathlib import Path

import pytest
from eng_contract.envelope import FailureEnvelope, Provenance
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness.calcs import REGISTRY
from eng_harness.ports import RunClass

CALC_ID = "harness.footing_rows_dims"
DATA = Path(__file__).resolve().parents[2] / "data" / "kinds" / "footing"


@pytest.fixture
def rows_call(
    store: ResultStore, clock: FixedClock, ids: SeededIdSource
) -> tuple[HarnessCalcPort, dict[str, JsonValue], str]:
    producer = Provenance(tool="fixture/footing", tool_version="1", inputs={}, started_at=clock.now(), duration_ms=0)
    dims = json.loads((DATA / "dims.json").read_bytes())
    subjects = json.loads((DATA / "subjects.json").read_bytes())
    base = store.put("harness.footing_dims/1", dims, producer).result_id
    extra = store.put("harness.footing_dims/1", dims, producer).result_id
    wrong = store.put("harness.footing_subjects/1", subjects, producer).result_id
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(REGISTRY, approvals, store, CalcSettings(max_items=1000), RunClass.TRIAL, clock, ids)
    return port, {"base": {"$ref": base}, "extra": {"$ref": extra}, "ids": ["J1"]}, wrong


@pytest.mark.parametrize("field", ["base", "extra"])
def test_wrong_kind_refused(
    rows_call: tuple[HarnessCalcPort, dict[str, JsonValue], str], tmp_path: Path, field: str
) -> None:
    port, args, wrong = rows_call
    before = set(tmp_path.rglob("res_*.json"))
    out = port.run(CALC_ID, args | {field: {"$ref": wrong}})
    assert isinstance(out, FailureEnvelope), out
    assert out.error.code is ErrorCode.REF_KIND_MISMATCH, out.error
    assert set(tmp_path.rglob("res_*.json")) == before


def test_missing_id_refused(rows_call: tuple[HarnessCalcPort, dict[str, JsonValue], str], tmp_path: Path) -> None:
    port, args, _ = rows_call
    missing = "absent-footing"
    before = set(tmp_path.rglob("res_*.json"))
    out = port.run(CALC_ID, args | {"ids": ["J1", missing]})
    assert isinstance(out, FailureEnvelope), out
    assert (out.error.code, out.error.field) == (ErrorCode.INVALID_ARGUMENT, "ids"), out.error
    assert missing in out.error.message
    assert out.error.received == missing
    assert set(tmp_path.rglob("res_*.json")) == before
