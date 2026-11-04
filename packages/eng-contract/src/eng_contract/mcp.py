"""MCP mapping helpers (spec 4.11; 04 section 10).

Purpose: map envelopes to and from MCP tool results as plain dicts; no MCP SDK is imported.
Errors: `NotAnEnvelope` when a tool result is not a contract envelope.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter, ValidationError

from eng_contract import CONTRACT_VERSION
from eng_contract.canonical import canonical_json
from eng_contract.envelope import Envelope, FailureEnvelope, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode

_ADAPTER: TypeAdapter[SuccessEnvelope | FailureEnvelope] = TypeAdapter(Envelope)
_JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class NotAnEnvelope(ContractError):  # noqa: N818  # B-024: name fixed by spec 4.11
    """A tool result is not a valid contract envelope; code `INVALID_ARGUMENT`; `errors` holds the validation errors."""

    def __init__(self, message: str, errors: list[Any] | None = None) -> None:
        """Keep the message and the validation `errors`."""
        super().__init__(ErrorCode.INVALID_ARGUMENT, message)
        self.errors = errors or []


class RawToolReply(BaseModel):
    """What a server that does not speak the contract returned (spec 4.11)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_error: bool
    structured: dict[str, JsonValue] | None
    texts: list[str]
    json_texts: list[JsonValue]
    other_blocks: int


def envelope_to_tool_result(env: SuccessEnvelope | FailureEnvelope) -> dict[str, Any]:
    """Map an envelope to an MCP tool result: canonical JSON text block, `structuredContent`, `isError`."""
    return {
        "content": [{"type": "text", "text": canonical_json(env.model_dump(mode="json", by_alias=True)).decode()}],
        "structuredContent": env.model_dump(mode="json", by_alias=True),
        "isError": not env.ok,
    }


def tool_result_to_envelope(result: Mapping[str, Any]) -> SuccessEnvelope | FailureEnvelope:
    """Validate `structuredContent` as an envelope.

    Raises:
        NotAnEnvelope: it is absent or invalid, or `isError` disagrees with `ok`.
    """
    structured = result.get("structuredContent")
    if structured is None:
        raise NotAnEnvelope("tool result has no structuredContent")
    try:
        env = _ADAPTER.validate_python(structured)
    except ValidationError as exc:
        raise NotAnEnvelope("structuredContent is not an envelope", exc.errors(include_context=False)) from exc
    if bool(result.get("isError", False)) is env.ok:
        raise NotAnEnvelope("isError disagrees with ok")
    return env


def extract_raw_reply(result: Mapping[str, Any]) -> RawToolReply:
    """Split any tool result into its error flag, structured content, texts, parsed JSON texts and other blocks."""
    texts: list[str] = []
    other = 0
    for block in result.get("content") or []:
        if isinstance(block, Mapping) and block.get("type") == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
        else:
            other += 1
    parsed: list[JsonValue] = []
    for text in texts:
        try:
            parsed.append(_JSON.validate_json(text))
        except ValidationError:
            continue
    structured = result.get("structuredContent")
    return RawToolReply(
        is_error=bool(result.get("isError", False)),
        structured=structured if isinstance(structured, dict) else None,
        texts=texts,
        json_texts=parsed,
        other_blocks=other,
    )


def output_schema() -> dict[str, Any]:
    """Object schema (JSON Schema 2020-12) for a tool's `outputSchema`: success or failure envelope."""
    defs: dict[str, Any] = {}
    for model in (SuccessEnvelope, FailureEnvelope):
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        defs.update(schema.pop("$defs", {}))
        defs[model.__name__] = schema
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["contract", "ok"],
        "properties": {"contract": {"const": CONTRACT_VERSION}, "ok": {"type": "boolean"}},
        "oneOf": [{"$ref": "#/$defs/SuccessEnvelope"}, {"$ref": "#/$defs/FailureEnvelope"}],
        "$defs": defs,
    }
