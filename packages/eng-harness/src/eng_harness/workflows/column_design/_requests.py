"""Engineer requests of the column workflow (spec 0013 section 4.3).

Spiral reinforcement and a special-seismic column parse, so the refusal names its gap.
Errors: `pydantic.ValidationError`; `request_refusal` for the two gaps.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from eng_harness.kinds.edit_cycle import NONEMPTY, Label
from eng_harness.workflows.model_edit_cycle._change_set import BasisValue, LengthValue, _InputValue

_GAP_SPIRAL = "CK Q4"  # spec 0013 section 4.3, CK Q4
_GAP_SEISMIC = "CK Q10"  # spec 0013 section 4.3, CK Q10
_Names = Annotated[list[Label], Field(min_length=NONEMPTY)]


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class _Area(_InputValue):
    quantity = "area"


_AreaValue = Annotated[BasisValue | _Area, Field(discriminator="source")]


class _Select(_M):
    """Stories and sections by name; null means unnamed, and at least one is named."""

    stories: _Names | None = None
    sections: _Names | None = None

    @model_validator(mode="after")
    def _some(self) -> Self:
        if self.stories is None and self.sections is None:
            raise ValueError("a selection names stories or sections")
        return self


class ColumnScopeRequest(_M):
    """Which frames and combinations to check, and that none is special seismic (spec 0013 section 4.3)."""

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
    """Return `("NOT_IMPLEMENTED", gap id)` for spiral or special seismic, else None (spec 0013 section 4.3)."""
    if isinstance(answer, ColumnScopeRequest) and answer.special_seismic:
        return ("NOT_IMPLEMENTED", _GAP_SEISMIC)
    if isinstance(answer, ColumnLayoutRequest) and any(row.transverse_kind == "spiral" for row in answer.sections):
        return ("NOT_IMPLEMENTED", _GAP_SPIRAL)
    return None
