"""Redaction of decision state: field names by construction, values at runtime (spec 0005 section 4.10; 16 section 2).

Units: string lengths count characters. Errors: ``check_state`` raises ``TypeError`` for a value that is not JSON;
``denied_token`` returns the offending token and the caller (``_points``) raises ``DecisionDefinitionError``.
Findings carry a field path and a reason, never a value.
"""

import re
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Annotated, Any, get_args, get_origin

from eng_contract.refs import Ref
from eng_contract.units import UNITS
from pydantic import BaseModel, ConfigDict, JsonValue

__all__ = [
    "DENIED_TOKENS",
    "LABEL_BOUND",
    "RedactionFinding",
    "RedactionReason",
    "check_state",
    "denied_token",
    "outgoing_state",
]

# Spec 0005 section 4.10: tokens of a field name (split on "_") that may not appear; settings may add, never remove.
DENIED_TOKENS = frozenset(
    {
        "project",
        "client",
        "address",
        "location",
        "person",
        "author",
        "engineer",
        "owner",
        "user",
        "email",
        "phone",
        "path",
        "file",
        "folder",
        "directory",
    }
)
LABEL_BOUND = 80  # characters; the maximum length of a Label (spec 0005 AC2)
_MIN_SENSITIVE = 3  # characters; shorter sensitive values are ignored (spec 0005 section 4.10)

_DRIVE = re.compile(r"^[A-Za-z]:")
# A URL scheme (spec 0005 section 4.10): any "scheme://" form, or a known scheme word followed by ":" (mailto:, tel:).
# Plain text with a colon ("Note: enlarge", "1:2") is no URL.
_SCHEME = re.compile(
    r"\b[A-Za-z][A-Za-z0-9+.\-]*://|\b(?:https?|ftp|file|mailto|tel|sms|data|javascript|urn):", re.IGNORECASE
)


class RedactionReason(StrEnum):
    """Why a value may not leave the machine."""

    PATH = "path"
    URL = "url"
    ADDRESS = "address"
    SENSITIVE_VALUE = "sensitive_value"
    TOO_LONG = "too_long"


class RedactionFinding(BaseModel):
    """One failed value: where it is (``field_path``, dotted, list items by index) and why. Never the value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field_path: str
    reason: RedactionReason


def denied_token(name: str, extra: frozenset[str]) -> str | None:
    """Return the first token of field ``name`` (split on ``_``, lower case) in the deny list or ``extra``, else None.

    ``None`` is the answer "no denied token", not a failure.
    """
    denied = DENIED_TOKENS | {t.lower() for t in extra}
    return next((token for token in name.lower().split("_") if token in denied), None)


def _reasons(text: str, sensitive: tuple[str, ...], *, structural: bool) -> list[RedactionReason]:
    found: list[RedactionReason] = []
    if structural:
        if _DRIVE.match(text) or "/" in text or "\\" in text:
            found.append(RedactionReason.PATH)
        if _SCHEME.search(text):
            found.append(RedactionReason.URL)
        if "@" in text:
            found.append(RedactionReason.ADDRESS)
    folded = text.casefold()
    if any(value in folded for value in sensitive):
        found.append(RedactionReason.SENSITIVE_VALUE)
    if len(text) > LABEL_BOUND:
        found.append(RedactionReason.TOO_LONG)
    return found


def _is_quantity(value: Mapping[str, object]) -> bool:
    """A ``{value, unit}`` object whose unit is a contract unit symbol (``kN/m`` holds a slash but is no path)."""
    unit = value.get("unit")
    return value.keys() == {"value", "unit"} and isinstance(unit, str) and unit in UNITS


def _walk(value: object, path: str, sensitive: tuple[str, ...], structural: bool) -> list[RedactionFinding]:
    """Collect findings under ``value``; raise ``TypeError`` (type name and path only) for a non-JSON value or key."""
    if isinstance(value, str):
        return [RedactionFinding(field_path=path, reason=r) for r in _reasons(value, sensitive, structural=structural)]
    found: list[RedactionFinding] = []
    if isinstance(value, Mapping):
        quantity = _is_quantity(value)
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"state key under '{path or '$'}' is {type(key).__name__}, not str")
            found += _walk(
                item, f"{path}.{key}" if path else key, sensitive, structural and not (quantity and key == "unit")
            )
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            found += _walk(item, f"{path}.{index}" if path else str(index), sensitive, structural)
    elif value is not None and not isinstance(value, int | float):  # bool is an int
        raise TypeError(f"state value at '{path or '$'}' is {type(value).__name__}, not a JSON value")
    return found


def check_state(state: JsonValue, sensitive_values: Iterable[str]) -> tuple[RedactionFinding, ...]:
    """Check every string of the JSON ``state`` (spec 0005 section 4.10); return findings sorted by path and reason.

    ``sensitive_values`` is the union of ``DecisionSettings`` and ``DecisionCall`` values; those shorter than 3
    characters are ignored and matching is case-insensitive. Empty result means the state may be sent or stored.
    Errors: ``TypeError`` naming the field path (never the value) when ``state`` holds anything but str, int, float,
    bool, None, a str-keyed mapping, a list or a tuple (a model, bytes or a set is refused, not passed as clean).
    """
    sensitive = tuple(v.casefold() for v in sensitive_values if len(v) >= _MIN_SENSITIVE)
    found = _walk(state, "" if isinstance(state, Mapping | list | tuple) else "$", sensitive, True)
    return tuple(sorted(found, key=lambda f: (f.field_path, f.reason.value)))


def _exclusion(annotation: Any) -> Any:
    """Return the pydantic ``exclude`` entry that drops every ``Ref`` under ``annotation`` (empty when none)."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _exclusion(get_args(annotation)[0])
    if origin is tuple:
        args = get_args(annotation)
        if args[-1] is Ellipsis or len(args) == 1:
            inner = _exclusion(args[0])
            return True if inner is True else ({"__all__": inner} if inner else {})
        return {i: spec for i, item in enumerate(args) if (spec := _exclusion(item))}
    if annotation is Ref:
        return True
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return {n: spec for n, info in annotation.model_fields.items() if (spec := _exclusion(info.annotation))}
    return {}


def outgoing_state(state: BaseModel) -> dict[str, Any]:
    """Return the JSON form of ``state`` without its ``Ref`` fields (spec 0005 AC34); the engineer screen shows them."""
    return state.model_dump(mode="json", exclude=_exclusion(type(state)) or None)
