"""SAP2000 add-frame and area edits, identity map and SP-4 table-edit gaps (plan 0012 T5; spec 0012 AC11 to AC13).

`AddFrameByCoordArgs` / `AddAreaByCoordArgs` are the canonical models. Lengths are millimetres in, converted to the
call's units token (`kN_mm_C` keeps millimetres). The host ignores the requested frame name (spec 0012 section 4.1);
`record_name` keeps the requested→host map for the ledger and later steps. Table-backed edit kinds raise SP-4.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from typing import NoReturn, cast

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import ParamModel, eng_param
from eng_contract.quantity import Quantity
from pydantic import Field, JsonValue

from eng_harness.adapters._args import convert_quantities
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._toolport import Binding, Builder
from eng_harness.adapters.csi._gaps import raise_gap

_Args = dict[str, JsonValue]

__all__ = [
    "EDIT_BUILDERS",
    "EDIT_MODELS",
    "TOKENS",
    "AddAreaByCoordArgs",
    "AddFrameByCoordArgs",
    "clear_name_map",
    "name_map",
    "record_name",
    "refuse_table_edit",
    "require_section",
]

TOKENS = {
    "csi_add_frame_by_coord": "kN_mm_C",
    "csi_add_area_by_coord": "kN_mm_C",
}

_TABLE_EDITS = {
    "set_frame_load_distributed": "SP-4",
    "set_area_load_uniform": "SP-4",
    "set_point_restraint": "SP-4",
    "set_point_load": "SP-4",
    "assign_area_section": "SP-4",
}

_NAME_MAP: dict[str, str] = {}


class AddFrameByCoordArgs(ParamModel):
    """`csi_add_frame_by_coord`: end points in millimetres; the host may ignore `name` (spec 0012 AC11)."""

    model: str
    section: str
    xi_mm: float = eng_param(unit="mm", ref_capable=True, engineering_quantity=True)
    yi_mm: float = eng_param(unit="mm", ref_capable=True, engineering_quantity=True)
    zi_mm: float = eng_param(unit="mm", ref_capable=True, engineering_quantity=True)
    xj_mm: float = eng_param(unit="mm", ref_capable=True, engineering_quantity=True)
    yj_mm: float = eng_param(unit="mm", ref_capable=True, engineering_quantity=True)
    zj_mm: float = eng_param(unit="mm", ref_capable=True, engineering_quantity=True)
    name: str | None = None


class AddAreaByCoordArgs(ParamModel):
    """`csi_add_area_by_coord`: boundary points as [x, y, z] in millimetres (spec 0012 AC13).

    The field is `points` (not `points_mm`) because ParamModel forbids a `_mm` suffix on a non-quantity list; values
    are always millimetres in and converted to the call's length unit in the builder.
    """

    model: str
    section: str
    points: list[list[float]] = Field(min_length=3)
    name: str | None = None


def name_map() -> Mapping[str, str]:
    """Requested frame name → host-assigned name (spec 0012 AC11)."""
    return dict(_NAME_MAP)


def clear_name_map() -> None:
    """Drop every recorded name (tests and a fresh run)."""
    _NAME_MAP.clear()


def record_name(requested: str | None, host: str) -> None:
    """Record the host name for `requested` when the caller supplied one (spec 0012 AC11)."""
    if requested:
        _NAME_MAP[requested] = host


def require_section(section: str, sections: set[str]) -> None:
    """Raise `NOT_FOUND` (`field: section`) when `section` is absent or the list is empty (spec 0012 section 6)."""
    if section not in sections:
        raise ContractError(ErrorCode.NOT_FOUND, f"section {section!r} is not in the model", field="section")


def refuse_table_edit(kind: str) -> NoReturn:
    """Raise `NotImplementedGap` SP-4 for an edit whose read-back needs a table (spec 0012 AC13)."""
    raise_gap(_TABLE_EDITS[kind])


def _builder[M: ParamModel](cls: type[M], build: Callable[[M, Binding], _Args]) -> Builder:
    def run(model: ParamModel, descriptor: ToolDescriptor, binding: Binding) -> _Args:
        if not isinstance(model, cls):
            raise TypeError(f"{descriptor.name} builds from {cls.__name__}, not {type(model).__name__}")
        return build(model, binding)

    return run


def _num(value: object) -> float:
    if isinstance(value, Quantity):
        return float(value.value)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"expected a number, got {type(value).__name__}")
    return float(value)


def _frame(m: AddFrameByCoordArgs, b: Binding) -> _Args:
    converted = convert_quantities(m, b.units_system or "")
    args: _Args = {
        "section": m.section,
        "start": [converted["xi_mm"], converted["yi_mm"], converted["zi_mm"]],
        "end": [converted["xj_mm"], converted["yj_mm"], converted["zj_mm"]],
    }
    if m.name is not None:
        args["name"] = m.name
    return args


def _area(m: AddAreaByCoordArgs, b: Binding) -> _Args:
    # Canonical millimetres in; kN_mm_C keeps them, kN_m_C scales to metres.
    scale = 1.0
    if b.units_system == "kN_m_C":
        scale = 0.001
    points = [[_num(coord) * scale for coord in point] for point in m.points]
    args: _Args = {"section": m.section, "points": cast(JsonValue, points)}
    if m.name is not None:
        args["name"] = m.name
    return args


EDIT_MODELS: dict[str, type[ParamModel]] = {
    "AddFrameByCoordArgs": AddFrameByCoordArgs,
    "AddAreaByCoordArgs": AddAreaByCoordArgs,
}
EDIT_BUILDERS: dict[str, Builder] = {
    "csi_add_frame_by_coord": _builder(AddFrameByCoordArgs, _frame),
    "csi_add_area_by_coord": _builder(AddAreaByCoordArgs, _area),
}


def update_map(mapping: MutableMapping[str, str], requested: str | None, host: str) -> None:
    """Write `requested` → `host` into `mapping` when `requested` is set (test helper for a private map)."""
    if requested:
        mapping[requested] = host
