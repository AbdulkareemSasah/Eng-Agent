"""Payload models of the Revit harness kinds (plan 0011 T6; spec 0011 §4.5).

Units: suffixes name the unit (`_mm`, `_deg`). Errors: `pydantic.ValidationError`.
The calc kind `harness.frame_element_map/1` (§4.11) is registered by plan 0011 T12; this module only
names the registration point.
"""

from collections.abc import Iterable
from typing import Annotated, Any, Literal, Self

from eng_contract.quantity import Quantity
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StringConstraints, model_validator

__all__ = [
    "FRAME_ELEMENT_MAP_KIND_NAME",
    "REVIT_KINDS",
    "RevitGrids",
    "RevitLevels",
    "RevitStatus",
    "RevitStructure",
    "RevitWriteResult",
]

FRAME_ELEMENT_MAP_KIND_NAME = "harness.frame_element_map/1"
"""Registration point for the mapping calc kind (spec 0011 §4.11; plan 0011 T12)."""

_Str = Annotated[str, StringConstraints(min_length=1, max_length=200)]
_Category = Literal["column", "framing"]
_LocationKind = Literal["point", "curve"]
# Spec 0011 §4.8 / §4.11: length and angle roles are Quantity; material and etabs_link are
# string (or element id as StrictInt). Writes also allow integer / string / element id.
ParameterValue = Quantity | str | StrictInt


class _P(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


def _ordered(items: Iterable[Any], what: str) -> None:
    keys = list(items)
    if keys != sorted(set(keys)):
        raise ValueError(f"{what} must be sorted and unique")


class Point3(_P):
    """A point in model global coordinates, millimetres (spec 0011 §4.5).

    Local copy: `eng_contract.kinds.Point3` is not a public_modules export (same pattern as
    `_kinds.Name` vs `eng_contract.kinds._common.Name`).
    """

    x_mm: float
    y_mm: float
    z_mm: float


class RevitStatus(_P):
    """`harness.revit_status/1` (spec 0011 §4.5)."""

    title: _Str
    file_base_name: _Str
    revit_version: _Str
    is_workshared: StrictBool
    active_is_bound: StrictBool
    catalog_version: _Str
    ping_status: _Str


class LevelRow(_P):
    """One level: elevation in millimetres, three-decimal display from the server."""

    element_id: StrictInt
    name: _Str
    elevation_mm: float


class RevitLevels(_P):
    """`harness.revit_levels/1`: levels sorted by elevation (spec 0011 §4.5)."""

    levels: list[LevelRow]

    @model_validator(mode="after")
    def _sorted(self) -> Self:
        keys = [(row.elevation_mm, row.element_id) for row in self.levels]
        if keys != sorted(keys):
            raise ValueError("levels must be sorted by elevation_mm then element_id")
        ids = [row.element_id for row in self.levels]
        if ids != sorted(set(ids)):
            raise ValueError("levels must be unique by element_id")
        return self


class GridRow(_P):
    """One grid line; `start`/`end` may be null when the server omits them."""

    element_id: StrictInt
    name: _Str
    start: Point3 | None
    end: Point3 | None
    length_mm: float


class RevitGrids(_P):
    """`harness.revit_grids/1`: grids sorted by element_id (spec 0011 §4.5)."""

    grids: list[GridRow]

    @model_validator(mode="after")
    def _sorted(self) -> Self:
        _ordered((row.element_id for row in self.grids), "grids")
        return self


class ElementRow(_P):
    """One structural column or framing element of `harness.revit_structure/1`."""

    unique_id: _Str
    element_id: StrictInt
    category: _Category
    family: _Str
    type_id: StrictInt
    type_name: _Str
    level_id: StrictInt
    level_name: _Str
    location_kind: _LocationKind
    i: Point3 | None
    j: Point3 | None
    rotation_deg: float | None
    parameters: dict[str, ParameterValue]


class TypeRow(_P):
    """One family type with its instance ids and mapped parameter values."""

    type_id: StrictInt
    family: _Str
    name: _Str
    instance_ids: list[StrictInt]
    parameters: dict[str, ParameterValue]

    @model_validator(mode="after")
    def _instances_sorted(self) -> Self:
        if self.instance_ids != sorted(set(self.instance_ids)):
            raise ValueError("instance_ids must be sorted and unique")
        return self


class RevitStructure(_P):
    """`harness.revit_structure/1` (spec 0011 §4.5)."""

    elements: list[ElementRow]
    types: list[TypeRow]

    @model_validator(mode="after")
    def _sorted(self) -> Self:
        _ordered((row.unique_id for row in self.elements), "elements")
        type_ids = [row.type_id for row in self.types]
        if type_ids != sorted(set(type_ids)):
            raise ValueError("types must be sorted and unique by type_id")
        return self


class WriteTarget(_P):
    """One write target: element and/or type reference (spec 0011 §4.5)."""

    unique_id: _Str | None = None
    element_id: StrictInt | None = None
    type_id: StrictInt | None = None

    @model_validator(mode="after")
    def _has_ref(self) -> Self:
        if self.unique_id is None and self.element_id is None and self.type_id is None:
            raise ValueError("target needs unique_id, element_id or type_id")
        if self.element_id is not None and self.element_id == 0:
            raise ValueError("element_id must be non-zero when set")
        return self


class RevitWriteResult(_P):
    """`harness.revit_write_result/1` (spec 0011 §4.5)."""

    tool: _Str
    op_id: _Str
    targets: list[WriteTarget]
    reply_summary: _Str


REVIT_KINDS: dict[str, type[BaseModel]] = {
    "harness.revit_status/1": RevitStatus,
    "harness.revit_levels/1": RevitLevels,
    "harness.revit_grids/1": RevitGrids,
    "harness.revit_structure/1": RevitStructure,
    "harness.revit_write_result/1": RevitWriteResult,
}
