"""The change-set model of the model edit cycle (spec 0007 section 4.3).

Purpose: the shape of the engineer's answer to the change-set request, validated by Pydantic only; everything that
needs the model or the design basis is the calc `harness.change_set_check` (spec 0007 section 4.4.1).
Units: an input value carries its own unit, of the dimension of its field (length, line load, area load, ratio).
Errors: `pydantic.ValidationError` naming the field (the engine maps it to `INVALID_ARGUMENT`).
"""

from typing import Annotated, Any, ClassVar, Literal, Self

from eng_contract.units import QUANTITY_KINDS, UnitError, unit
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator, model_validator

from eng_harness.kinds.edit_cycle import LABEL_MAX, MAX_ITEMS, NONEMPTY, ChangeSetSettings

__all__ = ["ChangeSetDraft", "ChangeSetRequest", "ChangeSetSettings", "Label"]

Label = Annotated[str, StringConstraints(min_length=NONEMPTY, max_length=LABEL_MAX)]
"""A name or short text: 1 to 200 characters (spec 0007 section 5)."""
_Names = Annotated[list[Label], Field(min_length=NONEMPTY)]
_BasisPath = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$")]


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class BasisValue(_M):
    """A value taken from the design basis by path."""

    source: Literal["basis"]
    path: _BasisPath


class _Input(_M):
    """A number entered by the engineer with its unit; subclasses fix the quantity kind of the field."""

    source: Literal["input"]
    value: Annotated[float, Field(strict=True)]
    unit: str
    quantity: ClassVar[str]

    @field_validator("unit")
    @classmethod
    def _dimension(cls, symbol: str) -> str:
        try:
            found = unit(symbol)
        except UnitError as exc:
            raise ValueError(f"unknown unit {symbol!r}") from exc
        if found.dimension != QUANTITY_KINDS[cls.quantity].dimension:
            raise ValueError(f"unit {symbol!r} is not a {cls.quantity} unit")
        return symbol


class LengthInput(_Input):
    """A length."""

    quantity: ClassVar[str] = "length"


class LineLoadInput(_Input):
    """A line load."""

    quantity: ClassVar[str] = "line_load"


class AreaLoadInput(_Input):
    """An area load."""

    quantity: ClassVar[str] = "area_load"


class RatioInput(_Input):
    """A dimensionless ratio."""

    quantity: ClassVar[str] = "dimensionless"


type Length = Annotated[BasisValue | LengthInput, Field(discriminator="source")]
type LineLoad = Annotated[BasisValue | LineLoadInput, Field(discriminator="source")]
type AreaLoad = Annotated[BasisValue | AreaLoadInput, Field(discriminator="source")]
type Ratio = Annotated[BasisValue | RatioInput, Field(discriminator="source")]


def _select_some(*values: object) -> None:
    if all(v is None for v in values):
        raise ValueError("a selection needs at least one criterion")


class FrameSelect(_M):
    """Frames by story and section name."""

    story: Label | None = None
    section: Label | None = None

    @model_validator(mode="after")
    def _some(self) -> Self:
        _select_some(self.story, self.section)
        return self


class AreaSelect(FrameSelect):
    """Areas by story, section name and area kind."""

    area_kind: Literal["slab", "wall"] | None = None

    @model_validator(mode="after")
    def _some_area(self) -> Self:
        _select_some(self.story, self.section, self.area_kind)
        return self


class _Item(_M):
    id: Label


def _one_target(names: list[str] | None, select: object, field: str) -> None:
    if (names is None) == (select is None):
        raise ValueError(f"exactly one of {field} and select")


class FrameSection(_Item):
    """Assign a frame section."""

    kind: Literal["frame_section"]
    frames: _Names | None = None
    select: FrameSelect | None = None
    section: Label

    @model_validator(mode="after")
    def _target(self) -> Self:
        _one_target(self.frames, self.select, "frames")
        return self


class AreaSection(_Item):
    """Assign an area section."""

    kind: Literal["area_section"]
    areas: _Names | None = None
    select: AreaSelect | None = None
    section: Label

    @model_validator(mode="after")
    def _target(self) -> Self:
        _one_target(self.areas, self.select, "areas")
        return self


class WallSection(_Item):
    """Define a wall section."""

    kind: Literal["wall_section"]
    name: Label
    material: Label
    thickness: Length
    shell_type: Literal["ShellThin", "ShellThick", "Membrane"]


class FrameUniformLoad(_Item):
    """Uniform line load on frames; a direction other than gravity is a refused variant (H-G2)."""

    kind: Literal["frame_uniform_load"]
    frames: _Names | None = None
    select: FrameSelect | None = None
    pattern: Label
    direction: Label
    w: LineLoad

    @model_validator(mode="after")
    def _target(self) -> Self:
        _one_target(self.frames, self.select, "frames")
        return self


class AreaUniformLoad(_Item):
    """Uniform load on areas; a direction other than gravity is a refused variant (H-G2)."""

    kind: Literal["area_uniform_load"]
    areas: _Names | None = None
    select: AreaSelect | None = None
    pattern: Label
    direction: Label
    q: AreaLoad

    @model_validator(mode="after")
    def _target(self) -> Self:
        _one_target(self.areas, self.select, "areas")
        return self


class LoadPatternAdd(_Item):
    """Add a load pattern; `superimposed_dead` and `roof_live` are refused variants (H-G3)."""

    kind: Literal["load_pattern_add"]
    name: Label
    type: Literal["dead", "live", "seismic", "wind", "snow", "other", "superimposed_dead", "roof_live"]
    self_weight: Ratio


class CaseRef(_M):
    """A load pattern, case or combination."""

    case: Label
    case_type: Literal["load_pattern", "load_case", "load_combination"]
    step: Label | None = None


class ComboItem(_M):
    """One case of a combination with its scale factor."""

    case: CaseRef
    scale: Ratio


class LoadCombinationSet(_Item):
    """Add or replace a load combination; type `range` is a refused variant (H-G3)."""

    kind: Literal["load_combination_set"]
    name: Label
    type: Literal["linear_add", "envelope", "absolute_add", "srss", "range"]
    items: Annotated[list[ComboItem], Field(min_length=NONEMPTY)]


class LoadCombinationDelete(_Item):
    """Delete a load combination (always asked)."""

    kind: Literal["load_combination_delete"]
    name: Label


class JointRestraints(_Item):
    """Set joint restraints."""

    kind: Literal["joint_restraints"]
    joints: _Names
    ux: StrictBool
    uy: StrictBool
    uz: StrictBool
    rx: StrictBool
    ry: StrictBool
    rz: StrictBool


class _Refused(_Item):
    """A refused kind (spec 0007 section 4.3.2): it parses so the check can refuse it with its gap id."""

    model_config = ConfigDict(frozen=True, extra="allow", allow_inf_nan=False)


class RefusedSlabSection(_Refused):
    """Refused kind `slab_section`."""

    kind: Literal["slab_section"]


class RefusedFrameSectionDefine(_Refused):
    """Refused kind `frame_section_define`."""

    kind: Literal["frame_section_define"]


class RefusedAreaSectionDefine(_Refused):
    """Refused kind `area_section_define`."""

    kind: Literal["area_section_define"]


class RefusedMaterialDefine(_Refused):
    """Refused kind `material_define`."""

    kind: Literal["material_define"]


class RefusedFramePointLoad(_Refused):
    """Refused kind `frame_point_load`."""

    kind: Literal["frame_point_load"]


class RefusedLoadPatternChange(_Refused):
    """Refused kind `load_pattern_change`."""

    kind: Literal["load_pattern_change"]


class RefusedLoadPatternDelete(_Refused):
    """Refused kind `load_pattern_delete`."""

    kind: Literal["load_pattern_delete"]


class RefusedSeismicParameters(_Refused):
    """Refused kind `seismic_parameters`."""

    kind: Literal["seismic_parameters"]


ChangeItem = Annotated[
    FrameSection
    | AreaSection
    | WallSection
    | FrameUniformLoad
    | AreaUniformLoad
    | LoadPatternAdd
    | LoadCombinationSet
    | LoadCombinationDelete
    | JointRestraints
    | RefusedSlabSection
    | RefusedFrameSectionDefine
    | RefusedAreaSectionDefine
    | RefusedMaterialDefine
    | RefusedFramePointLoad
    | RefusedLoadPatternChange
    | RefusedLoadPatternDelete
    | RefusedSeismicParameters,
    Field(discriminator="kind"),
]


class ChangeSetDraft(_M):
    """The engineer's change set: items with unique ids, an optional note and benchmark request id."""

    items: Annotated[list[ChangeItem], Field(min_length=NONEMPTY, max_length=MAX_ITEMS)]
    note: Label | None = None
    benchmark_request: Label | None = None

    @field_validator("items")
    @classmethod
    def _unique_ids(cls, items: list[Any]) -> list[Any]:
        ids = [i.id for i in items]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate item id")
        return items


class ChangeSetRequest(_M):
    """The data request asked once per cycle (`x-eng-input: data`); its answer is stored as engineer input."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", allow_inf_nan=False, json_schema_extra={"x-eng-input": "data"}
    )

    change_set: ChangeSetDraft
