"""The result codec (spec 0001 4.5.2): canonical round trip, then quantity objects rebuilt.

Purpose: a live result and a replayed one pass through the same steps, so block code sees equal values.
Units: none; quantity objects keep the unit they carry.
Errors: `CanonicalJsonError` for a value outside the JSON data model or a summary that is not an object.
"""

from collections.abc import Mapping
from typing import cast

from eng_contract.canonical import CanonicalJsonError, canonical_json, loads
from eng_contract.quantity import LabeledQuantity, Quantity
from eng_contract.units import UNITS

from eng_harness.ctx import SummaryValue

__all__ = ["decode", "decode_summary"]

_QUANTITY_KEYS = frozenset({"value", "unit"})


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _rebuild(value: object) -> SummaryValue:
    if isinstance(value, list):
        return [_rebuild(item) for item in value]
    if not isinstance(value, dict):
        return cast(SummaryValue, value)  # a JSON scalar after the canonical round trip
    unit = value.get("unit")
    if _is_number(value.get("value")) and isinstance(unit, str) and unit in UNITS:
        labels = {k: v for k, v in value.items() if k not in _QUANTITY_KEYS}
        if all(isinstance(v, str | int) for v in labels.values()):  # bool is an int
            number = float(value["value"])
            return LabeledQuantity(value=number, unit=unit, **labels) if labels else Quantity(number, unit)
    return {key: _rebuild(item) for key, item in value.items()}


def decode(value: object) -> SummaryValue:
    """Pass `value` through canonical JSON and rebuild its quantity objects (integral floats come back as floats).

    A quantity object is a JSON object with a numeric `value`, a `unit` that is a known symbol, and at most string
    or integer labels; anything else stays plain data.

    Raises:
        CanonicalJsonError: `value` is not canonical-serializable.
    """
    return _rebuild(loads(canonical_json(value)))


def decode_summary(summary: object) -> dict[str, SummaryValue]:
    """`decode` for an envelope summary, which must be an object.

    Raises:
        CanonicalJsonError: `summary` is not a mapping or is not canonical-serializable.
    """
    if not isinstance(summary, Mapping):
        raise CanonicalJsonError("a summary must be a JSON object")
    return cast(dict[str, SummaryValue], decode(dict(summary)))  # an object stays an object
