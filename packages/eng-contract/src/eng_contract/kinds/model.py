"""The `model.*` kinds, version 1 (spec 4.10.2): the neutral description of a structural model.

Units: millimetres, degrees, MPa, kN/m3, kN/m and kPa as the field suffixes say; `_ratio` fields have no unit.
Errors: `pydantic.ValidationError` for every violated rule. These kinds are frozen: any change is a new version.
"""
# ruff: noqa: N815  # B-020: field names are fixed by spec 4.10.2 (symbol plus unit suffix, e.g. fc_MPa, w_kN_m)

from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, model_validator

from eng_contract.kinds._common import CaseRef, CaseType, Name, Payload, Point3, Positive, require_unique

_Opt = Annotated[float, Field(gt=0)] | None


class Story(Payload):
    """One story; `similar_to` names another story of the list."""

    name: Name
    elevation_mm: float
    height_mm: Positive
    master_story: StrictBool
    similar_to: Name | None = None


class Stories(Payload):
    """`model.stories/1`: stories from the bottom up, with strictly increasing elevations above the base."""

    base_elevation_mm: float
    stories: list[Story]

    @model_validator(mode="after")
    def _check(self) -> Self:
        require_unique(self.stories, "name", "story names")
        elevations = [self.base_elevation_mm, *(s.elevation_mm for s in self.stories)]
        if any(low >= high for low, high in pairwise(elevations)):
            raise ValueError("story elevations must be strictly increasing and above base elevation")
        names = {s.name for s in self.stories}
        if any(s.similar_to is not None and s.similar_to not in names for s in self.stories):
            raise ValueError("similar_to must name a story of the list")
        return self


class Axis(StrEnum):
    """Direction a grid line is perpendicular to."""

    X = "x"
    Y = "y"


class GridLine(Payload):
    """A grid line at `coordinate_mm` along its axis."""

    id: Name
    axis: Axis
    coordinate_mm: float
    visible: StrictBool


class GridSystem1(Payload):
    """One Cartesian grid system."""

    name: Name
    origin_x_mm: float
    origin_y_mm: float
    rotation_deg: float
    lines: list[GridLine]

    @model_validator(mode="after")
    def _check(self) -> Self:
        require_unique(self.lines, "id", "grid line ids")
        return self


class GridSystem(Payload):
    """`model.grid_system/1`: Cartesian grid systems only (other grid types are a later kind version)."""

    systems: list[GridSystem1]

    @model_validator(mode="after")
    def _check(self) -> Self:
        require_unique(self.systems, "name", "grid system names")
        return self


class FrameKind(StrEnum):
    """Role of a frame member."""

    COLUMN = "column"
    BEAM = "beam"
    BRACE = "brace"
    OTHER = "other"


class Frame(Payload):
    """A frame member between points `i` and `j` (which must differ)."""

    id: Name
    kind: FrameKind
    section: Name
    i_joint: Name | None = None
    j_joint: Name | None = None
    i: Point3
    j: Point3
    story: Name | None = None
    rotation_deg: float

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.i == self.j:
            raise ValueError("end points i and j must differ")
        return self


class FramePlacements(Payload):
    """`model.frame_placements/1`."""

    frames: list[Frame]

    @model_validator(mode="after")
    def _check(self) -> Self:
        require_unique(self.frames, "id", "frame ids")
        return self


class AreaKind(StrEnum):
    """Role of an area object."""

    SLAB = "slab"
    WALL = "wall"
    DECK = "deck"
    OTHER = "other"


class Area(Payload):
    """An area object bounded by at least three points."""

    id: Name
    kind: AreaKind
    section: Name
    points: Annotated[list[Point3], Field(min_length=3)]
    joints: list[Name] | None = None
    story: Name | None = None


class AreaPlacements(Payload):
    """`model.area_placements/1`."""

    areas: list[Area]

    @model_validator(mode="after")
    def _check(self) -> Self:
        require_unique(self.areas, "id", "area ids")
        return self


class Rectangular(Payload):
    """Rectangular section, width `b_mm` and depth `h_mm`."""

    type: Literal["rectangular"]
    b_mm: Positive
    h_mm: Positive


class Circular(Payload):
    """Circular section of diameter `D_mm`."""

    type: Literal["circular"]
    D_mm: Positive


class OtherShape(Payload):
    """A shape that the host names and this contract does not describe."""

    type: Literal["other"]
    host_shape: Name


class FrameSection(Payload):
    """A named frame section."""

    name: Name
    material: Name
    shape: Annotated[Rectangular | Circular | OtherShape, Field(discriminator="type")]


class AreaSectionKind(StrEnum):
    """Kind of an area section."""

    SLAB = "slab"
    WALL = "wall"
    DECK = "deck"


class AreaSection(Payload):
    """A named area section of thickness `thickness_mm`."""

    name: Name
    material: Name
    kind: AreaSectionKind
    thickness_mm: Positive


class Sections(Payload):
    """`model.sections/1`."""

    frame_sections: list[FrameSection]
    area_sections: list[AreaSection]

    @model_validator(mode="after")
    def _check(self) -> Self:
        require_unique(self.frame_sections, "name", "frame section names")
        require_unique(self.area_sections, "name", "area section names")
        return self


class MaterialType(StrEnum):
    """Kind of material."""

    CONCRETE = "concrete"
    REBAR = "rebar"
    STEEL = "steel"
    OTHER = "other"


class Material(Payload):
    """A material; the strengths that its type needs must be present (concrete: fc; rebar, steel: fy)."""

    name: Name
    type: MaterialType
    E_MPa: Positive
    nu_ratio: Annotated[float, Field(ge=0, lt=0.5)]
    gamma_kN_m3: Annotated[float, Field(ge=0)]
    fc_MPa: _Opt = None
    fy_MPa: _Opt = None
    fu_MPa: _Opt = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.type is MaterialType.CONCRETE and self.fc_MPa is None:
            raise ValueError("fc_MPa is required for concrete")
        if self.type in (MaterialType.REBAR, MaterialType.STEEL) and self.fy_MPa is None:
            raise ValueError("fy_MPa is required for rebar and steel")
        return self


class Materials(Payload):
    """`model.materials/1`."""

    materials: list[Material]

    @model_validator(mode="after")
    def _check(self) -> Self:
        require_unique(self.materials, "name", "material names")
        return self


class PatternType(StrEnum):
    """Type of a load pattern."""

    DEAD = "dead"
    SUPERIMPOSED_DEAD = "superimposed_dead"
    LIVE = "live"
    ROOF_LIVE = "roof_live"
    WIND = "wind"
    SEISMIC = "seismic"
    SNOW = "snow"
    OTHER = "other"


class CombinationType(StrEnum):
    """How a combination adds its items."""

    LINEAR_ADD = "linear_add"
    ENVELOPE = "envelope"
    ABSOLUTE_ADD = "absolute_add"
    SRSS = "srss"
    RANGE = "range"


class LoadDirection(StrEnum):
    """Direction of a uniform load."""

    GRAVITY = "gravity"
    GLOBAL_X = "global_x"
    GLOBAL_Y = "global_y"
    GLOBAL_Z = "global_z"
    LOCAL_1 = "local_1"
    LOCAL_2 = "local_2"
    LOCAL_3 = "local_3"


class LoadPattern(Payload):
    """A load pattern with its self-weight multiplier."""

    name: Name
    type: PatternType
    self_weight_ratio: Annotated[float, Field(ge=0)]


class CombinationItem(Payload):
    """One case of a combination with its scale factor."""

    case: CaseRef
    scale_ratio: float


class Combination(Payload):
    """A load combination of at least one item; it may not reference itself."""

    name: Name
    type: CombinationType
    items: Annotated[list[CombinationItem], Field(min_length=1)]


class FrameLoad(Payload):
    """A uniform load over the full length of a frame."""

    frame: Name
    pattern: Name
    direction: LoadDirection
    w_kN_m: float


class AreaLoad(Payload):
    """A uniform load over an area."""

    area: Name
    pattern: Name
    direction: LoadDirection
    q_kPa: float


class LoadSet(Payload):
    """`model.load_set/1`: every referenced pattern must exist in `patterns`."""

    patterns: list[LoadPattern]
    combinations: list[Combination]
    frame_loads: list[FrameLoad]
    area_loads: list[AreaLoad]

    @model_validator(mode="after")
    def _check(self) -> Self:
        require_unique(self.patterns, "name", "pattern names")
        require_unique(self.combinations, "name", "combination names")
        known = {p.name for p in self.patterns}
        used = [load.pattern for load in self.frame_loads] + [load.pattern for load in self.area_loads]
        for combo in self.combinations:
            for item in combo.items:
                if item.case.case_type is CaseType.LOAD_COMBINATION and item.case.case == combo.name:
                    raise ValueError(f"combination {combo.name!r} references itself")
                if item.case.case_type is CaseType.LOAD_PATTERN:
                    used.append(item.case.case)
        if unknown := sorted(set(used) - known):
            raise ValueError(f"unknown pattern: {unknown}")
        return self


class JointRestraint(Payload):
    """Restrained degrees of freedom of one joint (true = restrained)."""

    joint: Name
    ux: StrictBool
    uy: StrictBool
    uz: StrictBool
    rx: StrictBool
    ry: StrictBool
    rz: StrictBool


class JointRestraints(Payload):
    """`model.joint_restraints/1`."""

    joints: list[JointRestraint]

    @model_validator(mode="after")
    def _check(self) -> Self:
        require_unique(self.joints, "joint", "restrained joints")
        return self
