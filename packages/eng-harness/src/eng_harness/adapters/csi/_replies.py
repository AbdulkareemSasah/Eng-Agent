"""CSI replies mapped to neutral and harness kinds (plan 0002 T11; spec 0002 section 4.6.4)."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from eng_contract.kinds.model import (
    AreaKind,
    AreaPlacements,
    Axis,
    Combination,
    CombinationType,
    FrameKind,
    FramePlacements,
    GridLine,
    GridSystem,
    GridSystem1,
    JointRestraint,
    JointRestraints,
    LoadDirection,
    LoadPattern,
    LoadSet,
    PatternType,
    Stories,
    Story,
)
from eng_contract.units import convert, csi_unit_system
from pydantic import BaseModel, ConfigDict, Field

_HOST_KIND = "harness.csi_model_status/1"


class CsiModelStatus(BaseModel):
    """`harness.csi_model_status/1` (spec 0002 section 4.6.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    units: str
    locked: bool | None = None
    object_counts: dict[str, int] = Field(default_factory=dict)
    program_version: str = ""
    file_name: str = Field(min_length=1)


CSI_KINDS = {_HOST_KIND: CsiModelStatus}

_PATTERN = {
    "dead": PatternType.DEAD,
    "live": PatternType.LIVE,
    "wind": PatternType.WIND,
    "quake": PatternType.SEISMIC,
    "seismic": PatternType.SEISMIC,
    "snow": PatternType.SNOW,
    "superdead": PatternType.SUPERIMPOSED_DEAD,
    "other": PatternType.OTHER,
}
_COMBO = {
    0: CombinationType.LINEAR_ADD,
    1: CombinationType.ENVELOPE,
    2: CombinationType.ABSOLUTE_ADD,
    3: CombinationType.SRSS,
}
_AREA = {"slab": AreaKind.SLAB, "wall": AreaKind.WALL, "deck": AreaKind.DECK}


def _length(value: float, units: str) -> float:
    # eng-contract spec 4.7.4: `csi_unit_system(units).length` is the CSI present-length symbol for the token.
    return convert(value, csi_unit_system(units).length, "mm")


def _area_load(value: float, units: str) -> float:
    # eng-contract spec 4.7.4: `stress` is force/length² in the reply's present units; kind fields use `kPa`.
    return convert(value, csi_unit_system(units).stress, "kPa")


def _line_load(value: float, units: str) -> float:
    # eng-contract spec 4.7.4: `line_load` is force/length in the reply's present units; kind fields use `kN/m`.
    return convert(value, csi_unit_system(units).line_load, "kN/m")


def _point(raw: Sequence[float], units: str) -> dict[str, float]:
    x, y, z = (float(raw[0]), float(raw[1]), float(raw[2])) if len(raw) >= 3 else (0.0, 0.0, 0.0)
    return {"x_mm": _length(x, units), "y_mm": _length(y, units), "z_mm": _length(z, units)}


def host_stories(items: list[dict[str, Any]]) -> dict[str, Any]:
    rows = sorted(items, key=lambda row: float(row.get("elevation", 0.0)))
    return {"base_elevation": rows[0].get("elevation", 0.0) if rows else 0.0, "stories": rows}


def stories(items: list[dict[str, Any]], units: str) -> Stories:
    rows = sorted(items, key=lambda row: float(row["elevation"]))
    if rows:
        foot = float(rows[0]["elevation"]) - float(rows[0]["height"])
        base = _length(foot, units)
    else:
        base = 0.0
    return Stories(
        base_elevation_mm=base,
        stories=[
            Story(
                name=str(row["name"]),
                elevation_mm=_length(float(row["elevation"]), units),
                height_mm=_length(float(row["height"]), units),
                master_story=bool(row.get("is_master", False)),
                similar_to=None if row.get("similar_to") in (None, "") else str(row["similar_to"]),
            )
            for row in rows
        ],
    )


def _grid_lines(lines: list[dict[str, Any]], axis: Axis, units: str) -> list[GridLine]:
    return [
        GridLine(
            id=str(row["id"]),
            axis=axis,
            coordinate_mm=_length(float(row["ordinate"]), units),
            visible=bool(row.get("visible", True)),
        )
        for row in lines
    ]


def host_grid(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "systems": [
            row
            for row in items
            if str(row.get("type", "Cartesian")).lower() == "cartesian" and {"name", "x_lines", "y_lines"} <= row.keys()
        ]
    }


def grids(items: list[dict[str, Any]], units: str) -> GridSystem:
    systems: list[GridSystem1] = []
    for row in items:
        if str(row.get("type", "Cartesian")).lower() != "cartesian":
            continue
        origin = row.get("origin") or [0.0, 0.0]
        systems.append(
            GridSystem1(
                name=str(row["name"]),
                origin_x_mm=_length(float(origin[0]), units),
                origin_y_mm=_length(float(origin[1]), units),
                rotation_deg=float(row.get("rotation_deg", 0.0)),
                lines=_grid_lines(list(row.get("x_lines") or []), Axis.X, units)
                + _grid_lines(list(row.get("y_lines") or []), Axis.Y, units),
            )
        )
    return GridSystem(systems=systems)


def host_frames(items: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [{"id": str(row.get("label") or row.get("name")), **row} for row in items]
    return {"frames": sorted(rows, key=lambda row: row["id"])}


def frames(items: list[dict[str, Any]], units: str) -> FramePlacements:
    rows = []
    for row in items:
        label = str(row.get("label") or row.get("name"))
        rows.append(
            {
                "id": label,
                "kind": FrameKind.OTHER,
                "section": str(row["section"]),
                "i_joint": None,
                "j_joint": None,
                "i": _point(row["point1"], units),
                "j": _point(row["point2"], units),
                "story": None if row.get("story") in (None, "") else str(row["story"]),
                "rotation_deg": 0.0,
            }
        )
    return FramePlacements.model_validate({"frames": rows})


def host_areas(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"areas": sorted([{"id": str(row["name"]), **row} for row in items], key=lambda row: row["id"])}


def areas(items: list[dict[str, Any]], units: str, sections: Mapping[str, str]) -> AreaPlacements:
    rows = []
    for row in items:
        kind = _AREA.get(str(sections.get(str(row.get("section", "")), "other")).lower(), AreaKind.OTHER)
        rows.append(
            {
                "id": str(row["name"]),
                "kind": kind,
                "section": str(row["section"]),
                "points": [_point(point, units) for point in row["points"]],
                "joints": None,
                "story": None,
            }
        )
    return AreaPlacements.model_validate({"areas": rows})


def _pattern_type(text: str) -> PatternType:
    return _PATTERN.get(text.strip().lower().replace(" ", ""), PatternType.OTHER)


_TEXT_COMBO = {
    "linearadd": CombinationType.LINEAR_ADD,
    "linear_add": CombinationType.LINEAR_ADD,
    "envelope": CombinationType.ENVELOPE,
    "absoluteadd": CombinationType.ABSOLUTE_ADD,
    "srss": CombinationType.SRSS,
}


def _combo_type(value: object) -> CombinationType:
    if isinstance(value, int):
        return _COMBO.get(value, CombinationType.LINEAR_ADD)
    return _TEXT_COMBO.get(str(value).lower().replace(" ", ""), CombinationType.LINEAR_ADD)


def host_load_set(
    patterns: list[dict[str, Any]],
    combos: list[dict[str, Any]],
    frame_rows: list[dict[str, Any]],
    area_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "patterns": sorted(patterns, key=lambda row: str(row["name"])),
        "combinations": sorted(combos, key=lambda row: str(row["name"])),
        "frame_loads": frame_rows,
        "area_loads": area_rows,
    }


def load_set(
    patterns: list[dict[str, Any]],
    combos: list[dict[str, Any]],
    pattern_table: list[dict[str, Any]],
    combo_table: list[dict[str, Any]],
    frame_rows: list[dict[str, Any]],
    area_rows: list[dict[str, Any]],
    units: str,
) -> LoadSet:
    merged = {str(row["name"]): row for row in patterns}
    for row in pattern_table:
        merged.setdefault(str(row["Name"]), {"name": str(row["Name"]), "type": row.get("Type", "Other")})
    patterns_out = [
        LoadPattern(
            name=str(row["name"]),
            type=_pattern_type(str(row.get("type", row.get("Type", "Other")))),
            self_weight_ratio=float(row.get("self_weight", row.get("SelfWtMultpl", 0.0))),
        )
        for row in merged.values()
    ]
    combos_out: list[Combination] = []
    table_types = {str(row["Name"]): row.get("Type", "Linear Add") for row in combo_table}
    for row in combos:
        name = str(row["name"])
        items = [
            {
                "case": {"case": str(part["name"]), "case_type": "load_pattern", "step": None},
                "scale_ratio": float(part["factor"]),
            }
            for part in row.get("items", [])
        ] or [{"case": {"case": name, "case_type": "load_combination", "step": None}, "scale_ratio": 1.0}]
        combos_out.append(
            Combination.model_validate(
                {"name": name, "type": _combo_type(row.get("type", table_types.get(name, 0))), "items": items}
            )
        )
    frame_loads = [
        {
            "frame": str(row.get("Frame", row.get("frame"))),
            "pattern": str(row.get("LoadPattern", row.get("pattern"))),
            "direction": LoadDirection.GRAVITY,
            "w_kN_m": _line_load(float(row.get("Value", row.get("value", 0.0))), units),
        }
        for row in frame_rows
        if row.get("Frame") or row.get("frame")
    ]
    area_loads = [
        {
            "area": str(row.get("UniqueName", row.get("area"))),
            "pattern": str(row.get("LoadPattern", row.get("pattern"))),
            "direction": LoadDirection.GRAVITY,
            "q_kPa": _area_load(float(row.get("Value", row.get("value", 0.0))), units),
        }
        for row in area_rows
        if row.get("UniqueName") or row.get("area")
    ]
    return LoadSet.model_validate(
        {
            "patterns": patterns_out,
            "combinations": combos_out,
            "frame_loads": frame_loads,
            "area_loads": area_loads,
        }
    )


def host_restraints(rows: list[dict[str, Any]]) -> dict[str, Any]:
    joints = [
        {
            "joint": str(row.get("UniqueName", row.get("joint"))),
            "ux": bool(row.get("Ux", row.get("ux"))),
            "uy": bool(row.get("Uy", row.get("uy"))),
            "uz": bool(row.get("Uz", row.get("uz"))),
            "rx": bool(row.get("Rx", row.get("rx"))),
            "ry": bool(row.get("Ry", row.get("ry"))),
            "rz": bool(row.get("Rz", row.get("rz"))),
        }
        for row in rows
    ]
    return {"joints": sorted(joints, key=lambda row: row["joint"])}


def restraints(rows: list[dict[str, Any]]) -> JointRestraints:
    return JointRestraints(
        joints=[
            JointRestraint(
                joint=str(row.get("UniqueName", row.get("joint"))),
                ux=bool(row.get("Ux", row.get("ux"))),
                uy=bool(row.get("Uy", row.get("uy"))),
                uz=bool(row.get("Uz", row.get("uz"))),
                rx=bool(row.get("Rx", row.get("rx"))),
                ry=bool(row.get("Ry", row.get("ry"))),
                rz=bool(row.get("Rz", row.get("rz"))),
            )
            for row in rows
        ]
    )


def model_status(info: dict[str, Any], model_path: Path | None) -> CsiModelStatus:
    counts = info.get("object_counts") or info.get("counts") or {}
    if not isinstance(counts, dict):
        counts = {}
    name = model_path.name if model_path is not None else "model"
    locked = info.get("locked")
    return CsiModelStatus(
        units=str(info.get("units", "")),
        locked=None if locked is None else bool(locked),
        object_counts={str(k): int(v) for k, v in counts.items()},
        program_version=str(info.get("program_version", "")),
        file_name=name,
    )


def area_section_kinds(items: list[dict[str, Any]]) -> dict[str, str]:
    return {str(row["name"]): str(row.get("type", "other")) for row in items}
