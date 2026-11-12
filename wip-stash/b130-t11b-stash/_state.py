"""CSI model-state reader and fingerprint (plan 0002 T11; spec 0002 section 4.6.4)."""

import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eng_contract.canonical import canonical_json
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.adapters.csi import products
from eng_harness.adapters.csi._replies import (
    _HOST_KIND,
    area_section_kinds,
    areas,
    frames,
    grids,
    host_areas,
    host_frames,
    host_grid,
    host_load_set,
    host_restraints,
    host_stories,
    load_set,
    model_status,
    restraints,
    stories,
)
from eng_harness.servers import CallEffect

LIST_LIMIT = 2000  # S-12 section 2; spec 0002 section 4.6.4
_KEYS = (
    "model.stories/1",
    "model.grid_system/1",
    "model.frame_placements/1",
    "model.area_placements/1",
    "model.load_set/1",
    "model.joint_restraints/1",
)

HostCall = Callable[[str, dict[str, Any], CallEffect], Awaitable[dict[str, Any]]]


def _sort_key(row: object) -> str:
    if isinstance(row, dict):
        for name in ("name", "id", "joint", "label"):
            if name in row:
                return str(row[name])
    return canonical_json(row).decode()


def sort_lists(body: dict[str, Any]) -> dict[str, Any]:
    """Sort each named list in a host payload by its stable key."""
    out: dict[str, Any] = {}
    for field, value in body.items():
        out[field] = sorted(value, key=_sort_key) if isinstance(value, list) else value
    return out


def fingerprint_host(sections: Mapping[str, Any], object_counts: Mapping[str, int]) -> str:
    """Fingerprint of the six host payloads and `object_counts` (spec 0002 section 4.6.4)."""
    body = {
        **{key: sort_lists(dict(payload)) for key, payload in sections.items()},
        "object_counts": dict(sorted(object_counts.items())),
    }
    return hashlib.sha256(canonical_json(body)).hexdigest()


@dataclass(frozen=True)
class StateRead:
    """A model-state read: canonical kinds, host sections and fingerprint inputs."""

    kinds: dict[str, Any]
    host: dict[str, Any]
    object_counts: dict[str, int]


class CsiStateReader:
    """Reads the ETABS model-state set through the `main` role."""

    def __init__(self, *, product: str, call: HostCall) -> None:
        self._product, self._call = product, call
        self._tables = products.profile(product).tables

    async def read(self, pid: int, model_path: Path | None) -> StateRead:
        target = {"target": {"product": self._product, "pid": pid}}
        table_args = {"table": "", "row_limit": LIST_LIMIT, **target}
        limit = {"limit": LIST_LIMIT, "units": "kN_m_C"}
        info = await self._call("csi_model_info", target, CallEffect.READ)
        stories_reply = await self._list("csi_list_stories", {**target, **limit})
        grids_reply = await self._list("csi_list_grids", {**target, **limit})
        frames_reply = await self._list("csi_list_frames", {**target, **limit})
        areas_reply = await self._list("csi_list_areas", {**target, **limit})
        patterns = await self._list("csi_list_load_patterns", {**target, "limit": LIST_LIMIT})
        combos = await self._list("csi_list_load_combos", {**target, "limit": LIST_LIMIT})
        area_sections = await self._list("csi_list_area_sections", {**target, "limit": LIST_LIMIT})
        restraint_rows = await self._table(table_args, self._tables["restraints"])
        pattern_rows = await self._table(table_args, self._tables["pattern_defs"])
        combo_rows = await self._table(table_args, self._tables["combo_defs"])
        frame_loads = await self._table(table_args, self._tables["frame_loads"])
        area_loads = await self._table(table_args, self._tables["area_loads"])
        sections = area_section_kinds(area_sections)
        units = str(info.get("units", "kN_m_C"))
        host = {
            "model.stories/1": host_stories(stories_reply),
            "model.grid_system/1": host_grid(grids_reply),
            "model.frame_placements/1": host_frames(frames_reply),
            "model.area_placements/1": host_areas(areas_reply),
            "model.load_set/1": host_load_set(patterns, combos, frame_loads, area_loads),
            "model.joint_restraints/1": host_restraints(restraint_rows),
        }
        kinds = {
            "model.stories/1": stories(stories_reply, units).model_dump(mode="json"),
            "model.grid_system/1": grids(grids_reply, units).model_dump(mode="json"),
            "model.frame_placements/1": frames(frames_reply, units).model_dump(mode="json"),
            "model.area_placements/1": areas(areas_reply, units, sections).model_dump(mode="json"),
            "model.load_set/1": load_set(
                patterns, combos, pattern_rows, combo_rows, frame_loads, area_loads, units
            ).model_dump(mode="json"),
            "model.joint_restraints/1": restraints(restraint_rows).model_dump(mode="json"),
            _HOST_KIND: model_status(info, model_path).model_dump(mode="json"),
        }
        counts = kinds[_HOST_KIND]["object_counts"]
        return StateRead(kinds=kinds, host=host, object_counts=counts)

    async def _list(self, tool: str, args: dict[str, Any]) -> list[dict[str, Any]]:
        body = await self._call(tool, args, CallEffect.READ)
        if body.get("truncated"):
            raise ContractError(ErrorCode.LIMIT_EXCEEDED, f"{tool} was truncated", received=body.get("count"))
        items = body.get("items")
        return list(items) if isinstance(items, list) else []

    async def _table(self, args: dict[str, Any], table: str) -> list[dict[str, Any]]:
        body = await self._call("csi_db_table_read", {**args, "table": table}, CallEffect.READ)
        if body.get("truncated"):
            raise ContractError(ErrorCode.LIMIT_EXCEEDED, f"{table} was truncated", received=len(body.get("rows", [])))
        rows = body.get("rows")
        return list(rows) if isinstance(rows, list) else []
