"""Outgoing guard: the last check before a byte leaves the machine (spec 0009 section 4.5; AC12, AC13).

Two checks, both over ``DecisionSettings.sensitive_values`` only (a ``ProviderRequest`` carries none): the redaction
check of the request state (``guard_request``) and a scan of the final serialized body (``find_body_place``). Strings
are compared after Unicode NFC normalization and case folding; values shorter than 3 characters are ignored. A finding
is reported as an ``OutgoingPlace`` (the kind of place), never a path, key or value taken from the data.
"""

import json
import unicodedata
from collections.abc import Mapping, Sequence

from pydantic import JsonValue, SecretStr

from eng_harness.decisions._redaction import check_state
from eng_harness.decisions.interfaces import OutgoingPlace, ProviderError, ProviderErrorCode, ProviderRequest

__all__ = ["find_body_place", "guard_request"]

_MIN_SENSITIVE = 3  # characters; spec 0005 section 4.10
_MAX_DEPTH = 64  # nesting of embedded data blocks that is followed; deeper input is refused


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _needles(sensitive_values: Sequence[str]) -> tuple[str, ...]:
    return tuple(_fold(value) for value in sensitive_values if len(value) >= _MIN_SENSITIVE)


def _place(text: str, needles: tuple[str, ...], secret: SecretStr | None, place: OutgoingPlace) -> OutgoingPlace | None:
    # the key is compared without binding it to a name, so no frame keeps it
    if secret is not None and secret.get_secret_value() and secret.get_secret_value() in text:
        return OutgoingPlace.KEY_MATERIAL
    folded = _fold(text)
    return place if any(needle in folded for needle in needles) else None


def _embedded(text: str) -> JsonValue:
    """The JSON object or array a string holds (a data block embedded in a message), else None."""
    if not text.lstrip().startswith(("{", "[")):
        return None
    try:
        parsed: JsonValue = json.loads(text)
    except ValueError:
        return None
    return parsed


def _walk(
    value: object, needles: tuple[str, ...], secret: SecretStr | None, text_place: OutgoingPlace, depth: int = 0
) -> OutgoingPlace | None:
    """Scan every string value and every object key, at any depth, and the data blocks embedded in strings."""
    if depth > _MAX_DEPTH:
        return OutgoingPlace.STATE_VALUE
    found: OutgoingPlace | None = None
    if isinstance(value, str):
        inner = _embedded(value)  # the embedded block first, so that the finding names its own place
        found = None if inner is None else _walk(inner, needles, secret, text_place, depth + 1)
        found = found or _place(value, needles, secret, text_place)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            found = _place(str(key), needles, secret, OutgoingPlace.STATE_KEY) or _walk(
                item, needles, secret, text_place, depth + 1
            )
            if found is not None:
                break
    elif isinstance(value, list | tuple):
        for item in value:
            found = _walk(item, needles, secret, text_place, depth + 1)
            if found is not None:
                break
    return found


def find_body_place(body: bytes, sensitive_values: Sequence[str], secret: SecretStr | None) -> OutgoingPlace | None:
    """Return the kind of place in the serialized JSON ``body`` that holds a sensitive value or the key, else None.

    The body is parsed, never searched as raw bytes, so JSON escaping cannot hide a value. A body that is not valid
    JSON is reported as ``STATE_VALUE`` (it is not scannable, so it is not sent).
    """
    try:
        parsed: JsonValue = json.loads(body)
    except ValueError:
        return OutgoingPlace.STATE_VALUE
    return _walk(parsed, _needles(sensitive_values), secret, OutgoingPlace.STATE_VALUE)


def guard_request(request: ProviderRequest, sensitive_values: Sequence[str]) -> None:
    """Re-run the redaction check on ``request`` (AC13); an adapter calls it before it builds a body.

    Raises:
        ProviderError: ``REDACTION_BLOCKED`` with ``where`` set when the point, an option, or the state holds a
            sensitive value (in a string or in an object key), a path, a URL or an address.
    """
    needles = _needles(sensitive_values)
    place = _place(request.point, needles, None, OutgoingPlace.POINT)
    for option in request.options:
        place = (
            place
            or _place(option.value, needles, None, OutgoingPlace.OPTION_VALUE)
            or _place(option.label, needles, None, OutgoingPlace.OPTION_LABEL)
        )
    place = place or _walk(request.state, needles, None, OutgoingPlace.STATE_VALUE)
    if place is None:
        try:
            structural = bool(check_state(dict(request.state), sensitive_values))
        except TypeError:
            structural = True
        place = OutgoingPlace.STATE_VALUE if structural else None
    if place is not None:
        raise ProviderError(ProviderErrorCode.REDACTION_BLOCKED, where=place)
