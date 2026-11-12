"""CSI model-state reader and fingerprint (plan 0002 T11b; spec 0002 sections 4.5.4 and 4.6.4).

Reads the six neutral kinds and the host status through the `main` role: every list at `limit` 2000, every table at
`row_limit` 2000. Errors (`ContractError`): `LIMIT_EXCEEDED` (`received`: the row count) for a list or table read with
`truncated: true`; `HOST_ERROR` with `host_code` `UNEXPECTED_REPLY` for a reply without its rows; `PRECONDITION_FAILED`
(`units_verified`) when the model's units differ before and after the read, as then the table values are mislabelled.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eng_contract.canonical import canonical_json, payload_sha256
from eng_contract.errors import ContractError, ErrorCode, Precondition
from pydantic import BaseModel

from eng_harness.adapters.csi import products
from eng_harness.adapters.csi._replies import (
    CsiModelStatus,
    area_section_kinds,
    areas,
    frames,
    grids,
    load_set,
    model_status,
    restraints,
    stories,
)
from eng_harness.servers import CallEffect

LIST_LIMIT = 2000  # S-12 section 2: the cap of every list tool and table read, which has no paging
READ_UNITS = "kN_mm_C"  # spec 4.6.3: the lengths token; the four list reads convert from it, not from present units

HostCall = Callable[[str, dict[str, Any], CallEffect], Awaitable[dict[str, Any]]]

_LISTS = (  # (name, tool, takes the units token): the read order of spec 4.6.4
    ("stories", "csi_list_stories", True),
    ("grids", "csi_list_grids", True),
    ("frames", "csi_list_frames", True),
    ("areas", "csi_list_areas", True),
    ("patterns", "csi_list_load_patterns", False),
    ("combos", "csi_list_load_combos", False),
    ("area_sections", "csi_list_area_sections", False),
)
_TABLES = ("restraints", "pattern_defs", "combo_defs", "frame_loads", "area_loads")  # keys of the product profile
_SOURCES = {  # the host reads behind each neutral kind: what the fingerprint covers
    "model.stories/1": ("stories",),
    "model.grid_system/1": ("grids",),
    "model.frame_placements/1": ("frames",),
    "model.area_placements/1": ("areas", "area_sections"),
    "model.load_set/1": ("patterns", "combos", "pattern_defs", "combo_defs", "frame_loads", "area_loads"),
    "model.joint_restraints/1": ("restraints",),
}


def _ordered(value: object) -> object:
    """`value` with each list of objects sorted by canonical text; other lists (coordinates, polygons) keep order."""
    if isinstance(value, dict):
        return {key: _ordered(item) for key, item in value.items()}
    if isinstance(value, list):
        items = [_ordered(item) for item in value]
        if items and all(isinstance(item, dict) for item in items):
            return sorted(items, key=canonical_json)
        return items
    return value


def fingerprint(sections: Mapping[str, object], object_counts: Mapping[str, int]) -> str:
    """SHA-256 of the canonical JSON of the host `sections` and `object_counts` (spec 4.6.4).

    The sections are the host rows as read, in the units of the read (no conversion rounding enters), with every list
    of objects ordered; the file's save time is not part of it.
    """
    return payload_sha256({"sections": _ordered(sections), "object_counts": dict(object_counts)})


@dataclass(frozen=True)
class StateRead:
    """One model-state read: the six neutral payloads by kind, the host status and the fingerprint."""

    payloads: dict[str, BaseModel]
    status: CsiModelStatus
    fingerprint: str


class CsiStateReader:
    """Reads the model-state set of a product through `call` (the `main` role of the CSI server)."""

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
        try:  # a row the T11 mappers cannot read is an unusable reply, like a reply without its rows
            status = model_status(info, model_path)
            loads = load_set(  # the tables carry no token: their values are in the present units
                rows["patterns"], rows["combos"], rows["pattern_defs"], rows["combo_defs"],
                rows["frame_loads"], rows["area_loads"], status.units,
            )  # fmt: skip
            payloads: dict[str, BaseModel] = {
                "model.stories/1": stories(rows["stories"], READ_UNITS),
                "model.grid_system/1": grids(rows["grids"], READ_UNITS),
                "model.frame_placements/1": frames(rows["frames"], READ_UNITS),
                "model.area_placements/1": areas(rows["areas"], READ_UNITS, area_section_kinds(rows["area_sections"])),
                "model.load_set/1": loads,
                "model.joint_restraints/1": restraints(rows["restraints"]),
            }
        except (KeyError, TypeError, ValueError) as error:  # pydantic's ValidationError is a ValueError
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
