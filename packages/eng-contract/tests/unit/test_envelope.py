"""Provenance and envelopes (plan T7; spec 4.2.2, 4.2.5; AC7, AC8, AC9, AC11)."""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from eng_contract.canonical import canonical_json
from eng_contract.envelope import (
    INLINE_DATA_LIMIT_BYTES,
    SUMMARY_LIMIT_BYTES,
    Envelope,
    FailureEnvelope,
    FileSource,
    HostInfo,
    LiteralInput,
    Provenance,
    RefInput,
    SuccessEnvelope,
    make_failure,
    make_success,
)
from eng_contract.errors import ContractError, ContractWarning, ErrorCode, ErrorDetail, WarningCode
from eng_contract.records import ResultRecord

RID = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
MID = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"
TS = "2026-01-02T03:04:05.678Z"
SHA = "a" * 64


def prov(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tool": "eng-contract/probe",
        "tool_version": "0.1.0",
        "inputs": {"story.height_m": {"literal": 3.2}, "load": {"ref": RID + "#/a"}},
        "started_at": TS,
        "duration_ms": 5,
    }
    return base | over


def success(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "contract": "eng-contract/1",
        "ok": True,
        "result_id": RID,
        "kind": "model.info/1",
        "summary": {"n": 1},
        "data": None,
        "complete": True,
        "provenance": prov(),
    }
    return base | over


def failure() -> dict[str, Any]:
    return {
        "contract": "eng-contract/1",
        "ok": False,
        "error": {"code": "NOT_FOUND", "message": "x", "retryable": False},
    }


def record(payload: Any = None, **over: Any) -> ResultRecord:
    base: dict[str, Any] = {
        "contract": "eng-contract/1",
        "result_id": RID,
        "kind": "model.info/1",
        "created_at": TS,
        "units": "canonical/1",
        "complete": True,
        "producer": prov(),
        "parents": [],
        "payload_sha256": SHA,
        "payload": {"k": 1} if payload is None else payload,
        "payload_file": None,
    }
    return ResultRecord.model_validate(base | over)


def test_size_limits() -> None:
    assert (SUMMARY_LIMIT_BYTES, INLINE_DATA_LIMIT_BYTES) == (4096, 16384)

    def obj(n: int) -> dict[str, Any]:
        value = {"s": "x" * n}
        assert len(canonical_json(value)) == n + 8
        return value

    SuccessEnvelope.model_validate(success(summary=obj(4096 - 8)))
    with pytest.raises(ValidationError):
        SuccessEnvelope.model_validate(success(summary=obj(4096 - 7)))
    SuccessEnvelope.model_validate(success(data=obj(16384 - 8)))
    with pytest.raises(ValidationError):
        SuccessEnvelope.model_validate(success(data=obj(16384 - 7)))


def test_make_success_inlines_small_payloads() -> None:
    small = {"s": "x" * (16384 - 8)}
    env = make_success(record(small), {"n": 1})
    assert env.data == small
    assert (env.result_id, env.kind, env.complete) == (RID, "model.info/1", True)
    assert env.provenance == record().producer

    big = {"s": "x" * (16384 - 7)}
    assert make_success(record(big), {"n": 1}).data is None
    split = record(payload=None, payload_file=RID + ".payload.json.gz")
    assert make_success(split, {}).data is None


def test_make_success_warnings_follow_completeness() -> None:
    warn = ContractWarning(code=WarningCode.PARTIAL_DATA, message="m")
    incomplete = record(complete=False)
    env = make_success(incomplete, {}, warnings=[warn])
    assert env.complete is False
    assert env.warnings[0].code is WarningCode.PARTIAL_DATA
    with pytest.raises(ValidationError):
        make_success(incomplete, {})


def test_make_failure() -> None:
    detail = ErrorDetail(code=ErrorCode.NOT_FOUND, message="x", retryable=False)
    assert make_failure(detail).error == detail
    assert make_failure(ContractError(ErrorCode.NOT_FOUND, "x")).error == detail
    assert make_failure(detail).ok is False


def test_discriminated_by_ok() -> None:
    adapter: TypeAdapter[Any] = TypeAdapter(Envelope)
    assert isinstance(adapter.validate_python(failure()), FailureEnvelope)
    assert isinstance(adapter.validate_python(success()), SuccessEnvelope)
    assert isinstance(adapter.validate_json(canonical_json(failure())), FailureEnvelope)
    for bad in ({**failure(), "ok": "false"}, {**success(), "ok": 1}, {**success(), "ok": None}):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)
    missing = success()
    del missing["ok"]
    with pytest.raises(ValidationError):
        adapter.validate_python(missing)
    with pytest.raises(ValidationError):
        adapter.validate_python([1])
    assert len(adapter.json_schema()["oneOf"]) == 2


@pytest.mark.parametrize(
    ("complete", "codes", "valid"),
    [
        (True, [], True),
        (False, ["PARTIAL_DATA"], True),
        (True, ["PARTIAL_DATA"], False),
        (False, [], False),
        (True, ["DEPRECATED"], True),
        (False, ["DEPRECATED", "PARTIAL_DATA"], True),
    ],
)
def test_partial_data_consistency(complete: bool, codes: list[str], valid: bool) -> None:
    data = success(complete=complete, warnings=[{"code": c, "message": "m"} for c in codes])
    if valid:
        SuccessEnvelope.model_validate(data)
    else:
        with pytest.raises(ValidationError):
            SuccessEnvelope.model_validate(data)


def test_contract_literal_and_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        SuccessEnvelope.model_validate(success(contract="eng-contract/2"))
    with pytest.raises(ValidationError):
        SuccessEnvelope.model_validate(success(extra=1))


@pytest.mark.parametrize("tool", ["engineer", "template", "harness", "eng-contract/probe", "a1/b_c.d-e"])
def test_provenance_tool_accepts(tool: str) -> None:
    Provenance.model_validate(prov(tool=tool))


@pytest.mark.parametrize("tool", ["", "Engineer", "pkg", "pkg/", "/x", "A/b", "pkg/b c", "x/" + "y" * 200])
def test_provenance_tool_rejects(tool: str) -> None:
    with pytest.raises(ValidationError):
        Provenance.model_validate(prov(tool=tool))


def test_provenance_inputs_host_files() -> None:
    p = Provenance.model_validate(
        prov(
            host={"program": "ETABS", "version": "1", "model_id": MID, "model_revision": 0},
            files=[{"name": "a.edb", "sha256": SHA, "size_bytes": 0}],
        )
    )
    assert isinstance(p.host, HostInfo)
    assert isinstance(p.files[0], FileSource)
    assert isinstance(p.inputs["load"], RefInput)
    assert isinstance(p.inputs["story.height_m"], LiteralInput)
    assert Provenance.model_validate(prov()).files == []
    assert Provenance.model_validate(prov(inputs={"x": {"literal": None}})).inputs["x"] == LiteralInput(literal=None)


@pytest.mark.parametrize(
    "over",
    [
        {"inputs": {"1bad": {"literal": 1}}},
        {"inputs": {"x": {"ref": "not-a-ref"}}},
        {"inputs": {"x": {"ref": RID, "literal": 1}}},
        {"inputs": {"x": {}}},
        {"duration_ms": -1},
        {"started_at": "2026-02-30T00:00:00.000Z"},
        {"files": [{"name": "dir/a.edb", "sha256": SHA, "size_bytes": 1}]},
        {"files": [{"name": "dir\\a.edb", "sha256": SHA, "size_bytes": 1}]},
        {"files": [{"name": "a.edb", "sha256": "A" * 64, "size_bytes": 1}]},
        {"host": {"program": "E", "version": "1", "model_id": RID, "model_revision": 0}},
        {"host": {"program": "E", "version": "1", "model_id": MID, "model_revision": -1}},
    ],
)
def test_provenance_rejects(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Provenance.model_validate(prov(**over))


@pytest.mark.parametrize("ref", [RID, RID + "#", RID + "#/a/0"])
def test_ref_input_accepts_whole_and_pointer_forms(ref: str) -> None:
    assert RefInput.model_validate({"ref": ref}).ref == ref
