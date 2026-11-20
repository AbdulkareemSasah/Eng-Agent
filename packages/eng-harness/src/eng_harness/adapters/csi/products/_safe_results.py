"""SAFE analysis and result readers (plan 0008 T7; spec 0008 section 4.6, AC21 to AC23).

Soil pressures are read through `csi_db_table_read` and the candidate field map (spec 0008 section 4.5). Truncation is
`LIMIT_EXCEEDED` with hint `group` (gap SG-6). Base reactions use the typed tool `csi_results_base_reactions` with units
token `kN_m_C`. Analysis Messages stay a gap until a recording promotes the unknown map entry. No engineering number is
invented; sign conventions stay `host_unconfirmed/1` (Q6).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, NoReturn

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import ParamModel
from eng_contract.units import convert, csi_unit_system
from pydantic import Field, JsonValue

from eng_harness._kinds import (
    BaseReactionRow,
    BaseReactions,
    HarnessCaseRef,
    SafeSoilPressureRow,
    SafeSoilPressures,
    SafeSoilPressureSummary,
)
from eng_harness.adapters._toolport import Binding, Reader
from eng_harness.adapters.csi import _replies, _tables
from eng_harness.adapters.csi._gaps import SAFE_GAPS
from eng_harness.adapters.csi._state import LIST_LIMIT, HostCall
from eng_harness.servers import CallEffect

__all__ = [
    "ANALYSIS_MODELS",
    "READERS",
    "TOKENS",
    "ResultsBaseReactionsArgs",
    "base_reactions",
    "read_analysis_messages",
    "read_soil_pressures",
]

SOIL_TABLE = "Soil Pressures"
MESSAGES_TABLE = "Analysis Messages"
_REACTION = {"FX_kN": "F1", "FY_kN": "F2", "FZ_kN": "F3", "MX_kNm": "M1", "MY_kNm": "M2", "MZ_kNm": "M3"}


class ResultsBaseReactionsArgs(ParamModel):
    """`csi_results_base_reactions`: load case and combination names (S-12 schema)."""

    model: str
    cases: list[str] = Field(default_factory=list)
    combos: list[str] = Field(default_factory=list)


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise TypeError(f"numeric table cell expected, got {type(value).__name__}")
    return float(value)


def _pressure_kpa(value: object, units: str) -> float:
    return convert(_as_float(value), csi_unit_system(units).stress, "kPa")


def _optional_name(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _case_ref(case: object, case_type: object | None) -> HarnessCaseRef:
    """Build a case ref; table `case_type` is optional and defaults to load_case when absent."""
    raw = None if case_type is None or case_type == "" else str(case_type).strip().lower()
    if raw in ("load_combination", "combo", "combination"):
        kind: Literal["load_pattern", "load_case", "load_combination"] = "load_combination"
    elif raw in ("load_pattern", "pattern"):
        kind = "load_pattern"
    else:
        kind = "load_case"
    return HarnessCaseRef(case=str(case), case_type=kind, step=None)


def _unique_key(row: SafeSoilPressureRow) -> tuple[object, ...]:
    return (row.area, row.element, row.joint, row.case.case, row.step_type)


def soil_pressures_from_mapped(
    mapped: _tables.MappedTable,
    *,
    units: str,
    cases: Sequence[str] | None = None,
) -> SafeSoilPressures:
    """Map a field-mapped Soil Pressures table to `harness.safe_soil_pressures/1` (AC22)."""
    wanted = {name for name in (cases or ()) if name}
    rows: list[SafeSoilPressureRow] = []
    for raw in mapped.rows:
        case_name = raw.get("case")
        if case_name is None or case_name == "":
            raise ContractError(
                ErrorCode.INTERNAL,
                f"{SOIL_TABLE}: a row is missing the required case column",
                incident_id="Soil Pressures:case",
                received={"table": SOIL_TABLE, "logical": "case", "columns_seen": list(mapped.columns_seen)},
            )
        if wanted and str(case_name) not in wanted:
            continue
        row = SafeSoilPressureRow(
            area=_optional_name(raw.get("area")),
            element=_optional_name(raw.get("element")),
            joint=_optional_name(raw.get("joint")),
            case=_case_ref(case_name, raw.get("case_type")),
            step_type=_optional_name(raw.get("step_type")),
            case_type=_optional_name(raw.get("case_type")),
            pressure_kpa=_pressure_kpa(raw.get("pressure"), units),
        )
        rows.append(row)
    seen: dict[tuple[object, ...], SafeSoilPressureRow] = {}
    for row in rows:
        key = _unique_key(row)
        if key in seen:
            raise ContractError(
                ErrorCode.INTERNAL,
                f"{SOIL_TABLE}: key (area, element, joint, case, step_type) is not unique",
                incident_id="Soil Pressures:unique_key",
                received={"table": SOIL_TABLE, "logical": "unique_key", "columns_seen": list(mapped.columns_seen)},
            )
        seen[key] = row
    pressures = [row.pressure_kpa for row in rows]
    summary = SafeSoilPressureSummary(
        count=len(rows),
        min_kpa=min(pressures) if pressures else 0.0,
        max_kpa=max(pressures) if pressures else 0.0,
    )
    status: Literal["candidate", "reference"] = "candidate" if mapped.status == "candidate" else "reference"
    return SafeSoilPressures(
        source_table=SOIL_TABLE,
        sign_convention="host_unconfirmed/1",
        field_map_status=status,
        rows=rows,
        summary=summary,
    )


async def read_soil_pressures(
    call: HostCall,
    *,
    product: str,
    pid: int,
    cases: Sequence[str],
    units: str,
    group: str | None = None,
    row_limit: int = LIST_LIMIT,
) -> SafeSoilPressures:
    """Read Soil Pressures; truncation is LIMIT_EXCEEDED with hint `group` (SG-6, AC22)."""
    arguments: dict[str, Any] = {
        "target": {"product": product, "pid": pid},
        "table": SOIL_TABLE,
        "row_limit": row_limit,
    }
    if group is not None:
        arguments["group"] = group
    body = await call("csi_db_table_read", arguments, CallEffect.READ)
    rows = body.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ContractError(
            ErrorCode.HOST_ERROR,
            f"the reply of {SOIL_TABLE} has no usable rows",
            retryable=False,
            host_code="UNEXPECTED_REPLY",
            host_method="csi_db_table_read",
            field="rows",
        )
    if body.get("truncated"):
        raise ContractError(
            ErrorCode.LIMIT_EXCEEDED,
            f"{SAFE_GAPS['SG-6']} (SG-6)",
            received=len(rows),
            hint="group",
        )
    mapped = _tables.map_rows(SOIL_TABLE, rows)
    return soil_pressures_from_mapped(mapped, units=units, cases=cases)


async def read_analysis_messages(call: HostCall, *, product: str, pid: int) -> NoReturn:
    """Reading Analysis Messages is a gap until a recording sets its keys (AC23, AC13)."""
    arguments: dict[str, Any] = {
        "target": {"product": product, "pid": pid},
        "table": MESSAGES_TABLE,
        "row_limit": LIST_LIMIT,
    }
    body = await call("csi_db_table_read", arguments, CallEffect.READ)
    rows = body.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        rows = []
    _tables.map_rows(MESSAGES_TABLE, rows)  # raises NotImplementedGap for unknown
    raise AssertionError("Analysis Messages map entry must stay unknown until recorded")


def _case_ref_from_host(row: Mapping[str, Any]) -> dict[str, Any]:
    step = row.get("step")
    return {
        "case": str(row["case"]),
        "case_type": "load_combination" if row.get("kind") == "combo" else "load_case",
        "step": None if step in (None, "") else str(step),
    }


def _scaled(row: Mapping[str, Any], units: str, fields: Mapping[str, str]) -> dict[str, float]:
    system = csi_unit_system(units)
    unit_of = {"kN": ("force", "kN"), "kNm": ("moment", "kN.m")}
    scaled: dict[str, float] = {}
    for name, key in fields.items():
        member, unit = unit_of[name.rpartition("_")[2]]
        scaled[name] = convert(float(row[key]), getattr(system, member), unit)
    return scaled


def base_reactions(reply: Mapping[str, Any], units: str) -> BaseReactions:
    """Map `csi_results_base_reactions` to `harness.base_reactions/1` (AC23)."""
    items = reply.get("items")
    if not isinstance(items, list) or not all(isinstance(row, dict) for row in items):
        raise ContractError(
            ErrorCode.HOST_ERROR,
            "the reply of csi_results_base_reactions has no usable items",
            retryable=False,
            host_code="UNEXPECTED_REPLY",
            host_method="csi_results_base_reactions",
            field="items",
        )
    rows = [
        BaseReactionRow.model_validate({"case": _case_ref_from_host(row), **_scaled(row, units, _REACTION)})
        for row in items
    ]
    return BaseReactions(moment_reference="host_unconfirmed/1", rows=rows)


def _reader(mapper: Any) -> Reader:
    def read(reply: Mapping[str, JsonValue], binding: Binding) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
        return mapper(reply, binding).model_dump(mode="json"), {}

    return read


READERS: dict[str, Reader] = {
    "csi_results_base_reactions": _reader(lambda r, b: base_reactions(r, b.units_system or "")),
    # Re-export shared analysis readers so tests can discover them on this module (AC21, AC23).
    "csi_run_analysis": _reader(lambda r, b: _replies.analysis_run(r)),
    "csi_analysis_status": _reader(lambda r, b: _replies.analysis_status(r)),
}

TOKENS = {"csi_results_base_reactions": "kN_m_C"}  # spec 0008 section 4.6: force/moment results

ANALYSIS_MODELS: dict[str, type[ParamModel]] = {
    "ResultsBaseReactionsArgs": ResultsBaseReactionsArgs,
}
