"""Revit specification-identifier units (plan 0011 T5; spec 0011 AC7, §4.6).

Purpose: convert a parameter's `rawValue` by `_specs.toml` (length `ft`→`mm`, angle `rad`→`deg`) through
`eng_contract.units.convert`. `displayValue` is never parsed. An unmapped `specId` is left out with info issue
`PARAMETER_UNIT_UNMAPPED`. Units: mm, deg. Errors: none raised.
"""

import tomllib
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from typing import Any, Literal, NamedTuple

from eng_contract.issues import ModelIssue, Severity
from eng_contract.units import convert
from eng_contract.verdicts import Subject
from pydantic import BaseModel, ConfigDict, Field

__all__ = ["SpecEntry", "convert_parameter", "load_specs", "specs_table"]

SpecKind = Literal["length", "angle"]
SpecStatus = Literal["reference", "candidate"]


class SpecEntry(BaseModel):
    """One specification identifier mapped to a contract quantity kind and its internal/contract units."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: SpecKind
    internal_unit: str
    contract_unit: str
    status: SpecStatus
    source: str = Field(min_length=1)


class _Loaded(NamedTuple):
    by_id: dict[str, SpecEntry]


@lru_cache(maxsize=1)
def load_specs() -> _Loaded:
    """Load the packaged `_specs.toml` (length and angle only, spec 0011 §4.6)."""
    text = files("eng_harness.adapters.revit").joinpath("_specs.toml").read_text(encoding="utf-8")
    data = tomllib.loads(text)
    specs = data.get("specs")
    if not isinstance(specs, dict):
        msg = "revit/_specs.toml: missing [specs] table"
        raise ValueError(msg)
    by_id: dict[str, SpecEntry] = {}
    for spec_id, row in specs.items():
        if not isinstance(row, dict):
            msg = f"revit/_specs.toml: {spec_id!r} is not a table"
            raise ValueError(msg)
        by_id[str(spec_id)] = SpecEntry.model_validate(row)
    return _Loaded(by_id=by_id)


def specs_table() -> dict[str, SpecEntry]:
    """The specification map; keys are Autodesk Spec identifiers (candidate until L7)."""
    return dict(load_specs().by_id)


def convert_parameter(
    parameter: Mapping[str, Any],
    *,
    subject: Subject,
) -> tuple[float | None, ModelIssue | None]:
    """Convert `rawValue` by `specId`; return `(value_in_contract_unit, None)` or `(None, info issue)`.

    `displayValue` is ignored (spec 0011 §4.6 / AC7). A missing or unmapped `specId` yields
    `PARAMETER_UNIT_UNMAPPED`.
    """
    spec_id = parameter.get("specId")
    raw = parameter.get("rawValue")
    # displayValue is intentionally unread (AC7: never parsed).
    _ = parameter.get("displayValue")
    if not isinstance(spec_id, str) or not spec_id:
        return None, ModelIssue(
            severity=Severity.INFO,
            code="PARAMETER_UNIT_UNMAPPED",
            subject=subject,
            message="parameter has no specId; left out of the payload",
        )
    entry = load_specs().by_id.get(spec_id)
    if entry is None:
        return None, ModelIssue(
            severity=Severity.INFO,
            code="PARAMETER_UNIT_UNMAPPED",
            subject=subject,
            message=f"specification {spec_id} has no entry in _specs.toml; left out of the payload",
        )
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None, ModelIssue(
            severity=Severity.INFO,
            code="PARAMETER_UNIT_UNMAPPED",
            subject=subject,
            message=f"specification {spec_id}: rawValue is not a number; left out of the payload",
        )
    return convert(float(raw), entry.internal_unit, entry.contract_unit), None
