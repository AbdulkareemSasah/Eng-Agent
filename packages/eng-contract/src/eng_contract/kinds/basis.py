"""The `basis.*` kinds, version 1 (spec 4.10.2): the design basis and the engineer's inputs to it.

Units: a field's `unit` is a symbol of `units.UNITS` or null; a path whose last segment has a unit suffix must carry
that suffix's canonical unit.
Errors: `pydantic.ValidationError` for every violated rule (a missing or malformed `source`, an unknown unit, a unit
that contradicts the suffix, a template field without a citation).
"""

import re
from collections.abc import Iterable
from typing import Annotated, Self

from pydantic import JsonValue, StringConstraints, TypeAdapter, ValidationError, field_validator, model_validator

from eng_contract._types import Sha256Hex
from eng_contract.ids import Timestamp
from eng_contract.kinds._common import Name, Payload
from eng_contract.refs import RefString
from eng_contract.units import QUANTITY_KINDS, UNITS, kind_for_field

_SUFFIXES = "|".join(re.escape(kind.suffix) for kind in QUANTITY_KINDS.values())
BasisPath = Annotated[
    str,
    StringConstraints(pattern=rf"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*\.(?:[a-z0-9_]*(?:{_SUFFIXES})|[a-z0-9_]+)$"),
]
"""Dotted path of a basis field, for example `limits.drift_ratio`: lowercase segments, except that the last may end with
one unit suffix of `units.QUANTITY_KINDS` written as the table writes it, for example `compare.stress_MPa`."""
_TIMESTAMP = TypeAdapter(Timestamp)
_REF = TypeAdapter(RefString)


def _known_unit(symbol: str | None) -> str | None:
    if symbol is not None and symbol not in UNITS:
        raise ValueError(f"unknown unit {symbol!r}")
    return symbol


def _valid_source(source: str) -> bool:
    scheme, _, rest = source.partition(":")
    name, _, tail = rest.rpartition("@")
    try:
        if scheme == "template":
            return bool(name and tail and "@" not in name)
        if scheme == "engineer":
            return bool(name) and bool(_TIMESTAMP.validate_python(tail))
        return scheme == "model" and bool(_REF.validate_python(rest))
    except ValidationError:
        return False


class BasisField(Payload):
    """One basis value with its provenance; a template value cites the standard that gives it."""

    value: JsonValue
    unit: str | None
    source: str
    confirmed: bool
    citation: str | None

    _unit_known = field_validator("unit")(_known_unit)

    @field_validator("source")
    @classmethod
    def _source_form(cls, source: str) -> str:
        if not _valid_source(source):
            raise ValueError(
                f"malformed source {source!r}: template:<name>@<version>, engineer:<name>@<Timestamp> or model:<ref>"
            )
        return source

    @model_validator(mode="after")
    def _template_cites(self) -> Self:
        if self.source.startswith("template:") and not self.citation:
            raise ValueError("a template field requires a citation")
        return self


class TemplateRef(Payload):
    """The template the basis was started from."""

    name: Name
    version: Name
    sha256: Sha256Hex


class DesignBasis(Payload):
    """`basis.design_basis/1`: fields keyed by dotted path."""

    template: TemplateRef | None
    fields: dict[BasisPath, BasisField]

    @model_validator(mode="after")
    def _units_match_suffix(self) -> Self:
        for path, field in self.fields.items():
            quantity = kind_for_field(path.rsplit(".", 1)[-1])
            if quantity is not None and field.unit != quantity.canonical_unit:
                raise ValueError(f"unit of {path!r} does not match the unit suffix ({quantity.canonical_unit})")
        return self

    def missing(self, required: Iterable[str]) -> list[str]:
        """Return the paths of `required`, in order, that are absent or not confirmed (11 section 6 item 5)."""
        return [p for p in required if p not in self.fields or not self.fields[p].confirmed]


class EngineerValue(Payload):
    """A value the engineer entered in answer to a step."""

    value: JsonValue
    unit: str | None
    entered_by: Name
    entered_at: Timestamp

    _unit_known = field_validator("unit")(_known_unit)


class EngineerInput(Payload):
    """`basis.engineer_input/1`: `step` is the step path that asked."""

    step: Name
    fields: dict[Name, EngineerValue]
