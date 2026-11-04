"""MCP mapping helpers (plan T15; spec 4.11; AC49, AC49a, AC50)."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter

from eng_contract.canonical import canonical_json
from eng_contract.envelope import Envelope
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
