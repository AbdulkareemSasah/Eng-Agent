"""Envelopes with limits and provenance (plan 0002 T8; spec 0002 section 4.5.3, AC19).

Limits are those of the contract (spec 4.2.5): summary at most 4096 bytes, inline data at most 16384 bytes, both
measured on canonical JSON. The reply shape is the one the Sasaah servers send: one JSON text block, `isError: true`
with `{code, message, data}` on failure (S-12 section 6).
"""

import json
from typing import Any

import pytest
from eng_contract.canonical import canonical_json
from eng_contract.envelope import HostInfo, LiteralInput, Provenance, RefInput
from eng_contract.errors import ContractError, ErrorCode, WarningCode
from eng_contract.store import ResultStore

from eng_harness.adapters import HostReply, make_envelope, parse_reply
from eng_harness.ports import ServerCheck

MODEL = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"
SHA = "c" * 64
TOOL = "sasaah-csi-mcp/csi_list_stories"
KIND = "harness.run_output/1"
HOST = HostInfo(program="ETABS", version="22.1.0", model_id=MODEL, model_revision=2)
CHECK = ServerCheck(
    server="main",
    build="0123456789ab+fedcba987654",
    min_build="",
    fingerprint=SHA,
    expected_fingerprint=SHA,
    ok=True,
    reason=None,
)


def _result(body: object, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(body)}], "isError": is_error}


def _make(store: ResultStore, value: dict[str, Any], *, truncated: bool = False, **over: Any) -> Any:
    fields: dict[str, Any] = {
        "tool": TOOL,
        "kind": KIND,
        "payload": {"value": value},
        "summary": {"count": 1},
        "reply": HostReply(data={}, truncated=truncated),
        "check": CHECK,
        "host": HOST,
        "inputs": {},
        "started_at": "2026-01-01T00:00:01.000Z",
        "duration_ms": 37,
    }
    return make_envelope(store, **(fields | over))


def test_limits_and_provenance(store: ResultStore) -> None:
    rid = store.put("harness.run_input/1", {"value": {"t_mm": 1.0}}, _producer()).result_id
    inputs = {"thickness_mm": RefInput(ref=f"{rid}#/value/t_mm"), "name": LiteralInput(literal="W1")}
    envelope = _make(store, {"stories": ["S1"]}, inputs=inputs)

    # small payload: inline data, complete, no warning; the payload is in the store in any case
    assert (envelope.ok, envelope.kind, envelope.complete, envelope.warnings) == (True, KIND, True, [])
    assert envelope.data == {"value": {"stories": ["S1"]}}
    assert store.payload(envelope.result_id) == {"value": {"stories": ["S1"]}}

    # provenance: tool, build, host program, model id and revision, inputs as given, timing
    p = envelope.provenance
    assert (p.tool, p.tool_version) == (TOOL, "0123456789ab+fedcba987654")
    assert p.host == HOST  # program, model id and revision
    assert (p.inputs, p.started_at, p.duration_ms) == (inputs, "2026-01-01T00:00:01.000Z", 37)
    # parents of the stored result are the results of the resolved references
    assert store.get(envelope.result_id).parents == [rid]


def _producer() -> Provenance:
    return Provenance(tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0)


def test_inline_data_limit(store: ResultStore) -> None:
    def size(n: int) -> int:
        return len(canonical_json({"value": {"text": "x" * n}}))

    fit = 16384 - (size(0))  # characters that make the canonical payload exactly 16384 bytes
    assert size(fit) == 16384
    assert _make(store, {"text": "x" * fit}).data is not None
    over = _make(store, {"text": "x" * (fit + 1)})
    assert over.data is None  # larger data is in the store only
    assert store.payload(over.result_id) == {"value": {"text": "x" * (fit + 1)}}
    assert over.complete is True


def test_summary_limit(store: ResultStore) -> None:
    fit = 4096 - len(canonical_json({"note": ""}))
    assert _make(store, {}, summary={"note": "y" * fit}).summary == {"note": "y" * fit}
    with pytest.raises(ContractError) as caught:
        _make(store, {}, summary={"note": "y" * (fit + 1)})
    assert caught.value.detail.code is ErrorCode.LIMIT_EXCEEDED


def test_truncated_reply_is_partial(store: ResultStore) -> None:
    envelope = _make(store, {"stories": ["S1"]}, truncated=True)
    assert envelope.complete is False
    assert [w.code for w in envelope.warnings] == [WarningCode.PARTIAL_DATA]
    assert store.get(envelope.result_id).complete is False


def test_payload_is_validated_against_the_kind(store: ResultStore) -> None:
    with pytest.raises(ContractError) as caught:
        _make(store, {}, payload={"stories": ["S1"]})  # harness.run_output/1 needs `value`
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT


def test_file_input_kind_is_registered(store: ResultStore) -> None:
    record = store.put(
        "harness.file_input/1",
        {"name": "model.EDB", "sha256": SHA, "size_bytes": 10},
        _producer(),
    )
    assert record.kind == "harness.file_input/1"
    with pytest.raises(ContractError):  # a path is not a base name
        store.put("harness.file_input/1", {"name": "C:/x/model.EDB", "sha256": SHA, "size_bytes": 10}, _producer())


def test_parse_reply() -> None:
    assert parse_reply(_result({"items": [1, 2], "truncated": False})) == HostReply(
        data={"items": [1, 2], "truncated": False}, truncated=False
    )
    assert parse_reply(_result({"items": [], "truncated": True})).truncated is True
    assert parse_reply(_result({"items": []})).truncated is False
    assert parse_reply(_result({"truncated": "yes"})).truncated is False  # only the JSON true counts


@pytest.mark.parametrize(
    "result",
    [
        {"content": [], "isError": False},
        {"content": [{"type": "text", "text": "not json"}], "isError": False},
        {"content": [{"type": "text", "text": "[1]"}], "isError": False},
        {"content": [{"type": "text", "text": "{}"}, {"type": "text", "text": "{}"}], "isError": False},
        {"content": [{"type": "image", "data": "", "mimeType": "image/png"}], "isError": False},
    ],
)
def test_unexpected_reply_shapes_are_refused(result: dict[str, Any]) -> None:
    with pytest.raises(ContractError) as caught:
        parse_reply(result)
    assert (caught.value.detail.code, caught.value.detail.host_code) == (ErrorCode.HOST_ERROR, "UNEXPECTED_REPLY")


def test_error_replies_are_not_envelopes() -> None:
    body = {"code": "model_locked", "message": "locked", "data": None}
    with pytest.raises(ContractError) as caught:
        parse_reply(_result(body, is_error=True))
    detail = caught.value.detail
    assert (detail.code, detail.host_code, detail.retryable) == (ErrorCode.HOST_ERROR, "model_locked", False)
