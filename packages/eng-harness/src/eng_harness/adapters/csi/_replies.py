"""CSI replies mapped to neutral and harness kinds (plan 0002 T11, T13; spec 0002 sections 4.6.1, 4.6.4).

Units: the result mappers take the call's units token (`kN_m_C`, spec 4.6.1) and answer kN, kN.m and mm; their reply
field names are host facts to confirm at the first local run (OQ-G10).
Errors: `ContractError` `HOST_ERROR` (`host_code` `UNEXPECTED_REPLY`, spec 0002 A3) when a reply field is missing or
unusable, from every mapper: never a bare `KeyError` or a pydantic `ValidationError`.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from functools import wraps
from pathlib import Path
from typing import Any, NoReturn

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.forces import JointReactions, MemberEnd, StoryDrifts
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

from eng_harness.kinds.csi import (
    CSI_KINDS,
    CaseStatus,
    CsiAnalysisRun,
    CsiAnalysisStatus,
    CsiDesignRun,
    CsiModelStatus,
    CsiRows,
)

__all__ = [
    "CSI_KINDS",
    "CaseStatus",
    "CsiAnalysisRun",
    "CsiAnalysisStatus",
    "CsiDesignRun",
    "CsiModelStatus",
    "CsiRows",
]

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
_COMBO_KIND = {"combo": "load_combination"}  # the host's `kind` of a combination item: `case` or `combo`
_AREA = {"slab": AreaKind.SLAB, "wall": AreaKind.WALL, "deck": AreaKind.DECK}


def _length(value: float, units: str) -> float:
    return convert(value, csi_unit_system(units).length, "mm")  # spec 4.7.4 present length → mm


def _area_load(value: float, units: str) -> float:
    return convert(value, csi_unit_system(units).stress, "kPa")  # spec 4.7.4 present stress → kPa


def _line_load(value: float, units: str) -> float:
    return convert(value, csi_unit_system(units).line_load, "kN/m")  # spec 4.7.4 present line load → kN/m


def _bad_reply(field: str, received: object, message: str = "") -> NoReturn:
    raise ContractError(
        ErrorCode.HOST_ERROR,
        message or f"the host reply field {field} is not usable",
        retryable=False,
        host_code="UNEXPECTED_REPLY",
        field=field,
        received=received,
    )


def _mapped[**P, R](mapper: Callable[P, R]) -> Callable[P, R]:
    """`mapper` with a missing or unusable reply value raised as `UNEXPECTED_REPLY` (field `rows`), no bare error."""

    @wraps(mapper)
    def run(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return mapper(*args, **kwargs)
        except KeyError as error:
            _bad_reply("rows", None, f"{mapper.__name__}: the host reply has no field {error.args[0]}")
        except AttributeError, TypeError, ValueError:  # a row that is no object; pydantic's error is a ValueError
            _bad_reply("rows", None, f"{mapper.__name__}: a value of the host reply cannot be mapped")

    return run


def _point(raw: Sequence[float], units: str, *, field: str) -> dict[str, float]:
    if len(raw) != 3:
        _bad_reply(field, list(raw))
    try:
        x, y, z = (float(raw[0]), float(raw[1]), float(raw[2]))
    except TypeError, ValueError:
        _bad_reply(field, list(raw))
    if not all(math.isfinite(v) for v in (x, y, z)):
        _bad_reply(field, list(raw))
    return {"x_mm": _length(x, units), "y_mm": _length(y, units), "z_mm": _length(z, units)}


@_mapped
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


@_mapped
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


@_mapped
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
                "i": _point(row["point1"], units, field="point1"),
                "j": _point(row["point2"], units, field="point2"),
                "story": None if row.get("story") in (None, "") else str(row["story"]),
                "rotation_deg": 0.0,
            }
        )
    return FramePlacements.model_validate({"frames": rows})


@_mapped
def areas(items: list[dict[str, Any]], units: str, sections: Mapping[str, str]) -> AreaPlacements:
    rows = []
    for row in items:
        kind = _AREA.get(str(sections.get(str(row.get("section", "")), "other")).lower(), AreaKind.OTHER)
        rows.append(
            {
                "id": str(row["name"]),
                "kind": kind,
                "section": str(row["section"]),
                "points": [_point(point, units, field=f"points[{index}]") for index, point in enumerate(row["points"])],
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


@_mapped
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
                "case": {"case": str(part["name"]), "case_type": _COMBO_KIND.get(part.get("kind"), "load_pattern")},
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


@_mapped
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


@_mapped
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


@_mapped
def area_section_kinds(items: list[dict[str, Any]]) -> dict[str, str]:
    return {str(row["name"]): str(row.get("type", "other")) for row in items}


def _rows(reply: Mapping[str, Any], field: str) -> list[dict[str, Any]]:
    rows = reply.get(field)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        _bad_reply(field, None)
    return rows


@_mapped
def analysis_run(reply: Mapping[str, Any]) -> CsiAnalysisRun:
    return CsiAnalysisRun(started=reply["started"])


@_mapped
def analysis_status(reply: Mapping[str, Any]) -> CsiAnalysisStatus:
    cases = [CaseStatus(case=str(row["case"]), status_code=row["status_code"]) for row in _rows(reply, "cases")]
    return CsiAnalysisStatus(cases=cases)


@_mapped
def design_run(reply: Mapping[str, Any]) -> CsiDesignRun:
    return CsiDesignRun(reply=dict(reply))


@_mapped
def design_results(reply: Mapping[str, Any]) -> CsiRows:
    return CsiRows(rows=_rows(reply, "items"))


@_mapped
def analysis_messages(reply: Mapping[str, Any]) -> CsiRows:
    return CsiRows(rows=_rows(reply, "rows"))


def _case_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    """The case of a result row: a combination when the host's `kind` says `combo`, else a load case."""
    step = row.get("step")
    return {
        "case": str(row["case"]),
        "case_type": "load_combination" if row.get("kind") == "combo" else "load_case",
        "step": None if step in (None, "") else str(step),
    }


_UNIT = {"kN": ("force", "kN"), "kNm": ("moment", "kN.m"), "mm": ("length", "mm")}  # field suffix: system member, unit
_REACTION = {"FX_kN": "F1", "FY_kN": "F2", "FZ_kN": "F3", "MX_kNm": "M1", "MY_kNm": "M2", "MZ_kNm": "M3"}
_MEMBER = (
    {f"{k}_kN": k for k in ("P", "V2", "V3")} | {f"{k}_kNm": k for k in ("T", "M2", "M3")} | {"station_mm": "station"}
)
_DRIFT_POINT = {"x_mm": "x", "y_mm": "y", "z_mm": "z"}  # optional in the reply


def _scaled(row: Mapping[str, Any], units: str, fields: Mapping[str, str]) -> dict[str, float]:
    """The host `fields` ({canonical field: host key}) of `row` in the canonical unit named by each field's suffix."""
    system = csi_unit_system(units)
    scaled = {}
    for name, key in fields.items():
        member, unit = _UNIT[name.rpartition("_")[2]]
        scaled[name] = convert(float(row[key]), getattr(system, member), unit)
    return scaled


@_mapped
def joint_reactions(reply: Mapping[str, Any], units: str) -> JointReactions:
    rows = [
        {"joint": str(row["joint"]), "case": _case_ref(row), **_scaled(row, units, _REACTION)}
        for row in _rows(reply, "items")
    ]
    return JointReactions.model_validate({"axes": "global", "rows": rows})


@_mapped
def member_forces(reply: Mapping[str, Any], units: str) -> MemberEnd:
    rows = [
        {
            "member": str(row["frame"]),
            "case": _case_ref(row),
            "end": row.get("end") if row.get("end") in ("i", "j") else None,
            **_scaled(row, units, _MEMBER),
        }
        for row in _rows(reply, "items")
    ]
    return MemberEnd.model_validate({"sign_convention": "host_local/1", "rows": rows})


@_mapped
def story_drifts(reply: Mapping[str, Any], units: str) -> StoryDrifts:
    rows = [
        {
            "story": str(row["story"]),
            "case": _case_ref(row),
            "direction": row["direction"],
            "drift_ratio": float(row["drift"]),
            "point": str(row["label"]) if row.get("label") else None,
            **_scaled(row, units, {k: v for k, v in _DRIFT_POINT.items() if row.get(v) is not None}),
        }
        for row in _rows(reply, "items")
    ]
    return StoryDrifts.model_validate({"rows": rows})
