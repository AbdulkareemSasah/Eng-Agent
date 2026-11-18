"""The change-set model of the edit cycle (spec 0007 section 4.3.1, 4.3.2).

Purpose: the engineer's answer to the change-set request, as data: items of nine v1 kinds whose engineering values
are a basis path or a number with a unit, and the refused kinds and variants as parseable models so that the check
can name their gap instead of the engineer meeting a schema error. No logic beyond validation.
Units: a literal value names its unit; the unit must have the dimension of the field (length, line load, area load,
dimensionless). The change-set input models also hold the value in the canonical unit as `value_<suffix>`, filled and
checked here by `eng_contract.units` (spec 0007 4.3.1); the check compares and converts by `eng_contract.units` too.
Errors: `pydantic.ValidationError` for every violated rule, naming the field (engine AC61: `INVALID_ARGUMENT`).
"""
# ruff: noqa: N815  # B-557: field names are fixed by the contract's unit suffixes (EC §4.7.2), e.g. value_kN_m

from typing import Annotated, Any, ClassVar, Literal, Self

from eng_contract.kinds.basis import BasisPath
from eng_contract.units import QUANTITY_KINDS, UNITS
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from eng_harness.kinds.edit_cycle import NONEMPTY, Label, canonical_number

__all__ = [
    "REFUSED_KIND_GAPS",
    "ChangeSetDraft",
    "ChangeSetSettings",
    "refused_gap",
]

REFUSED_KIND_GAPS = {
    "slab_section": "H-G1",
    "frame_section_define": "H-G1",
    "area_section_define": "H-G1",
    "material_define": "H-G1",
    "frame_point_load": "H-G2",
    "load_pattern_change": "OQ-G8",
    "load_pattern_delete": "OQ-G8",
    "seismic_parameters": "CG-1",
}
"""The gap id of each refused kind (spec 0007 4.3.2)."""
_DIRECTION_GAP = "H-G2"
_VARIANT_GAP = "H-G3"
_REFUSED_TYPES = {"load_pattern_add": ("superimposed_dead", "roof_live"), "load_combination_set": ("range",)}
_GRAVITY = "gravity"
_SETTINGS_KEY = "change_set_settings"
"""Validation-context key under which the caller passes `ChangeSetSettings`."""


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ChangeSetSettings(_M):
    """The size limit of a change set (a software setting from `harness.toml`; it has no default)."""

    max_items: Annotated[int, Field(ge=NONEMPTY)]


class BasisValue(_M):
    """A value taken from the design basis by path."""

    source: Literal["basis"]
    path: BasisPath


class _InputValue(_M):
    """A literal value of the engineer with its unit; the unit must have the dimension of `quantity`."""

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


class _CanonicalInput(_InputValue):
    """An input value that also holds its number in the canonical unit (`value_<suffix>`, spec 0007 4.3.1).

    A reference can reach a number only under a key with a unit suffix (contract 4.6.2), so the model fills the field
    from `value` and `unit` when it is absent and refuses a given one that differs from the conversion.
    """

    @model_validator(mode="before")
    @classmethod
    def _canonical(cls, data: Any) -> Any:
        given: dict[str, Any] = data if isinstance(data, dict) else {}
        exact = canonical_number(given.get("value"), given.get("unit"), cls.quantity)
        if exact is None:
            return data  # the field validators name the fault
        name = f"value{QUANTITY_KINDS[cls.quantity].suffix}"
        if given.get(name) is None:
            return {**given, name: exact}
        if given[name] != exact:
            raise ValueError(
                f"{name} {given[name]!r} is not {given['value']} {given['unit']} in the canonical unit ({exact})"
            )
        return data


class LengthInput(_CanonicalInput):
    """A literal length."""

    quantity = "length"
    value_mm: float | None = None


class LineLoadInput(_CanonicalInput):
    """A literal line load."""

    quantity = "line_load"
    value_kN_m: float | None = None


class AreaLoadInput(_CanonicalInput):
    """A literal area load."""

    quantity = "area_load"
    value_kPa: float | None = None


class RatioInput(_CanonicalInput):
    """A literal dimensionless number."""

    quantity = "dimensionless"
    value_ratio: float | None = None


LengthValue = Annotated[BasisValue | LengthInput, Field(discriminator="source")]
LineLoadValue = Annotated[BasisValue | LineLoadInput, Field(discriminator="source")]
AreaLoadValue = Annotated[BasisValue | AreaLoadInput, Field(discriminator="source")]
RatioValue = Annotated[BasisValue | RatioInput, Field(discriminator="source")]
_Names = Annotated[list[Label], Field(min_length=NONEMPTY)]


class _Item(_M):
    id: Label


class FrameSelect(_M):
    """Frames by story and section; at least one is named."""

    story: Label | None = None
    section: Label | None = None

    @model_validator(mode="after")
    def _some(self) -> Self:
        if self.story is None and self.section is None:
            raise ValueError("a selection names a story or a section")
        return self


class AreaSelect(FrameSelect):
    """Areas by story, section and kind."""

    area_kind: Literal["slab", "wall"] | None = None


class _FrameTargets(_Item):
    frames: _Names | None = None
    select: FrameSelect | None = None

    @model_validator(mode="after")
    def _one(self) -> Self:
        if (self.frames is None) == (self.select is None):
            raise ValueError("give frames or select, not both and not neither")
        return self


class _AreaTargets(_Item):
    areas: _Names | None = None
    select: AreaSelect | None = None

    @model_validator(mode="after")
    def _one(self) -> Self:
        if (self.areas is None) == (self.select is None):
            raise ValueError("give areas or select, not both and not neither")
        return self


class FrameSection(_FrameTargets):
    """Assign a section to frames."""

    kind: Literal["frame_section"]
    section: Label


class AreaSection(_AreaTargets):
    """Assign a section to areas."""

    kind: Literal["area_section"]
    section: Label


class WallSection(_Item):
    """Define a wall section."""

    kind: Literal["wall_section"]
    name: Label
    material: Label
    thickness: LengthValue
    shell_type: Literal["ShellThin", "ShellThick", "Membrane"]


class FrameUniformLoad(_FrameTargets):
    """A uniform line load on frames; a direction other than gravity is a refused variant."""

    kind: Literal["frame_uniform_load"]
    pattern: Label
    direction: Label
    w: LineLoadValue


class AreaUniformLoad(_AreaTargets):
    """A uniform area load; a direction other than gravity is a refused variant."""

    kind: Literal["area_uniform_load"]
    pattern: Label
    direction: Label
    q: AreaLoadValue


class LoadPatternAdd(_Item):
    """Add a load pattern; the types `superimposed_dead` and `roof_live` are refused variants."""

    kind: Literal["load_pattern_add"]
    name: Label
    type: Literal["dead", "live", "seismic", "wind", "snow", "other", "superimposed_dead", "roof_live"]
    self_weight: RatioValue


class ComboCase(_M):
    """The case of a combination term, in the shape of the contract's `CaseRef` (which no public module exports)."""

    case: Label
    case_type: Literal["load_pattern", "load_case", "load_combination"]
    step: Label | None = None


class ComboTerm(_M):
    """One case of a combination with its scale."""

    case: ComboCase
    scale: RatioValue


class LoadCombinationSet(_Item):
    """Replace or add a load combination; the type `range` is a refused variant."""

    kind: Literal["load_combination_set"]
    name: Label
    type: Literal["linear_add", "envelope", "absolute_add", "srss", "range"]
    items: Annotated[list[ComboTerm], Field(min_length=NONEMPTY)]


class LoadCombinationDelete(_Item):
    """Delete a load combination (always asked, engine 4.7)."""

    kind: Literal["load_combination_delete"]
    name: Label


class JointRestraints(_Item):
    """Set the restraints of joints."""

    kind: Literal["joint_restraints"]
    joints: _Names
    ux: bool
    uy: bool
    uz: bool
    rx: bool
    ry: bool
    rz: bool


class RefusedItem(_Item):
    """A refused kind (spec 0007 4.3.2): it parses with any other fields so that the check can name its gap."""

    model_config = ConfigDict(frozen=True, extra="allow", allow_inf_nan=False)
    kind: Literal[
        "slab_section",
        "frame_section_define",
        "area_section_define",
        "material_define",
        "frame_point_load",
        "load_pattern_change",
        "load_pattern_delete",
        "seismic_parameters",
    ]


Item = Annotated[
    FrameSection
    | AreaSection
    | WallSection
    | FrameUniformLoad
    | AreaUniformLoad
    | LoadPatternAdd
    | LoadCombinationSet
    | LoadCombinationDelete
    | JointRestraints
    | RefusedItem,
    Field(discriminator="kind"),
]


class ChangeSetDraft(_M):
    """The engineer's change set: `items` with unique ids; `max_items` applies when the caller passes the settings."""

    items: Annotated[list[Item], Field(min_length=NONEMPTY)]
    note: Label | None = None
    benchmark_request: Label | None = None

    @field_validator("items")
    @classmethod
    def _items(cls, items: list[Any], info: ValidationInfo) -> list[Any]:
        ids = [i.id for i in items]
        if len(ids) != len(set(ids)):
            raise ValueError("item ids must be unique")
        settings = (info.context or {}).get(_SETTINGS_KEY)
        if isinstance(settings, ChangeSetSettings) and len(items) > settings.max_items:
            raise ValueError(f"at most {settings.max_items} items")
        return items


def refused_gap(item: BaseModel) -> str | None:
    """Return the gap id when `item` is a refused kind or variant (spec 0007 4.3.2), else None."""
    kind = getattr(item, "kind", "")
    if kind in REFUSED_KIND_GAPS:
        return REFUSED_KIND_GAPS[kind]
    if getattr(item, "direction", _GRAVITY) != _GRAVITY:
        return _DIRECTION_GAP
    if getattr(item, "type", None) in _REFUSED_TYPES.get(kind, ()):
        return _VARIANT_GAP
    return None
