"""Trace: the recorded steps of one calculation (spec 4.9.3).

Purpose: make every code-pack or harness calculation reproducible and auditable inside a payload.
Units: symbols of `units.UNITS` or null (dimensionless or unitless).
Errors: `pydantic.ValidationError` for duplicate names, a `uses` entry that is not earlier, or an unknown output.
"""

import re
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, field_validator, model_validator

from eng_contract._types import Sha256Hex
from eng_contract.cited import Cited
from eng_contract.refs import RefString
from eng_contract.units import unit as lookup_unit
from eng_contract.verdicts import CODE_PACK_CHECK_ID, Subject, VerdictStatus

_Name = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
_FROZEN = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


def _known_unit(symbol: str | None) -> str | None:
    if symbol is not None:
        lookup_unit(symbol)  # raises UnitError (UNIT_MISMATCH) for an unknown symbol
    return symbol


class TraceInput(BaseModel):
    """An input value, with `ref` naming where it came from."""

    model_config = _FROZEN

    name: _Name
    value: JsonValue
    unit: str | None = None
    ref: RefString | None = None

    _unit_known = field_validator("unit")(_known_unit)


class TraceConstant(BaseModel):
    """A named, cited constant."""

    model_config = _FROZEN

    name: _Name
    cited: Cited


class TraceStep(BaseModel):
    """One calculation step; `uses` names earlier inputs, constants or steps."""

    model_config = _FROZEN

    name: _Name
    value: int | Annotated[float, Field(allow_inf_nan=False)] | bool | str
    unit: str | None = None
    formula: Annotated[str, StringConstraints(max_length=1000)]
    source: Annotated[str, StringConstraints(max_length=500)]
    uses: list[_Name]

    _unit_known = field_validator("unit")(_known_unit)


class Trace(BaseModel):
    """A calculation trace; names are unique over inputs, constants and steps."""

    model_config = _FROZEN

    calc_id: Annotated[str, StringConstraints(max_length=200)]
    calc_version: Annotated[str, StringConstraints(max_length=64)]
    content_sha256: Sha256Hex
    subject: Subject | None = None
    inputs: list[TraceInput]
    constants: list[TraceConstant]
    steps: list[TraceStep]
    outputs: list[_Name]
    status: VerdictStatus | None = None
    messages: list[Annotated[str, StringConstraints(max_length=2000)]] = Field(default_factory=list)

    @field_validator("calc_id")
    @classmethod
    def _calc_id_form(cls, calc_id: str) -> str:
        if not (re.fullmatch(CODE_PACK_CHECK_ID, calc_id) or re.fullmatch(r"^harness\.[a-z0-9_.]+$", calc_id)):
            raise ValueError("calc_id must be a code-pack check_id or match ^harness\\.[a-z0-9_.]+$")
        return calc_id

    @model_validator(mode="after")
    def _names_consistent(self) -> Self:
        seen: set[str] = set()
        for name in [*(i.name for i in self.inputs), *(c.name for c in self.constants)]:
            if name in seen:
                raise ValueError(f"duplicate name {name!r}")
            seen.add(name)
        for step in self.steps:
            missing = [n for n in step.uses if n not in seen]
            if missing:
                raise ValueError(f"step {step.name!r} uses names that are not earlier in the trace: {missing}")
            if step.name in seen:
                raise ValueError(f"duplicate name {step.name!r}")
            seen.add(step.name)
        producible = {i.name for i in self.inputs} | {t.name for t in self.steps}
        unknown = [n for n in self.outputs if n not in producible]
        if unknown:
            raise ValueError(f"outputs name no input or step: {unknown}")
        return self


__all__ = ["Trace", "TraceConstant", "TraceInput", "TraceStep"]
