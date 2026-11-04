"""Shared building blocks of the neutral kinds (spec 4.10.1, 4.10.2).

Units: every field whose name has a unit suffix carries `x-eng-unit` in its JSON Schema (04 section 4 rule 1).
Errors: `ValueError` inside validators, which Pydantic reports as `ValidationError`.
"""

from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from eng_contract.units import kind_for_field

Name = Annotated[str, StringConstraints(min_length=1, max_length=200)]
"""An `id` or `name` string: 1 to 200 characters."""
Positive = Annotated[float, Field(gt=0)]


def _annotate_units(schema: dict[str, Any]) -> None:
    for field, prop in schema.get("properties", {}).items():
        quantity = kind_for_field(field)
        if quantity is not None:
            prop["x-eng-unit"] = quantity.canonical_unit


class Payload(BaseModel):
    """Base of every kind payload and its parts: frozen, no extra fields, finite numbers, unit annotations."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False, json_schema_extra=_annotate_units)


def require_unique(items: Iterable[Any], attr: str, what: str) -> None:
    """Raise `ValueError` naming the duplicated `attr` values of `items` (`what` names the list)."""
    values = [getattr(i, attr) for i in items]
    if duplicated := sorted({v for v in values if values.count(v) > 1}):
        raise ValueError(f"duplicate {what}: {duplicated}")


class Point3(Payload):
    """A point in model global coordinates, millimetres."""

    x_mm: float
    y_mm: float
    z_mm: float


class CaseType(StrEnum):
    """What a `CaseRef` names."""

    LOAD_PATTERN = "load_pattern"
    LOAD_CASE = "load_case"
    LOAD_COMBINATION = "load_combination"


class CaseRef(Payload):
    """A load pattern, case or combination; `step` is the envelope `Max`/`Min` or step number as the host reports it."""

    case: Name
    case_type: CaseType
    step: str | None = None
