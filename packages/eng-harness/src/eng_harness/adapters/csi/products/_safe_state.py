"""SAFE table-backed readers and model-state reader (plan 0008 T4, T5; spec 0008 AC9 to AC12, 4.4, 4.5).

Host field keys are those of `_safe_tables.toml` (SAFE 22 reference). Present-unit values are converted only through
`eng_contract.units.csi_unit_system`. PropType mapping and the `SECTION_TYPE_NOT_MAPPED` info issue follow AC11; soil
support stiffness uses the unit-weight dimension (spec Q3). The state reader covers grids, points, areas, frames, the
load set, joint loads, soil supports and status (AC9); truncation is `LIMIT_EXCEEDED` (AC10).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.issues import ModelIssue, Severity
from eng_contract.kinds.model import (
    AreaKind,
    AreaSection,
    AreaSectionKind,
    Material,
    Materials,
    MaterialType,
    Sections,
)
from eng_contract.units import convert, csi_unit_system
from eng_contract.verdicts import Subject, SubjectKind
from pydantic import BaseModel

from eng_harness._kinds import (
    JointLoad,
    JointLoads,
    ModelPoint,
    ModelPoints,
    SafeSoilAssignment,
    SafeSoilProperty,
    SafeSoilSupports,
)
from eng_harness.adapters.csi import _tables, products
from eng_harness.adapters.csi._replies import areas, frames, grids, load_set, model_status
from eng_harness.adapters.csi._state import LIST_LIMIT, READ_UNITS, StateRead, fingerprint
from eng_harness.servers import CallEffect

__all__ = [
    "SafeSoilAssignment",
    "SafeSoilProperty",
    "SafeSoilSupports",
    "SafeStateReader",
    "fingerprint",
    "joint_loads_from_rows",
    "materials_from_rows",
    "points_from_items",
    "sections_from_rows",
    "soil_supports_from_rows",
]

HostCall = Callable[[str, dict[str, Any], CallEffect], Awaitable[dict[str, Any]]]

_LISTS = (  # (name, tool, takes the units token): SAFE read order of spec 0008 section 4.4 (no stories)
    ("grids", "csi_list_grids", True),
    ("points", "csi_list_points", True),
    ("frames", "csi_list_frames", True),
    ("areas", "csi_list_areas", True),
    ("patterns", "csi_list_load_patterns", False),
    ("combos", "csi_list_load_combos", False),
)
_TABLES = (
    "pattern_defs",
    "combo_defs",
    "joint_loads",
    "slab_sections",
    "materials_general",
    "materials_mechanical",
    "materials_concrete",
    "soil_properties",
    "soil_assignments",
)
_SOURCES = {  # host reads behind each kind: what the fingerprint covers (spec 0008 section 4.4, 0002 section 4.6.4)
    "model.grid_system/1": ("grids",),
    "harness.model_points/1": ("points",),
    "model.frame_placements/1": ("frames",),
    "model.area_placements/1": ("areas",),
    "model.sections/1": ("slab_sections",),
    "model.materials/1": ("materials_general", "materials_mechanical", "materials_concrete"),
    "model.load_set/1": ("patterns", "combos", "pattern_defs", "combo_defs"),
    "harness.joint_loads/1": ("joint_loads",),
    "harness.safe_soil_supports/1": ("soil_properties", "soil_assignments"),
}

# PropType values that become `model.sections/1` kind `slab` (spec 0008 AC11).
# Ribbed, Waffle and any other type are left out with info issue SECTION_TYPE_NOT_MAPPED.
_SLAB_TYPES = frozenset({"slab", "drop", "stiff", "mat", "footing"})


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise TypeError(f"numeric table cell expected, got {type(value).__name__}")
    return float(value)


def _length_mm(value: object, units: str) -> float:
    return convert(_as_float(value), csi_unit_system(units).length, "mm")


def _stress_mpa(value: object, units: str) -> float:
    return convert(_as_float(value), csi_unit_system(units).stress, "MPa")


def _unit_weight(value: object, units: str) -> float:
    return convert(_as_float(value), csi_unit_system(units).unit_weight, "kN/m3")


def _mapped(table: str, rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    return _tables.map_rows(table, rows).rows


def sections_from_rows(rows: Sequence[Mapping[str, Any]], units: str) -> tuple[Sections, list[ModelIssue]]:
    """Build `model.sections/1` from `Slab Property Definitions` rows (AC11)."""
    mapped = _mapped("Slab Property Definitions", rows)
    area_sections: list[AreaSection] = []
    issues: list[ModelIssue] = []
    for row in mapped:
        name = str(row["name"])
        prop = str(row["prop_type"]).strip()
        key = prop.lower().replace(" ", "")
        if key not in _SLAB_TYPES:
            issues.append(
                ModelIssue(
                    severity=Severity.INFO,
                    code="SECTION_TYPE_NOT_MAPPED",
                    subject=Subject(kind=SubjectKind.SECTION, id=name),
                    message=f"slab property type {prop!r} is not mapped to model.sections/1",
                )
            )
            continue
        area_sections.append(
            AreaSection(
                name=name,
                material=str(row["material"]),
                kind=AreaSectionKind.SLAB,
                thickness_mm=_length_mm(row["thickness"], units),
            )
        )
    return Sections(frame_sections=[], area_sections=area_sections), issues


def materials_from_rows(
    general: Sequence[Mapping[str, Any]],
    mechanical: Sequence[Mapping[str, Any]],
    concrete: Sequence[Mapping[str, Any]],
    units: str,
) -> Materials:
    """Build `model.materials/1` from the three material tables (AC11)."""
    gen = {str(row["material"]): row for row in _mapped("Material Properties - General", general)}
    mech = {
        str(row["material"]): row for row in _mapped("Material Properties - Basic Mechanical Properties", mechanical)
    }
    conc = {str(row["material"]): row for row in _mapped("Material Properties - Concrete Data", concrete)}
    materials: list[Material] = []
    for name, row in gen.items():
        host_type = str(row["type"]).strip().lower().replace(" ", "")
        is_concrete = host_type == "concrete"
        body = mech[name]
        materials.append(
            Material(
                name=name,
                type=MaterialType.CONCRETE if is_concrete else MaterialType.OTHER,
                E_MPa=_stress_mpa(body["e1"], units),
                nu_ratio=_as_float(body["u12"]),
                gamma_kN_m3=_unit_weight(body["unit_weight"], units),
                fc_MPa=_stress_mpa(conc[name]["fc"], units) if is_concrete else None,
            )
        )
    return Materials(materials=materials)


def soil_supports_from_rows(
    properties: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    units: str,
) -> SafeSoilSupports:
    """Build `harness.safe_soil_supports/1` from the area-spring tables (AC12)."""
    props = [
        SafeSoilProperty(
            name=str(row["name"]),
            stiffness_option=str(row["stiff_opt"]),
            u1_kn_m3=_unit_weight(row["stiff_u1"], units),
            u2_kn_m3=_unit_weight(row["stiff_u2"], units),
            u3_kn_m3=_unit_weight(row["stiff_u3"], units),
            nonlinear_u3=str(row["nonlin_opt3"]),
        )
        for row in _mapped("Spring Property Definitions - Area Springs", properties)
    ]
    assigned: list[SafeSoilAssignment] = []
    for row in _mapped("Area Assignments - Area Springs", assignments):
        raw = row["spring_prop"]
        text = str(raw).strip() if raw is not None else ""
        prop_name = None if text.lower() == "none" or text == "" else text
        assigned.append(SafeSoilAssignment(area=str(row["unique_name"]), property=prop_name))
    return SafeSoilSupports(properties=props, assignments=assigned)


def _force_kn(value: object, units: str) -> float:
    return convert(_as_float(value), csi_unit_system(units).force, "kN")


def _moment_knm(value: object, units: str) -> float:
    return convert(_as_float(value), csi_unit_system(units).moment, "kN.m")


def _punch_mm(value: object, units: str) -> float | None:
    """Punching dimensions: present length to mm; null when absent, non-positive or unusable (spec 0008 section 4.3)."""
    if value is None or value == "":
        return None
    length = _length_mm(value, units)
    return length if length > 0 else None


def points_from_items(items: Sequence[Mapping[str, Any]], units: str) -> ModelPoints:
    """Build `harness.model_points/1` from `csi_list_points` (spec 0008 section 4.4)."""
    points = [
        ModelPoint(
            name=str(row["name"]),
            x_mm=_length_mm(row["x"], units),
            y_mm=_length_mm(row["y"], units),
            z_mm=_length_mm(row["z"], units),
        )
        for row in items
    ]
    return ModelPoints(points=points)


def joint_loads_from_rows(rows: Sequence[Mapping[str, Any]], units: str) -> JointLoads:
    """Build `harness.joint_loads/1` from `Joint Loads Assignments - Force` (spec 0008 section 4.3, 4.4)."""
    mapped = _mapped("Joint Loads Assignments - Force", rows)
    loads = [
        JointLoad(
            joint=str(row["unique_name"]),
            pattern=str(row["load_pattern"]),
            fx_kn=_force_kn(row["fx"], units),
            fy_kn=_force_kn(row["fy"], units),
            fz_kn=_force_kn(row["fz"], units),
            mx_knm=_moment_knm(row["mx"], units),
            my_knm=_moment_knm(row["my"], units),
            mz_knm=_moment_knm(row["mz"], units),
            punch_x_mm=_punch_mm(row["x_dim"], units),
            punch_y_mm=_punch_mm(row["y_dim"], units),
        )
        for row in mapped
    ]
    return JointLoads(axes="global", loads=loads)


class SafeStateReader:
    """Reads the SAFE model-state set through `call` (spec 0008 section 4.4; plan 0008 T5)."""

    def __init__(self, *, product: str, call: HostCall) -> None:
        self._product, self._call = product, call
        self._tables = products.profile(product).tables

    async def read(self, pid: int, model_path: Path | None) -> StateRead:
        """Read the instance `pid`; `model_path` names the status's file (its base name only)."""
        target = {"target": {"product": self._product, "pid": pid}}
        info = await self._call("csi_model_info", target, CallEffect.READ)
        rows: dict[str, list[dict[str, Any]]] = {}
        for name, tool, tokened in _LISTS:
            arguments = {**target, "limit": LIST_LIMIT, **({"units": READ_UNITS} if tokened else {})}
            rows[name] = await self._rows(tool, "items", arguments, tool)
        for name in _TABLES:
            arguments = {**target, "table": self._tables[name], "row_limit": LIST_LIMIT}
            rows[name] = await self._rows("csi_db_table_read", "rows", arguments, self._tables[name])
        after = await self._call("csi_model_info", target, CallEffect.READ)
        if after.get("units") != info.get("units"):
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED,
                "the model's units changed during the read",
                precondition=Precondition.units_verified,
                expected={"units": info.get("units")},
                received=after.get("units"),
            )
        try:
            status = model_status(info, model_path)
            present = status.units
            sections, _issues = sections_from_rows(rows["slab_sections"], present)
            loads = load_set(
                rows["patterns"],
                rows["combos"],
                rows["pattern_defs"],
                rows["combo_defs"],
                [],  # frame_loads: not read in v1 (spec 0008 section 4.4)
                [],  # area_loads: not read in v1
                present,
            )
            # Every SAFE area is a slab (spec 0008 section 4.4); walls are not read.
            section_kinds = {str(row.get("section", "")): AreaKind.SLAB.value for row in rows["areas"]}
            payloads: dict[str, BaseModel] = {
                "model.grid_system/1": grids(rows["grids"], READ_UNITS),
                "harness.model_points/1": points_from_items(rows["points"], READ_UNITS),
                "model.frame_placements/1": frames(rows["frames"], READ_UNITS),
                "model.area_placements/1": areas(rows["areas"], READ_UNITS, section_kinds),
                "model.sections/1": sections,
                "model.materials/1": materials_from_rows(
                    rows["materials_general"],
                    rows["materials_mechanical"],
                    rows["materials_concrete"],
                    present,
                ),
                "model.load_set/1": loads,
                "harness.joint_loads/1": joint_loads_from_rows(rows["joint_loads"], present),
                "harness.safe_soil_supports/1": soil_supports_from_rows(
                    rows["soil_properties"], rows["soil_assignments"], present
                ),
            }
        except (KeyError, TypeError, ValueError) as error:
            raise ContractError(
                ErrorCode.HOST_ERROR,
                "a reply of the model-state read has rows the neutral kinds cannot map",
                retryable=False,
                host_code="UNEXPECTED_REPLY",
                field="rows",
            ) from error
        host = {kind: {name: rows[name] for name in names} for kind, names in _SOURCES.items()}
        return StateRead(payloads, status, fingerprint(host, status.object_counts))

    async def _rows(self, tool: str, field: str, arguments: dict[str, Any], what: str) -> list[dict[str, Any]]:
        body = await self._call(tool, arguments, CallEffect.READ)
        rows = body.get(field)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ContractError(
                ErrorCode.HOST_ERROR,
                f"the reply of {what} has no usable {field}",
                retryable=False,
                host_code="UNEXPECTED_REPLY",
                host_method=tool,
                field=field,
            )
        if body.get("truncated"):
            raise ContractError(
                ErrorCode.LIMIT_EXCEEDED, f"{what} was truncated at {LIST_LIMIT} rows", received=len(rows)
            )
        return rows
