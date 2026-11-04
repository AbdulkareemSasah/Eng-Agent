"""Cited: a constant with its unit and source, recorded in traces (spec 4.8).

Purpose: every engineering constant in code is a `Cited`; it has no arithmetic or ordering, code reads `.value`.
Units: any symbol in `units.UNITS`; `"1"` for dimensionless.
Errors: `UnitError` (`UNIT_MISMATCH`) for an unknown unit; `pydantic.ValidationError` for other invalid fields.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, field_validator

from eng_contract.units import unit as lookup_unit


class Cited(BaseModel):
    """Value, unit, source (document, edition, clause, table or page) and an optional note."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: StrictInt | Annotated[float, Field(strict=True, allow_inf_nan=False)]
    unit: str
    source: Annotated[str, StringConstraints(min_length=8, max_length=500, pattern=r"\S")]
    note: Annotated[str, StringConstraints(max_length=500)] | None = None

    @field_validator("unit")
    @classmethod
    def _unit_known(cls, symbol: str) -> str:
        lookup_unit(symbol)  # raises UnitError (UNIT_MISMATCH) for an unknown symbol
        return symbol
