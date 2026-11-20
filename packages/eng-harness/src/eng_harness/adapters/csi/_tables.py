"""CSI table reader and SAFE field-map matching (plan 0008 T4; spec 0008 section 4.5, AC13).

`csi_db_table_read` values are in the present units (no `units` parameter); labelling and conversion belong to the
callers. Column matching is exact equality of the normalized name (lower case, letters and digits only). None or
several matches for a logical column is `INTERNAL` with the columns seen, never a first match. An `unknown` map entry
is a `NotImplementedGap` until a recording promotes it.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any, Literal, NoReturn

from eng_contract.errors import ContractError, ErrorCode
from pydantic import BaseModel, ConfigDict, Field

from eng_harness.adapters.csi._state import LIST_LIMIT, HostCall
from eng_harness.errors import NotImplementedGap
from eng_harness.servers import CallEffect

__all__ = [
    "FieldMap",
    "FieldSpec",
    "MappedTable",
    "TableEntry",
    "load_field_map",
    "map_rows",
    "normalize_name",
    "read_table",
    "safe_field_map",
]

_Status = Literal["reference", "candidate", "unknown"]
_NORM = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str) -> str:
    """Lower case with letters and digits only (spec 0008 section 4.5)."""
    return _NORM.sub("", name.strip().lower())


class FieldSpec(BaseModel):
    """One logical column: a host name (`reference`) or accepted normalized names (`candidate`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str | None = None
    names: tuple[str, ...] = ()
    required: bool = True

    def accepted(self) -> frozenset[str]:
        """Normalized names that may match this logical column."""
        if self.host is not None:
            return frozenset({normalize_name(self.host)})
        return frozenset(self.names)


class TableEntry(BaseModel):
    """One table in the field-map data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: _Status
    source: str = Field(min_length=1)
    fields: Mapping[str, FieldSpec] = Field(default_factory=dict)


class FieldMap(BaseModel):
    """The packaged SAFE field-map file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tables: Mapping[str, TableEntry]


@dataclass(frozen=True, slots=True)
class MappedTable:
    """Rows with logical column names after field-map matching; `status` is the map entry's status."""

    table: str
    status: _Status
    rows: tuple[dict[str, Any], ...]
    columns_seen: tuple[str, ...]


def load_field_map(text: str) -> FieldMap:
    """Parse field-map TOML text into a `FieldMap`."""
    data = tomllib.loads(text)
    return FieldMap.model_validate(data)


@lru_cache(maxsize=1)
def safe_field_map() -> FieldMap:
    """Load the packaged SAFE field-map data (`products/_safe_tables.toml`)."""
    text = files("eng_harness.adapters.csi.products").joinpath("_safe_tables.toml").read_text(encoding="utf-8")
    return load_field_map(text)


def _incident(table: str, logical: str) -> str:
    """`incident_id` naming the table and logical column (AC13); kept within the contract's 64-character limit."""
    raw = f"{table}:{logical}"
    return raw if len(raw) <= 64 else f"{normalize_name(table)[:40]}:{logical}"[:64]


def _fail_internal(table: str, logical: str, columns_seen: Sequence[str], message: str) -> NoReturn:
    raise ContractError(
        ErrorCode.INTERNAL,
        message,
        incident_id=_incident(table, logical),
        received={"table": table, "logical": logical, "columns_seen": list(columns_seen)},
    )


def _resolve_columns(table: str, entry: TableEntry, columns: Sequence[str]) -> dict[str, str | None]:
    """Map each logical field to the reply column name, or `None` when an optional field is absent."""
    normalized = {normalize_name(col): col for col in columns}
    if len(normalized) != len(columns):
        # Two reply headers that normalize to the same token: treat as ambiguous for every logical that hits them.
        dupes = [col for col in columns if sum(1 for c in columns if normalize_name(c) == normalize_name(col)) > 1]
        _fail_internal(
            table,
            "columns",
            columns,
            f"{table}: reply columns normalize ambiguously ({sorted({normalize_name(c) for c in dupes})})",
        )
    binding: dict[str, str | None] = {}
    for logical, spec in entry.fields.items():
        accepted = spec.accepted()
        hits = [normalized[token] for token in accepted if token in normalized]
        if len(hits) > 1:
            _fail_internal(
                table,
                logical,
                columns,
                f"{table}: logical column {logical!r} matches several reply columns {hits}",
            )
        if len(hits) == 0:
            if spec.required:
                _fail_internal(
                    table,
                    logical,
                    columns,
                    f"{table}: required logical column {logical!r} is missing from the reply",
                )
            binding[logical] = None
            continue
        binding[logical] = hits[0]
    return binding


def map_rows(
    table: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    field_map: FieldMap | None = None,
) -> MappedTable:
    """Map host rows of `table` to logical column names through the field map (spec 0008 section 4.5, AC13).

    Raises:
        ContractError: `INTERNAL` when a required column is missing or more than one column matches a logical field.
        NotImplementedGap: the map entry's status is `unknown`.
        KeyError: `table` is not in the field map.
    """
    mapping = field_map if field_map is not None else safe_field_map()
    entry = mapping.tables[table]
    columns_seen = tuple(dict.fromkeys(key for row in rows for key in row))
    if not columns_seen and rows:
        columns_seen = tuple(rows[0].keys())
    if entry.status == "unknown":
        evidence = (table, *columns_seen)
        raise NotImplementedGap(
            f"table {table!r} has field-map status unknown until a recording sets its keys",
            evidence=evidence,
        )
    if not rows:
        return MappedTable(table, entry.status, (), columns_seen)
    # Use the union of keys across rows so a missing column on every row is still detected.
    all_columns = tuple(dict.fromkeys(key for row in rows for key in row))
    binding = _resolve_columns(table, entry, all_columns)
    mapped: list[dict[str, Any]] = []
    for row in rows:
        out: dict[str, Any] = {}
        for logical, host_col in binding.items():
            out[logical] = None if host_col is None else row.get(host_col)
        mapped.append(out)
    return MappedTable(table, entry.status, tuple(mapped), all_columns)


async def read_table(
    call: HostCall,
    *,
    product: str,
    pid: int,
    table: str,
    fields: Sequence[str] | None = None,
    group: str | None = None,
    row_limit: int = LIST_LIMIT,
    field_map: FieldMap | None = None,
) -> MappedTable:
    """Call `csi_db_table_read` and map the reply through the field map; `truncated` is `LIMIT_EXCEEDED`."""
    arguments: dict[str, Any] = {
        "target": {"product": product, "pid": pid},
        "table": table,
        "row_limit": row_limit,
    }
    if fields is not None:
        arguments["fields"] = list(fields)
    if group is not None:
        arguments["group"] = group
    body = await call("csi_db_table_read", arguments, CallEffect.READ)
    rows = body.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ContractError(
            ErrorCode.HOST_ERROR,
            f"the reply of {table} has no usable rows",
            retryable=False,
            host_code="UNEXPECTED_REPLY",
            host_method="csi_db_table_read",
            field="rows",
        )
    if body.get("truncated"):
        raise ContractError(ErrorCode.LIMIT_EXCEEDED, f"{table} was truncated at {row_limit} rows", received=len(rows))
    return map_rows(table, rows, field_map=field_map)
