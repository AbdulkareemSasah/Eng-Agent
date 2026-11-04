"""Canonical JSON (RFC 8785) and payload hash (spec 4.3.1).

Purpose: one byte-exact serialization of the JSON data model, so hashes agree across producers.
Units: none; numbers are written as given. Errors: `CanonicalJsonError` (`INVALID_ARGUMENT`).
"""

import hashlib
import json
import math
from typing import Any

from pydantic import JsonValue

from eng_contract._jcs import format_float
from eng_contract.errors import ContractError, ErrorCode

_MAX_SAFE_INT = 2**53 - 1  # I-JSON range, RFC 8785 3.2.2.3 and RFC 7493 2.2


class CanonicalJsonError(ContractError):
    """A value or text is outside the JSON data model of spec 4.3.1; the code is fixed to `INVALID_ARGUMENT`."""

    def __init__(self, message: str) -> None:
        """Build the error with code `INVALID_ARGUMENT` (not retryable)."""
        super().__init__(ErrorCode.INVALID_ARGUMENT, message)


def _string(text: str, path: str) -> str:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CanonicalJsonError(f"lone surrogate in string at {path}") from exc
    return json.dumps(text, ensure_ascii=False)  # escapes exactly `"`, `\` and U+0000 to U+001F (RFC 8785 3.2.2.2)


def _write(value: object, out: list[str], path: str) -> None:
    if value is None:
        out.append("null")
    elif isinstance(value, bool):
        out.append("true" if value else "false")
    elif isinstance(value, int):
        if abs(value) > _MAX_SAFE_INT:
            raise CanonicalJsonError(f"integer outside +-(2**53 - 1) at {path}")
        out.append(str(int(value)))
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalJsonError(f"non-finite float at {path}")
        out.append(format_float(value))
    elif isinstance(value, str):
        out.append(_string(value, path))
    elif isinstance(value, list):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _write(item, out, f"{path}[{index}]")
        out.append("]")
    elif isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalJsonError(f"non-string key {type(key).__name__} at {path}")
        out.append("{")
        # UTF-16BE bytes compare as sequences of UTF-16 code units (RFC 8785 3.2.3); lone surrogates fail in _string.
        for index, key in enumerate(sorted(value, key=lambda k: k.encode("utf-16-be", "surrogatepass"))):
            if index:
                out.append(",")
            out.append(_string(key, path) + ":")
            _write(value[key], out, f"{path}.{key}")
        out.append("}")
    else:
        raise CanonicalJsonError(f"{type(value).__name__} is not a JSON type at {path}")


def canonical_json(value: object) -> bytes:
    """Serialize `value` as RFC 8785 UTF-8 bytes without BOM or whitespace.

    Accepts `dict` with `str` keys, `list`, `str`, `bool`, `None`, finite `float` and `int` within +-(2**53 - 1).

    Raises:
        CanonicalJsonError: anything else (NaN, infinities, large `int`, lone surrogate, `tuple`, `Decimal`, ...).
    """
    out: list[str] = []
    try:
        _write(value, out, "$")
    except RecursionError as exc:
        raise CanonicalJsonError("value is nested too deeply") from exc
    return "".join(out).encode("utf-8")


def payload_sha256(value: object) -> str:
    """Lower-case hex SHA-256 of `canonical_json(value)`.

    Raises:
        CanonicalJsonError: `value` is not serializable.
    """
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _parse_int(text: str) -> int | float:
    try:
        number = int(text)
        if abs(number) <= _MAX_SAFE_INT:
            return number
        as_float = float(number)
    except (ValueError, OverflowError) as exc:  # digit-count limit of int(), or beyond float64
        raise CanonicalJsonError("integer literal is not representable") from exc
    # Rule 4 writes an integral float of 2**53 or more as its shortest digits padded with zeros; accept that text too.
    if as_float == number or format_float(as_float) == text:
        return as_float
    raise CanonicalJsonError(f"integer literal {text} is outside +-(2**53 - 1) and not an exact float64")


def _parse_float(text: str) -> float:
    number = float(text)
    if not math.isfinite(number):
        raise CanonicalJsonError(f"number literal {text} overflows float64")
    return number


def _reject_constant(name: str) -> Any:
    raise CanonicalJsonError(f"{name} is not allowed")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise CanonicalJsonError("duplicate object key")
    return result


def loads(data: bytes) -> JsonValue:
    """Parse canonical bytes: the only parser for stored and referenced payloads.

    UTF-8 only. Integers beyond +-(2**53 - 1) become `float` when they are an exact float64 or the text that
    `canonical_json` writes for one, so `canonical_json(loads(canonical_json(v))) == canonical_json(v)` (AC4).
    The result is always accepted by `canonical_json`.

    Raises:
        CanonicalJsonError: invalid UTF-8 or JSON, NaN or an infinity, a duplicate key, a number that overflows
            float64, an integer literal that is not an exact float64, or a lone surrogate (escaped).
    """
    try:
        value: JsonValue = json.loads(
            data.decode("utf-8"),
            parse_int=_parse_int,
            parse_float=_parse_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_pairs,
        )
    except RecursionError as exc:
        raise CanonicalJsonError("text is nested too deeply") from exc
    except ValueError as exc:  # invalid UTF-8 (UnicodeDecodeError) or invalid JSON (JSONDecodeError)
        raise CanonicalJsonError(f"invalid JSON text: {exc}") from exc
    canonical_json(value)  # rule 3: an escaped lone surrogate parses but no canonical writer can produce it
    return value
