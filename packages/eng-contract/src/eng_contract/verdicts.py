"""Verdict and Subject: the result of one check on one subject (spec 4.9.1, 04 section 5.1).

Purpose: carry a code-pack or host check outcome with its demand, capacity, ratio and trace reference.
Units: `Subject.station_mm` in millimetres; demand and capacity are `Quantity` of one dimension; `ratio` has none.
Errors: `pydantic.ValidationError` for any consistency violation. Equality is physical: `Quantity` equality decides
and never raises (AC35a).
"""

import re
from enum import StrEnum, auto
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from eng_contract.quantity import Quantity
from eng_contract.refs import LocalTraceRef, RefString
from eng_contract.units import UNITS

CODE_PACK_CHECK_ID = r"^[a-z][a-z0-9_]*\.[0-9a-z_]+\.[a-z][a-z0-9_]*$"
HOST_CHECK_ID = r"^[a-z0-9_.:-]+$"


class VerdictSource(StrEnum):
    """Who produced the verdict."""

    CODE_PACK = "code_pack"
    HOST = "host"


class VerdictStatus(StrEnum):
    """Outcome of a check; each member's value is its own name."""

    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[str]) -> str:
        """Use the member name as its value (the default would lower-case it)."""
        return name

    PASS = auto()
    FAIL = auto()
    NOT_APPLICABLE = auto()
    NEEDS_ENGINEER = auto()
    ERROR = auto()


class SubjectKind(StrEnum):
    """Kind of the checked object; new values are additive."""

    JOINT = "joint"
    FRAME = "frame"
    AREA = "area"
    LINK = "link"
    STORY = "story"
    GRID_LINE = "grid_line"
    SECTION = "section"
    MATERIAL = "material"
    LOAD_PATTERN = "load_pattern"
    LOAD_COMBINATION = "load_combination"
    FOOTING = "footing"
    MODEL = "model"


class Subject(BaseModel):
    """The object a verdict or issue is about; `station_mm` is the position along it, `case` the governing case."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    kind: SubjectKind
    id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    station_mm: Annotated[float, Field(ge=0)] | None = None
    case: Annotated[str, StringConstraints(max_length=200)] | None = None


class Verdict(BaseModel):
    """One check result; `ratio` is computed by the producer (demand / capacity) and is not recomputed here."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    source: VerdictSource
    check_id: Annotated[str, StringConstraints(max_length=200)]
    code: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    clause: Annotated[str, StringConstraints(max_length=100)] | None = None
    subject: Subject
    demand: Quantity | None = None
    capacity: Quantity | None = None
    ratio: Annotated[float, Field(ge=0)] | None = None
    ratio_limit: Annotated[float, Field(gt=0)] = 1.0
    status: VerdictStatus
    governing: bool = False
    trace_ref: RefString | LocalTraceRef | None = None
    assumptions: list[Annotated[str, StringConstraints(max_length=500)]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        code_pack = self.source is VerdictSource.CODE_PACK
        pattern = CODE_PACK_CHECK_ID if code_pack else HOST_CHECK_ID
        if not re.fullmatch(pattern, self.check_id):
            raise ValueError(f"check_id {self.check_id!r} does not match the {self.source.value} pattern")
        if code_pack and (self.clause is None or self.trace_ref is None):
            raise ValueError("a code_pack verdict requires clause and trace_ref")
        if (
            self.demand is not None
            and self.capacity is not None
            and UNITS[self.demand.unit].dimension != UNITS[self.capacity.unit].dimension
        ):
            raise ValueError("demand and capacity must have the same dimension")
        if self.status in (VerdictStatus.PASS, VerdictStatus.FAIL):
            if self.ratio is None:
                raise ValueError(f"status {self.status.value} requires a ratio")
            if (self.ratio <= self.ratio_limit) != (self.status is VerdictStatus.PASS):
                raise ValueError(
                    f"status {self.status.value} contradicts ratio {self.ratio} and limit {self.ratio_limit}"
                )
            if code_pack and (self.demand is None or self.capacity is None):
                raise ValueError("a code_pack PASS or FAIL requires demand and capacity")
        return self


__all__ = ["Subject", "SubjectKind", "Verdict", "VerdictSource", "VerdictStatus"]
