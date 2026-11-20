"""SAP2000 model-state reader with declared absences (plan 0012 T4; spec 0012 AC7 to AC10, section 4.3, 4.4).

Reads frames, areas, points, sections, materials, the load set and status through typed list tools. Stories and grids
are declared absent (AC8): the reader does not call `csi_list_stories` or `csi_list_grids`, and emits info issues
`LEVELS_NOT_AVAILABLE` and `GRID_NOT_AVAILABLE`. Table-backed reads raise `NotImplementedGap` (SP-4) while every
field-map entry is `unknown` (AC10). Truncation is `LIMIT_EXCEEDED` (AC9). The fingerprint is over the kinds the
profile lists (spec 0012 section 4.3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.issues import ModelIssue, Severity
from eng_contract.kinds.model import Materials, Sections
from eng_contract.units import convert, csi_unit_system
from eng_contract.verdicts import Subject, SubjectKind
from pydantic import BaseModel

from eng_harness._kinds import ModelPoint, ModelPoints
from eng_harness.adapters.csi._replies import area_section_kinds, areas, frames, load_set, model_status
from eng_harness.adapters.csi._state import LIST_LIMIT, READ_UNITS, HostCall, StateRead, fingerprint
from eng_harness.adapters.csi._tables import FieldMap, load_field_map, map_rows
from eng_harness.adapters.csi.products import _sap2000
from eng_harness.errors import NotImplementedGap
from eng_harness.servers import CallEffect

__all__ = [
    "Sap2000StateReader",
    "fingerprint",
    "points_from_items",
    "sap2000_field_map",
]

_LISTS = (  # (name, tool, takes the units token): SAP2000 read order of spec 0012 section 4.3 (no stories, no grids)
    ("points", "csi_list_points", True),
    ("frames", "csi_list_frames", True),
    ("areas", "csi_list_areas", True),
    ("frame_sections", "csi_list_frame_sections", False),
    ("area_sections", "csi_list_area_sections", False),
    ("materials", "csi_list_materials", False),
    ("patterns", "csi_list_load_patterns", False),
    ("combos", "csi_list_load_combos", False),
)
_SOURCES = {  # host reads behind each kind: what the fingerprint covers (spec 0012 section 4.3)
    "model.frame_placements/1": ("frames",),
    "model.area_placements/1": ("areas", "area_sections"),
    "harness.model_points/1": ("points",),
    "model.sections/1": ("frame_sections", "area_sections"),
    "model.materials/1": ("materials",),
    "model.load_set/1": ("patterns", "combos"),
}


@lru_cache(maxsize=1)
def sap2000_field_map() -> FieldMap:
    """Load the packaged SAP2000 field-map data (`products/_sap2000_tables.toml`)."""
    text = files("eng_harness.adapters.csi.products").joinpath("_sap2000_tables.toml").read_text(encoding="utf-8")
    return load_field_map(text)


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise TypeError(f"numeric table cell expected, got {type(value).__name__}")
    return float(value)


def _length_mm(value: object, units: str) -> float:
    return convert(_as_float(value), csi_unit_system(units).length, "mm")


def points_from_items(items: Sequence[Mapping[str, Any]], units: str) -> ModelPoints:
    """Build `harness.model_points/1` from `csi_list_points` (spec 0012 section 4.3)."""
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


def _absence_issue(code: str, message: str) -> ModelIssue:
    return ModelIssue(
        severity=Severity.INFO,
        code=code,
        subject=Subject(kind=SubjectKind.MODEL, id="model"),
        message=message,
    )


def _map_table(table: str, rows: Sequence[Mapping[str, Any]]) -> None:
    """Raise `NotImplementedGap` (SP-4) for any SAP2000 table while entries are unknown (AC10)."""
    try:
        map_rows(table, rows, field_map=sap2000_field_map())
    except NotImplementedGap as error:
        raise NotImplementedGap(
            _sap2000.GAPS["SP-4"] + f": table {table!r}",
            evidence=("SP-4", table, *error.evidence[1:]),
        ) from error


class Sap2000StateReader:
    """Reads the SAP2000 model-state set through `call` (spec 0012 section 4.3; plan 0012 T4)."""

    def __init__(self, *, product: str, call: HostCall) -> None:
        self._product, self._call = product, call
        self.issues: tuple[ModelIssue, ...] = ()

    async def read(self, pid: int, model_path: Path | None) -> StateRead:
        """Read the instance `pid`; `model_path` names the status's file (its base name only)."""
        target = {"target": {"product": self._product, "pid": pid}}
        info = await self._call("csi_model_info", target, CallEffect.READ)
        rows: dict[str, list[dict[str, Any]]] = {}
        for name, tool, tokened in _LISTS:
            arguments = {**target, "limit": LIST_LIMIT, **({"units": READ_UNITS} if tokened else {})}
            rows[name] = await self._rows(tool, "items", arguments, tool)
        after = await self._call("csi_model_info", target, CallEffect.READ)
        if after.get("units") != info.get("units"):
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED,
                "the model's units changed during the read",
                precondition=Precondition.units_verified,
                expected={"units": info.get("units")},
                received=after.get("units"),
            )
        # Declared absences (spec 0012 AC8, SP-7): do not call csi_list_stories or csi_list_grids.
        self.issues = (
            _absence_issue(
                "LEVELS_NOT_AVAILABLE",
                "levels are not available on SAP2000: csi_list_stories is unsupported_by_version",
            ),
            _absence_issue(
                "GRID_NOT_AVAILABLE",
                "grids are not available on SAP2000: csi_list_grids is unsupported_by_version",
            ),
        )
        try:
            status = model_status(info, model_path)
            # Section and material property tables are unknown (AC10 / SP-4): name lists alone cannot fill
            # model.sections/1 or model.materials/1 without inventing host fields or engineering values.
            # The kinds are produced empty until a recording (L4) keys the tables (spec 0012 section 4.4).
            payloads: dict[str, BaseModel] = {
                "model.frame_placements/1": frames(rows["frames"], READ_UNITS),
                "model.area_placements/1": areas(
                    rows["areas"], READ_UNITS, area_section_kinds(rows["area_sections"])
                ),
                "harness.model_points/1": points_from_items(rows["points"], READ_UNITS),
                "model.sections/1": Sections(frame_sections=[], area_sections=[]),
                "model.materials/1": Materials(materials=[]),
                "model.load_set/1": load_set(
                    rows["patterns"],
                    rows["combos"],
                    [],  # pattern defs: table unknown (AC10)
                    [],  # combo defs: table unknown (AC10)
                    [],  # frame loads: table unknown (AC10)
                    [],  # area loads: table unknown (AC10)
                    status.units,
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

    def need_table(self, table: str, rows: Sequence[Mapping[str, Any]]) -> None:
        """Raise SP-4 when a reader needs a SAP2000 table while its field-map status is unknown (AC10)."""
        _map_table(table, rows)
