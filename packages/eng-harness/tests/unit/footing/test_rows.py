"""Copy calc refusals and stored traces through CalcPort (spec 0010 AC35, §4.4.7)."""

import json
from pathlib import Path

import pytest
from eng_contract.envelope import FailureEnvelope, Provenance, SuccessEnvelope
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore
from eng_contract.trace import Trace, TraceInput, TraceStep
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
    extra = store.put("harness.footing_dims/1", dims | {"footings": dims["footings"][1:]}, producer).result_id
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
    assert out.error.field == field
    assert out.error.message == "result kind harness.footing_subjects/1 is not accepted"
    assert out.error.expected == {"kinds": ["harness.footing_dims/1"]}
    assert out.error.received == "harness.footing_subjects/1"
    assert set(tmp_path.rglob("res_*.json")) == before


@pytest.mark.parametrize("missing", ["absent-footing", ""], ids=["unknown", "empty-string"])
def test_missing_id_refused(
    rows_call: tuple[HarnessCalcPort, dict[str, JsonValue], str], tmp_path: Path, missing: str
) -> None:
    port, args, _ = rows_call
    before = set(tmp_path.rglob("res_*.json"))
    out = port.run(CALC_ID, args | {"ids": ["J1", missing, "another-missing-footing"]})
    assert isinstance(out, FailureEnvelope), out
    assert (out.error.code, out.error.field) == (ErrorCode.INVALID_ARGUMENT, "ids"), out.error
    assert out.error.message == f"requested footing id {missing} is in neither input"
    assert out.error.expected is None
    assert out.error.received == missing
    assert set(tmp_path.rglob("res_*.json")) == before


@pytest.mark.parametrize(
    ("requested", "selection"),
    [pytest.param(["J2", "J1", "J2"], "J1=base; J2=extra", id="mixed"), pytest.param([], "", id="empty")],
)
def test_stored_trace_records_exact_selection(
    rows_call: tuple[HarnessCalcPort, dict[str, JsonValue], str],
    store: ResultStore,
    requested: list[str],
    selection: str,
) -> None:
    port, args, _ = rows_call
    base, extra = args["base"], args["extra"]
    assert isinstance(base, dict)
    assert isinstance(extra, dict)
    out = port.run(CALC_ID, args | {"ids": requested})
    assert isinstance(out, SuccessEnvelope), out
    trace = Trace.model_validate(store.payload(out.result_id)["trace"])
    assert trace.inputs == [
        TraceInput(name="base", value=["J1", "J2"], ref=str(base["$ref"])),
        TraceInput(name="extra", value=["J2"], ref=str(extra["$ref"])),
        TraceInput(name="ids", value=list(requested)),
    ]
    assert trace.constants == []
    assert trace.steps == [
        TraceStep(
            name="selected_rows",
            value=selection,
            formula="Keep requested ids in sorted order, using extra where present and base otherwise",
            source="eng-harness spec 0010 §4.4.7",
            uses=["base", "extra", "ids"],
        )
    ]
    assert trace.outputs == ["selected_rows"]
