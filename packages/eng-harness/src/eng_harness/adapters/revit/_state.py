"""Revit model-state reader, chunked reads and fingerprint (plan 0011 T7; AC9 to AC11, §4.5, §4.9).

Reads metadata, levels, grids, the two structural category lists, details, mapped-role parameters, family types and
worksets. List truncation is re-read per level (`LIMIT_EXCEEDED` when a level is still truncated). Chunks for details
and parameters halve on `RESPONSE_TOO_LARGE`. The fingerprint is `sha256(canonical_json(...))` over the raw read set
(type id and name, mapped parameters' `rawValue`, location, level, `unique_id`, level and grid data), sorted by
`unique_id` / `element_id`; save time and element count are excluded. Neutral `model.frame_placements/1` and
`model.sections/1` rows are emitted only for complete fields (AC11).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any, Literal, cast

from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.issues import ModelIssue, Severity
from eng_contract.kinds.model import (
    Circular,
    Frame,
    FrameKind,
    FramePlacements,
    FrameSection,
    Rectangular,
    Sections,
)
from eng_contract.quantity import Quantity
from eng_contract.units import convert
from eng_contract.verdicts import Subject, SubjectKind
from pydantic import BaseModel

from eng_harness.adapters.revit._parameters import ROLE_NAMES, RoleMap
from eng_harness.adapters.revit._replies import parse_revit_reply
from eng_harness.adapters.revit._units import convert_parameter
from eng_harness.kinds.revit import (
    ElementRow,
    GridRow,
    LevelRow,
    Point3,
    RevitGrids,
    RevitLevels,
    RevitStatus,
    RevitStructure,
    TypeRow,
)
from eng_harness.servers import CallEffect

__all__ = ["LIST_LIMIT", "RevitStateReader", "StateRead", "fingerprint", "revit_document_loaded"]

LIST_LIMIT = 1000  # spec 0011 §4.5: list_elements caps at 1000 with no offset
_CATEGORIES = ("OST_StructuralColumns", "OST_StructuralFraming")
_SECTION_ROLES = ("section_b", "section_h", "section_D")

HostCall = Callable[[str, dict[str, Any], CallEffect], Awaitable[Mapping[str, Any]]]


def revit_document_loaded(metadata_path: str | None, bound: Path) -> bool:
    """True when `get_model_metadata` path equals the bound file (spec 0011 §4.12 locate / model_state)."""
    if not metadata_path:
        return False
    return PureWindowsPath(metadata_path) == PureWindowsPath(bound)


def fingerprint(read_set: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the raw read set (spec 0011 §4.9 / AC10).

    Lists of objects are ordered by `unique_id` or `element_id`. Keys `save_time` and `element_count` are dropped.
    """
    return payload_sha256(_ordered_read_set(read_set))


def _ordered_read_set(read_set: Mapping[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in read_set.items() if key not in {"save_time", "element_count"}}
    result: dict[str, Any] = {}
    for key, value in body.items():
        if key == "elements" and isinstance(value, list):
            result[key] = sorted((_ordered_obj(row) for row in value if isinstance(row, dict)), key=_element_sort)
        elif key in {"levels", "grids", "types"} and isinstance(value, list):
            result[key] = sorted((_ordered_obj(row) for row in value if isinstance(row, dict)), key=_id_sort)
        else:
            result[key] = _ordered_obj(value)
    return result


def _element_sort(row: Mapping[str, Any]) -> tuple[str, int]:
    uid = row.get("unique_id")
    eid = row.get("element_id")
    return (str(uid) if isinstance(uid, str) else "", int(eid) if isinstance(eid, int) else 0)


def _id_sort(row: Mapping[str, Any]) -> int:
    for key in ("element_id", "type_id"):
        value = row.get(key)
        if isinstance(value, int):
            return value
    return 0


def _ordered_obj(value: object) -> object:
    if isinstance(value, dict):
        return {key: _ordered_obj(item) for key, item in sorted(value.items(), key=lambda pair: pair[0])}
    if isinstance(value, list):
        items = [_ordered_obj(item) for item in value]
        if items and all(isinstance(item, dict) for item in items):
            return sorted(items, key=lambda row: str(payload_sha256(row)))
        return items
    return value


@dataclass(frozen=True)
class StateRead:
    """One Revit model-state read: payloads by kind, status, fingerprint and info issues."""

    payloads: dict[str, BaseModel]
    status: RevitStatus
    fingerprint: str
    issues: tuple[ModelIssue, ...] = field(default_factory=tuple)


class RevitStateReader:
    """Reads the Revit model-state set through `call` on the read role (spec 0011 §4.9)."""

    def __init__(
        self,
        *,
        call: HostCall,
        role_map: RoleMap,
        catalog_version: str,
    ) -> None:
        self._call = call
        self._roles = role_map
        self._catalog_version = catalog_version

    async def read(self, *, bound_path: Path) -> StateRead:
        """Read the bound document; raise `LIMIT_EXCEEDED` on an unrecoverable truncation or too-large reply."""
        meta = await self._invoke("revit_get_model_metadata", {})
        levels_body = await self._invoke("revit_list_levels", {})
        grids_body = await self._invoke("revit_list_grids", {})
        level_rows = _as_dicts(levels_body.get("levels"))
        grid_rows = _as_dicts(grids_body.get("grids"))
        listed = await self._list_elements(level_rows)
        details = await self._chunked(
            "revit_get_element_details",
            [int(row["element_id"]) for row in listed],
            id_field="elementIds",
        )
        detail_by_id = {int(row["element_id"]): row for row in details if isinstance(row.get("element_id"), int)}
        type_ids = sorted({int(row["type_id"]) for row in detail_by_id.values() if isinstance(row.get("type_id"), int)})
        instance_params = await self._chunked_parameters(
            "revit_get_element_parameters",
            sorted(detail_by_id),
            id_field="elementIds",
            extra={"includeReadOnly": True},
        )
        type_params = await self._chunked_parameters(
            "revit_get_type_parameters",
            type_ids,
            id_field="typeIds",
        )
        family_types = await self._family_types(detail_by_id)
        await self._invoke("revit_list_worksets", {"includeElementCounts": False})
        status_body = await self._invoke("revit_connection_status", {})

        issues: list[ModelIssue] = []
        elements, types = self._structure_rows(detail_by_id, instance_params, type_params, family_types, issues)
        structure = RevitStructure(elements=elements, types=types)
        status = self._status(meta, status_body, bound_path)
        levels = RevitLevels(
            levels=sorted(
                (
                    LevelRow(
                        element_id=int(row["element_id"]),
                        name=str(row["name"]),
                        elevation_mm=float(row["elevation_mm"]),
                    )
                    for row in level_rows
                ),
                key=lambda row: (row.elevation_mm, row.element_id),
            )
        )
        grids = RevitGrids(
            grids=sorted(
                (
                    GridRow(
                        element_id=int(row["element_id"]),
                        name=str(row["name"]),
                        start=_point(row.get("start")),
                        end=_point(row.get("end")),
                        length_mm=float(row["length_mm"]),
                    )
                    for row in grid_rows
                ),
                key=lambda row: row.element_id,
            )
        )
        frames, sections = self._neutral(structure, issues)
        payloads: dict[str, BaseModel] = {
            "harness.revit_status/1": status,
            "harness.revit_levels/1": levels,
            "harness.revit_grids/1": grids,
            "harness.revit_structure/1": structure,
            "model.frame_placements/1": frames,
            "model.sections/1": sections,
        }
        raw_set = _fingerprint_set(level_rows, grid_rows, detail_by_id, instance_params, type_params)
        return StateRead(payloads, status, fingerprint(raw_set), tuple(issues))

    async def _invoke(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raw = await self._call(tool, arguments, CallEffect.READ)
        parsed = parse_revit_reply(dict(raw))
        return dict(parsed.body)

    async def _list_elements(self, levels: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        collected: dict[int, dict[str, Any]] = {}
        for category in _CATEGORIES:
            body = await self._invoke(
                "revit_list_elements",
                {"category": category, "limit": LIST_LIMIT},
            )
            rows = _as_dicts(body.get("items"))
            if body.get("truncated"):
                rows = await self._list_per_level(category, levels)
            for row in rows:
                eid = row.get("element_id")
                if isinstance(eid, int):
                    collected[eid] = row
        return list(collected.values())

    async def _list_per_level(self, category: str, levels: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for level in levels:
            level_id = level.get("element_id")
            if not isinstance(level_id, int):
                continue
            body = await self._invoke(
                "revit_list_elements",
                {"category": category, "level_id": level_id, "limit": LIST_LIMIT},
            )
            rows = _as_dicts(body.get("items"))
            if body.get("truncated"):
                raise ContractError(
                    ErrorCode.LIMIT_EXCEEDED,
                    f"revit_list_elements truncated at level {level_id} after the per-level read",
                    received=len(rows),
                )
            collected.extend(rows)
        return collected

    async def _chunked(
        self,
        tool: str,
        ids: Sequence[int],
        *,
        id_field: str,
        extra: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not ids:
            return []
        return await self._chunked_from(tool, list(ids), id_field=id_field, extra=extra or {})

    async def _chunked_from(
        self,
        tool: str,
        ids: list[int],
        *,
        id_field: str,
        extra: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        try:
            body = await self._invoke(tool, {id_field: ids, **extra})
        except ContractError as error:
            if error.detail.code is not ErrorCode.LIMIT_EXCEEDED or "RESPONSE_TOO_LARGE" not in error.detail.message:
                raise
            if len(ids) <= 1:
                raise
            mid = len(ids) // 2
            left = await self._chunked_from(tool, ids[:mid], id_field=id_field, extra=extra)
            right = await self._chunked_from(tool, ids[mid:], id_field=id_field, extra=extra)
            return left + right
        return _as_dicts(body.get("items"))

    async def _chunked_parameters(
        self,
        tool: str,
        ids: Sequence[int],
        *,
        id_field: str,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[int, list[dict[str, Any]]]:
        rows = await self._chunked(tool, ids, id_field=id_field, extra=extra)
        result: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            owner = row.get("id")
            if not isinstance(owner, int):
                continue
            result[owner] = _as_dicts(row.get("parameters"))
        return result

    async def _family_types(self, details: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:
        families: dict[str, str] = {}
        for row in details.values():
            family = row.get("family")
            if isinstance(family, str) and family and family not in families:
                families[family] = family
        collected: list[dict[str, Any]] = []
        for family_name in sorted(families):
            start = 0
            while True:
                body = await self._invoke(
                    "revit_list_family_types_in_family",
                    {
                        "family_name": family_name,
                        "include_parameter_values": True,
                        "start_index": start,
                        "max_types": 100,
                    },
                )
                rows = _as_dicts(body.get("items"))
                collected.extend(rows)
                if body.get("truncated") is not True:
                    break
                start += len(rows)
                if not rows:
                    break
        return collected

    def _status(self, meta: Mapping[str, Any], connection: Mapping[str, Any], bound_path: Path) -> RevitStatus:
        path = meta.get("path")
        title = str(meta.get("title") or bound_path.stem)
        base = PureWindowsPath(str(path)).name if isinstance(path, str) and path else bound_path.name
        return RevitStatus(
            title=title,
            file_base_name=PureWindowsPath(base).stem if base else bound_path.stem,
            revit_version=str(meta.get("revit_version") or "unknown"),
            is_workshared=bool(meta.get("is_workshared")),
            active_is_bound=revit_document_loaded(str(path) if isinstance(path, str) else None, bound_path),
            catalog_version=str(connection.get("catalog_version") or self._catalog_version),
            ping_status=str(connection.get("ping_status") or "unknown"),
        )

    def _structure_rows(
        self,
        details: Mapping[int, Mapping[str, Any]],
        instance_params: Mapping[int, Sequence[Mapping[str, Any]]],
        type_params: Mapping[int, Sequence[Mapping[str, Any]]],
        family_types: Sequence[Mapping[str, Any]],
        issues: list[ModelIssue],
    ) -> tuple[list[ElementRow], list[TypeRow]]:
        elements: list[ElementRow] = []
        for eid, row in sorted(details.items()):
            category = _category(row.get("category"))
            family = str(row.get("family") or "")
            type_id = int(row["type_id"])
            type_name = str(row.get("type_name") or "")
            params, rotation = self._map_params(
                family,
                instance_params.get(eid, ()),
                Subject(kind=SubjectKind.FRAME, id=str(row.get("unique_id") or eid)),
                issues,
            )
            elements.append(
                ElementRow(
                    unique_id=str(row["unique_id"]),
                    element_id=eid,
                    category=category,
                    family=family,
                    type_id=type_id,
                    type_name=type_name,
                    level_id=int(row["level_id"]),
                    level_name=str(row.get("level_name") or ""),
                    location_kind=_location_kind(row.get("location_kind")),
                    i=_point(row.get("i")),
                    j=_point(row.get("j")),
                    rotation_deg=rotation,
                    parameters=params,
                )
            )
        type_index: dict[int, dict[str, Any]] = {}
        for row in family_types:
            tid = row.get("type_id")
            if isinstance(tid, int):
                type_index[tid] = dict(row)
        for _eid, row in details.items():
            tid = row.get("type_id")
            if isinstance(tid, int) and tid not in type_index:
                type_index[tid] = {
                    "type_id": tid,
                    "family": row.get("family"),
                    "name": row.get("type_name"),
                    "instance_ids": [],
                }
        for tid, row in type_index.items():
            instances = [eid for eid, detail in details.items() if detail.get("type_id") == tid]
            row.setdefault("instance_ids", instances)
            if not row.get("instance_ids"):
                row["instance_ids"] = instances
        types: list[TypeRow] = []
        for tid, row in sorted(type_index.items()):
            family = str(row.get("family") or "")
            params, _ = self._map_params(
                family,
                type_params.get(tid, _as_dicts(row.get("parameters"))),
                Subject(kind=SubjectKind.SECTION, id=str(tid)),
                issues,
            )
            instance_ids = sorted({int(item) for item in (row.get("instance_ids") or []) if isinstance(item, int)})
            types.append(
                TypeRow(
                    type_id=tid,
                    family=family,
                    name=str(row.get("name") or row.get("type_name") or ""),
                    instance_ids=instance_ids,
                    parameters=params,
                )
            )
        elements.sort(key=lambda row: row.unique_id)
        types.sort(key=lambda row: row.type_id)
        return elements, types

    def _map_params(
        self,
        family: str,
        parameters: Sequence[Mapping[str, Any]],
        subject: Subject,
        issues: list[ModelIssue],
    ) -> tuple[dict[str, Quantity | str | int], float | None]:
        roles = self._roles.get(family, {})
        by_name = {str(row.get("name")): row for row in parameters if row.get("name")}
        mapped: dict[str, Quantity | str | int] = {}
        rotation: float | None = None
        for role_name in ROLE_NAMES:
            role = roles.get(role_name)
            if role is None:
                continue
            row = by_name.get(role.name)
            if row is None:
                continue
            if role_name == "material" or role_name == "etabs_link":
                value = row.get("rawValue", row.get("value"))
                if isinstance(value, str) and value:
                    mapped[role_name] = value
                if isinstance(value, int) and not isinstance(value, bool):
                    mapped[role_name] = value
                continue
            if role_name == "rotation":
                converted, issue = convert_parameter(row, subject=subject)
                if converted is not None:
                    mapped[role_name] = Quantity(value=converted, unit="deg")
                    rotation = converted
                else:
                    raw = row.get("rawValue")
                    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                        # Spec 0011 §4.6: angle internal unit is rad → contract deg (rotation role, L6).
                        # No Autodesk specId is cited yet (B-234); the role map identifies the quantity kind.
                        degrees = convert(float(raw), "rad", "deg")
                        mapped[role_name] = Quantity(value=degrees, unit="deg")
                        rotation = degrees
                    elif issue is not None:
                        issues.append(issue)
                continue
            converted, issue = convert_parameter(row, subject=subject)
            if converted is not None:
                mapped[role_name] = Quantity(value=converted, unit="mm")
            elif issue is not None:
                issues.append(issue)
        return mapped, rotation

    def _neutral(self, structure: RevitStructure, issues: list[ModelIssue]) -> tuple[FramePlacements, Sections]:
        type_by_id = {row.type_id: row for row in structure.types}
        frames: list[Frame] = []
        frame_sections: dict[str, FrameSection] = {}
        for element in structure.elements:
            type_row = type_by_id.get(element.type_id)
            section_name = f"{element.family}: {element.type_name}"
            if type_row is not None:
                shape = _section_shape(type_row.parameters)
                if shape is None:
                    issues.append(
                        ModelIssue(
                            severity=Severity.INFO,
                            code="SECTION_ROLES_UNMAPPED",
                            subject=Subject(kind=SubjectKind.SECTION, id=str(element.type_id)),
                            message=f"type {element.type_id} lacks a complete section role map",
                        )
                    )
                else:
                    material = type_row.parameters.get("material")
                    material_name = material if isinstance(material, str) and material else "unknown"
                    frame_sections.setdefault(
                        section_name,
                        FrameSection(name=section_name, material=material_name, shape=shape),
                    )
            if element.i is None or element.j is None or element.rotation_deg is None:
                if element.rotation_deg is None and element.category == "column":
                    issues.append(
                        ModelIssue(
                            severity=Severity.INFO,
                            code="ROTATION_UNAVAILABLE",
                            subject=Subject(kind=SubjectKind.FRAME, id=element.unique_id),
                            message=f"element {element.unique_id} has no readable rotation",
                        )
                    )
                continue
            if element.i == element.j:
                continue
            kind = FrameKind.COLUMN if element.category == "column" else FrameKind.OTHER
            frames.append(
                Frame.model_validate(
                    {
                        "id": element.unique_id,
                        "kind": kind,
                        "section": section_name,
                        "i_joint": None,
                        "j_joint": None,
                        "i": _contract_point(element.i),
                        "j": _contract_point(element.j),
                        "story": element.level_name,
                        "rotation_deg": element.rotation_deg,
                    }
                )
            )
        # Types with no instances still report SECTION_ROLES_UNMAPPED when incomplete (AC11).
        for type_row in structure.types:
            section_name = f"{type_row.family}: {type_row.name}"
            if section_name in frame_sections:
                continue
            if _section_shape(type_row.parameters) is None and any(
                role in type_row.parameters for role in _SECTION_ROLES
            ):
                issues.append(
                    ModelIssue(
                        severity=Severity.INFO,
                        code="SECTION_ROLES_UNMAPPED",
                        subject=Subject(kind=SubjectKind.SECTION, id=str(type_row.type_id)),
                        message=f"type {type_row.type_id} lacks a complete section role map",
                    )
                )
        frames.sort(key=lambda row: row.id)
        return (
            FramePlacements(frames=frames),
            Sections(frame_sections=sorted(frame_sections.values(), key=lambda row: row.name), area_sections=[]),
        )


def _fingerprint_set(
    levels: Sequence[Mapping[str, Any]],
    grids: Sequence[Mapping[str, Any]],
    details: Mapping[int, Mapping[str, Any]],
    instance_params: Mapping[int, Sequence[Mapping[str, Any]]],
    type_params: Mapping[int, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    elements = []
    for eid, row in details.items():
        params = {
            str(item.get("name")): {"rawValue": item.get("rawValue")}
            for item in instance_params.get(eid, ())
            if item.get("name")
        }
        elements.append(
            {
                "unique_id": row.get("unique_id"),
                "element_id": eid,
                "type_id": row.get("type_id"),
                "type_name": row.get("type_name"),
                "level_id": row.get("level_id"),
                "location": {
                    "kind": row.get("location_kind"),
                    "i": row.get("i"),
                    "j": row.get("j"),
                },
                "parameters": params,
            }
        )
    types = []
    for tid, rows in type_params.items():
        types.append(
            {
                "type_id": tid,
                "parameters": {
                    str(item.get("name")): {"rawValue": item.get("rawValue")} for item in rows if item.get("name")
                },
            }
        )
    return {
        "levels": [
            {
                "element_id": row.get("element_id"),
                "name": row.get("name"),
                "elevation_mm": row.get("elevation_mm"),
            }
            for row in levels
        ],
        "grids": [
            {
                "element_id": row.get("element_id"),
                "name": row.get("name"),
                "start": row.get("start"),
                "end": row.get("end"),
                "length_mm": row.get("length_mm"),
            }
            for row in grids
        ],
        "elements": elements,
        "types": types,
    }


def _as_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _category(value: object) -> Literal["column", "framing"]:
    text = str(value or "")
    if text in {"OST_StructuralColumns", "column"}:
        return "column"
    if text in {"OST_StructuralFraming", "framing"}:
        return "framing"
    raise ContractError(
        ErrorCode.HOST_ERROR,
        f"unexpected Revit category {text!r}",
        retryable=False,
        host_code="UNEXPECTED_REPLY",
        field="category",
    )


def _location_kind(value: object) -> Literal["point", "curve"]:
    text = str(value or "")
    if text in {"point", "curve"}:
        return cast(Literal["point", "curve"], text)
    raise ContractError(
        ErrorCode.HOST_ERROR,
        f"unexpected location_kind {text!r}",
        retryable=False,
        host_code="UNEXPECTED_REPLY",
        field="location_kind",
    )


def _point(value: object) -> Point3 | None:
    if not isinstance(value, Mapping):
        return None
    try:
        if "x_mm" in value:
            return Point3(x_mm=float(value["x_mm"]), y_mm=float(value["y_mm"]), z_mm=float(value["z_mm"]))
        return Point3(x_mm=float(value["x"]), y_mm=float(value["y"]), z_mm=float(value["z"]))
    except KeyError, TypeError, ValueError:
        return None


def _contract_point(point: Point3) -> dict[str, float]:
    """Contract `Point3` as a dict so Frame coercion does not import a non-exported module."""
    return {"x_mm": point.x_mm, "y_mm": point.y_mm, "z_mm": point.z_mm}


def _section_shape(parameters: Mapping[str, Quantity | str | int]) -> Rectangular | Circular | None:
    b = parameters.get("section_b")
    h = parameters.get("section_h")
    diameter = parameters.get("section_D")
    if isinstance(b, Quantity) and isinstance(h, Quantity):
        return Rectangular(type="rectangular", b_mm=b.value, h_mm=h.value)
    if isinstance(diameter, Quantity):
        return Circular(type="circular", D_mm=diameter.value)
    return None
