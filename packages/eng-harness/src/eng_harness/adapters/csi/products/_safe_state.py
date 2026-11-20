"""SAFE table-backed readers for sections, materials and soil supports (plan 0008 T4; spec 0008 AC11, AC12, 4.4, 4.5).

Host field keys are those of `_safe_tables.toml` (SAFE 22 reference). Present-unit values are converted only through
`eng_contract.units.csi_unit_system`. PropType mapping and the `SECTION_TYPE_NOT_MAPPED` info issue follow AC11; soil
support stiffness uses the unit-weight dimension (spec Q3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from eng_contract.issues import ModelIssue, Severity
from eng_contract.kinds.model import (
    AreaSection,
    AreaSectionKind,
    Material,
    Materials,
    MaterialType,
    Sections,
)
from eng_contract.units import convert, csi_unit_system
from eng_contract.verdicts import Subject, SubjectKind

from eng_harness._kinds import SafeSoilAssignment, SafeSoilProperty, SafeSoilSupports
from eng_harness.adapters.csi import _tables

__all__ = [
    "SafeSoilAssignment",
    "SafeSoilProperty",
    "SafeSoilSupports",
    "materials_from_rows",
    "sections_from_rows",
    "soil_supports_from_rows",
]

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
