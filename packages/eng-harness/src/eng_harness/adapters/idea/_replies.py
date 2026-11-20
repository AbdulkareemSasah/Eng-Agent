"""IDEA replies: path reduction, text cuts and kind payloads (plan 0014 T5; spec 0014 section 4.5).

Purpose: turn a raw IDEA JSON reply into harness kind payloads; absolute paths become base names (A11) and free texts
are cut to 500 characters before storage.
Units: none in this module (loads units are declared on the kinds). Errors: `ContractError` `HOST_ERROR` with
`host_code` `UNEXPECTED_REPLY` when a reply cannot be mapped to its kind (spec 0014 AC12, A1).
"""

from collections.abc import Mapping, Sequence
from pathlib import PurePath, PureWindowsPath
from typing import Any, cast

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.mcp import extract_raw_reply
from pydantic import BaseModel, ValidationError

from eng_harness.kinds.idea import (
    IDEA_KINDS,
    IdeaCheckRaw,
    IdeaLoads,
    IdeaProject,
    IdeaStatus,
)

__all__ = [
    "IDEA_KINDS",
    "TEXT_LIMIT",
    "cut_text",
    "parse_check_raw",
    "parse_loads",
    "parse_project",
    "parse_reply_json",
    "parse_status",
    "reduce_paths",
]

TEXT_LIMIT = 500
"""Maximum length of message texts stored on IDEA kinds (spec 0014 section 4.5)."""


def cut_text(text: str, limit: int = TEXT_LIMIT) -> str:
    """Return `text` cut to at most `limit` characters (spec 0014 section 4.5)."""
    return text if len(text) <= limit else text[:limit]


def _is_absolute_path(value: str) -> bool:
    """True when `value` looks like an absolute filesystem path (POSIX or Windows)."""
    if not value:
        return False
    posix = PurePath(value)
    windows = PureWindowsPath(value)
    return posix.is_absolute() or windows.is_absolute()


def _basename(value: str) -> str:
    """The base name of an absolute path; Windows and POSIX separators both apply."""
    windows = PureWindowsPath(value)
    if windows.is_absolute():
        return windows.name
    return PurePath(value).name


def reduce_paths(value: Any) -> Any:
    """Return `value` with every absolute path string reduced to its base name (A11; spec 0014 section 4.5)."""
    if isinstance(value, str):
        text = cut_text(value)
        return _basename(text) if _is_absolute_path(text) else text
    if isinstance(value, Mapping):
        return {key: reduce_paths(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [reduce_paths(item) for item in value]
    return value


def parse_reply_json(result: Mapping[str, Any]) -> dict[str, Any]:
    """The single JSON object of a successful IDEA tool result (shared envelope shape of 0002 section 4.5.3).

    Raises:
        ContractError: `HOST_ERROR` with `host_code` `UNEXPECTED_REPLY` for any other shape.
    """
    raw = extract_raw_reply(result)
    body = raw.json_texts[0] if raw.json_texts else None
    if raw.is_error or len(raw.texts) != 1 or raw.other_blocks or not isinstance(body, dict):
        code = (body.get("code") if raw.is_error and isinstance(body, dict) else None) or "UNEXPECTED_REPLY"
        raise ContractError(
            ErrorCode.HOST_ERROR,
            "the host reply is not a success",
            retryable=False,
            host_code=str(code)[:200],
        )
    reduced = reduce_paths(body)
    return cast(dict[str, Any], reduced)


def _validate[T: BaseModel](kind: str, payload: Mapping[str, Any], model: type[T]) -> T:
    try:
        return model.model_validate(reduce_paths(dict(payload)))
    except ValidationError as error:
        raise ContractError(
            ErrorCode.HOST_ERROR,
            f"the host reply is not a valid {kind}",
            retryable=False,
            host_code="UNEXPECTED_REPLY",
            field=kind,
            received={"errors": error.errors(include_url=False)},
        ) from None


def parse_status(payload: Mapping[str, Any]) -> IdeaStatus:
    """Validate a reduced `harness.idea_status/1` payload."""
    return _validate("harness.idea_status/1", payload, IdeaStatus)


def parse_project(payload: Mapping[str, Any]) -> IdeaProject:
    """Validate a reduced `harness.idea_project/1` payload."""
    return _validate("harness.idea_project/1", payload, IdeaProject)


def parse_loads(payload: Mapping[str, Any]) -> IdeaLoads:
    """Validate a reduced `harness.idea_loads/1` payload."""
    return _validate("harness.idea_loads/1", payload, IdeaLoads)


def parse_check_raw(payload: Mapping[str, Any]) -> IdeaCheckRaw:
    """Validate a reduced `harness.idea_check_raw/1` payload (`offline_stub` must be false)."""
    return _validate("harness.idea_check_raw/1", payload, IdeaCheckRaw)
