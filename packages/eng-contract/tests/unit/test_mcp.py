"""MCP mapping helpers (plan T15; spec 4.11; AC49, AC49a, AC50)."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter

from eng_contract.canonical import canonical_json
from eng_contract.envelope import Envelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.mcp import (
    NotAnEnvelope,
    RawToolReply,
    envelope_to_tool_result,
    extract_raw_reply,
    output_schema,
    tool_result_to_envelope,
)

DATA = Path(__file__).parent.parent / "data" / "envelopes"
_ADAPTER: TypeAdapter[Any] = TypeAdapter(Envelope)


def _raw(name: str) -> Any:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["success", "failure"])
def test_round_trip(name: str) -> None:
    env = _ADAPTER.validate_python(_raw(name))
    result = envelope_to_tool_result(env)
    assert result["structuredContent"] == env.model_dump(mode="json", by_alias=True)
    assert result["isError"] is (not env.ok)
    assert result["content"] == [{"type": "text", "text": canonical_json(env.model_dump(mode="json")).decode()}]
    assert tool_result_to_envelope(result) == env


def test_is_error_must_agree_with_ok() -> None:
    result = envelope_to_tool_result(_ADAPTER.validate_python(_raw("success")))
    result["isError"] = True
    with pytest.raises(NotAnEnvelope):
        tool_result_to_envelope(result)


def test_invalid_structured_content() -> None:
    with pytest.raises(NotAnEnvelope) as info:
        tool_result_to_envelope({"structuredContent": {"ok": "yes"}, "isError": False})
    assert info.value.errors


def test_raw_reply() -> None:
    result = {
        "isError": True,
        "content": [
            {"type": "text", "text": '{"a": 1}'},
            {"type": "text", "text": "plain words"},
            {"type": "image", "data": "x", "mimeType": "image/png"},
        ],
    }
    assert extract_raw_reply(result) == RawToolReply(
        is_error=True, structured=None, texts=['{"a": 1}', "plain words"], json_texts=[{"a": 1}], other_blocks=1
    )
    with pytest.raises(NotAnEnvelope):
        tool_result_to_envelope(result)
    assert extract_raw_reply({"content": []}).is_error is False


def test_output_schema_is_object() -> None:
    schema = output_schema()
    assert schema["type"] == "object"
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    validator = Draft202012Validator(schema)
    for name in ("success", "failure"):
        validator.validate(_raw(name))
    assert not validator.is_valid({"contract": "eng-contract/1", "ok": "yes"})


def _success_result() -> dict[str, Any]:
    return envelope_to_tool_result(_ADAPTER.validate_python(_raw("success")))


def test_error_messages_are_specific() -> None:
    with pytest.raises(NotAnEnvelope) as absent:
        tool_result_to_envelope({})
    assert absent.value.detail.message == "tool result has no structuredContent"
    with pytest.raises(NotAnEnvelope) as invalid:
        tool_result_to_envelope({"structuredContent": {"ok": "yes"}})
    assert invalid.value.detail.message == "structuredContent is not an envelope"
    result = _success_result()
    result["isError"] = True
    with pytest.raises(NotAnEnvelope) as disagree:
        tool_result_to_envelope(result)
    assert disagree.value.detail.message == "isError disagrees with ok"


def test_output_schema_structure() -> None:
    schema = output_schema()
    assert schema["required"] == ["contract", "ok"]
    assert schema["properties"] == {"contract": {"const": "eng-contract/1"}, "ok": {"type": "boolean"}}
    assert schema["oneOf"] == [{"$ref": "#/$defs/SuccessEnvelope"}, {"$ref": "#/$defs/FailureEnvelope"}]
    assert {"SuccessEnvelope", "FailureEnvelope"} <= set(schema["$defs"])
    assert set(schema) == {"$schema", "type", "required", "properties", "oneOf", "$defs"}


def test_not_an_envelope_is_a_contract_error() -> None:
    result = _success_result()
    result["isError"] = True
    with pytest.raises(NotAnEnvelope) as info:
        tool_result_to_envelope(result)
    assert isinstance(info.value, ContractError)
    assert info.value.detail.code == ErrorCode.INVALID_ARGUMENT
    assert info.value.detail.retryable is False
    with pytest.raises(NotAnEnvelope) as missing:
        tool_result_to_envelope({"isError": False})
    assert missing.value.detail.code == ErrorCode.INVALID_ARGUMENT


@pytest.mark.parametrize("flag", [False, None])
def test_failure_with_is_error_false_or_absent_is_rejected(flag: bool | None) -> None:
    result = envelope_to_tool_result(_ADAPTER.validate_python(_raw("failure")))
    if flag is None:
        del result["isError"]
    else:
        result["isError"] = flag
    with pytest.raises(NotAnEnvelope):
        tool_result_to_envelope(result)


def test_success_with_is_error_absent_passes() -> None:
    result = _success_result()
    del result["isError"]
    assert tool_result_to_envelope(result) == _ADAPTER.validate_python(_raw("success"))


def test_raw_reply_of_envelope_result() -> None:
    result = _success_result()
    reply = extract_raw_reply(result)
    assert reply.structured == result["structuredContent"]
    assert reply.is_error is False
    assert len(reply.json_texts) == 1


def test_raw_reply_counts_malformed_blocks() -> None:
    result = {"content": [{"type": "text", "text": 5}, {"type": "text"}, "oops", {"type": "text", "text": "ok"}]}
    reply = extract_raw_reply(result)
    assert reply.other_blocks == 3
    assert reply.texts == ["ok"]
    assert extract_raw_reply({"structuredContent": [1]}).structured is None
    assert extract_raw_reply({"isError": True}).is_error is True


def test_output_schema_rejects_wrong_contract_and_missing_ok() -> None:
    validator = Draft202012Validator(output_schema())
    good = _raw("success")
    assert validator.is_valid(good)
    assert not validator.is_valid({**good, "contract": "eng-contract/0"})
    assert not validator.is_valid({k: v for k, v in good.items() if k != "ok"})
    assert not validator.is_valid({k: v for k, v in good.items() if k != "contract"})
