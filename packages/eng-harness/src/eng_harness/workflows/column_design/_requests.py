"""Engineer requests of the column workflow (spec 0013 section 4.3); `request_refusal` names spiral and seismic gaps."""

from typing import Annotated, ClassVar, Literal, Self

from eng_contract.kinds.basis import BasisPath
from eng_contract.units import QUANTITY_KINDS, UNITS
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from eng_harness.kinds.edit_cycle import NONEMPTY, Label

_GAP_SPIRAL = "CK Q4"  # spec 0013 section 4.3, CK Q4
_GAP_SEISMIC = "CK Q10"  # spec 0013 section 4.3, CK Q10
_Names = Annotated[list[Label], Field(min_length=NONEMPTY)]


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class BasisValue(_M):
    source: Literal["basis"]
    path: BasisPath


class _InputValue(_M):
    source: Literal["input"]
    value: Annotated[float, Field(strict=True)]
    unit: Label
    quantity: ClassVar[str]

    @field_validator("unit")
    @classmethod
    def _dimension(cls, unit: str) -> str:
        known = UNITS.get(unit)
        if known is None or known.dimension != QUANTITY_KINDS[cls.quantity].dimension:
            raise ValueError(f"unit {unit!r} is not a {cls.quantity} unit")
        return unit


class _LengthInput(_InputValue):
    quantity = "length"


class _Area(_InputValue):
    quantity = "area"


LengthValue = Annotated[BasisValue | _LengthInput, Field(discriminator="source")]
_AreaValue = Annotated[BasisValue | _Area, Field(discriminator="source")]


class _Select(_M):
    stories: _Names | None = None
    sections: _Names | None = None

    @model_validator(mode="after")
    def _some(self) -> Self:
        if self.stories is None and self.sections is None:
            raise ValueError("a selection names stories or sections")
        return self


class ColumnScopeRequest(_M):
    frames: _Names | None = None
    select: _Select | None = None
    combinations: _Names
    special_seismic: StrictBool

    @model_validator(mode="after")
    def _one(self) -> Self:
        if (self.frames is None) == (self.select is None):
            raise ValueError("give frames or select, not both and not neither")
        return self


class _Layout(_M):
    section: Label
    transverse_kind: Literal["tied", "spiral"]
    n_bars_b: Annotated[int, Field(ge=2)]  # spec 0013 section 4.3: at least 2 (AF section 3)
    n_bars_h: Annotated[int, Field(ge=2)]  # spec 0013 section 4.3
    A_bar: _AreaValue
    d_prime: LengthValue


class ColumnLayoutRequest(_M):
    sections: Annotated[list[_Layout], Field(min_length=NONEMPTY)]


class _Rect(_M):
    b: LengthValue
    h: LengthValue


class _Circ(_M):
    D: LengthValue


class _Proposal(_M):
    frame_id: Label
    required: _Rect | _Circ


class ColumnProposalRequest(_M):
    columns: Annotated[list[_Proposal], Field(min_length=NONEMPTY)]


def request_refusal(answer: BaseModel) -> tuple[str, str] | None:
    if isinstance(answer, ColumnScopeRequest) and answer.special_seismic:
        return ("NOT_IMPLEMENTED", _GAP_SEISMIC)
    if isinstance(answer, ColumnLayoutRequest) and any(row.transverse_kind == "spiral" for row in answer.sections):
        return ("NOT_IMPLEMENTED", _GAP_SPIRAL)
    return None
