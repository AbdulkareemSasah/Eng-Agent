"""SAFE joint-load import and SAFE-only pattern mapping (plan 0008 T6; spec 0008 section 4.3, 4.4, AC14 to AC20).

`SetPointLoadArgs` is the canonical model for `csi_set_point_load`. Import validates every row before the first write,
orders by `(joint, pattern)`, skips or refuses all-zero rows (AC15), and passes the units token `kN_m_C` (AC17).
`superimposed_dead` maps to `SuperDead` when the product profile carries joint-load tables (SAFE); `roof_live` stays
gap H-G3. Units: canonical `kN` / `kN.m` in, token units out via `eng_contract.units`. No engineering number is
invented here.
"""

# B-215: FX_kN..MZ_kNm are the contract wire names of harness.joint_loads/1 (spec 0008 section 4.3).

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from eng_contract.envelope import Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.kinds.model import PatternType
from eng_contract.params import ParamModel, eng_param
from eng_contract.quantity import Quantity
from pydantic import JsonValue

from eng_harness._kinds import JointLoad, JointLoads
from eng_harness.adapters._args import convert_quantities
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._toolport import Binding, Builder
from eng_harness.adapters.csi import _edits as edits
from eng_harness.adapters.csi import products
from eng_harness.adapters.csi._gaps import raise_gap
from eng_harness.errors import NotImplementedGap

_Args = dict[str, JsonValue]

__all__ = [
    "EDIT_BUILDERS",
    "EDIT_MODELS",
    "SAFE_PATTERN",
    "TOKENS",
    "ImportResult",
    "ImportWarning",
    "SetPointLoadArgs",
    "import_joint_loads",
    "validate_import",
]

TOKENS = {"csi_set_point_load": "kN_m_C"}  # spec 0008 AC14, AC17: always the force/moment token

# Spec 0008 section 4.4: SuperDead is SAFE-only (Sasaah SafePhase.EnsurePatterns / SAFE 22 "Super Dead").
SAFE_PATTERN: dict[PatternType, str] = {
    PatternType.DEAD: "Dead",
    PatternType.LIVE: "Live",
    PatternType.SEISMIC: "Quake",
    PatternType.WIND: "Wind",
    PatternType.SNOW: "Snow",
    PatternType.OTHER: "Other",
    PatternType.SUPERIMPOSED_DEAD: "SuperDead",
}
_TYPE_GAP = "H-G3"
_FORCE_FIELDS = ("FX_kN", "FY_kN", "FZ_kN", "MX_kNm", "MY_kNm", "MZ_kNm")


class SetPointLoadArgs(ParamModel):
    """`csi_set_point_load`: one joint load in canonical kN / kN.m (spec 0008 section 4.3, AC14).

    `punch_x_mm` / `punch_y_mm` are not sent to the host (gap SG-7); when set they are the pre-write punching
    dimensions that `check_model` must still read (AC18).
    """

    model: str
    joint: str
    pattern: str
    FX_kN: float = eng_param(unit="kN", ref_capable=True, engineering_quantity=True)
    FY_kN: float = eng_param(unit="kN", ref_capable=True, engineering_quantity=True)
    FZ_kN: float = eng_param(unit="kN", ref_capable=True, engineering_quantity=True)
    MX_kNm: float = eng_param(unit="kN.m", ref_capable=True, engineering_quantity=True)
    MY_kNm: float = eng_param(unit="kN.m", ref_capable=True, engineering_quantity=True)
    MZ_kNm: float = eng_param(unit="kN.m", ref_capable=True, engineering_quantity=True)
    punch_x_mm: float | None = eng_param(unit="mm", default=None)
    punch_y_mm: float | None = eng_param(unit="mm", default=None)


def _num(value: Any) -> float:
    return float(value.value if isinstance(value, Quantity) else value)


def _builder[M: ParamModel](cls: type[M], build: Callable[[M, Binding], _Args]) -> Builder:
    def run(model: ParamModel, descriptor: ToolDescriptor, binding: Binding) -> _Args:
        if not isinstance(model, cls):
            raise TypeError(f"{descriptor.name} builds from {cls.__name__}, not {type(model).__name__}")
        return build(model, binding)

    return run


def _point_load(m: SetPointLoadArgs, b: Binding) -> _Args:
    converted = convert_quantities(m, b.units_system or "")
    return {
        "name": m.joint,
        "load_pattern": m.pattern,
        "force": [converted["FX_kN"], converted["FY_kN"], converted["FZ_kN"]],
        "moment": [converted["MX_kNm"], converted["MY_kNm"], converted["MZ_kNm"]],
    }


_ETABS_PATTERN: dict[PatternType, str] = {
    kind: name for kind, name in SAFE_PATTERN.items() if kind is not PatternType.SUPERIMPOSED_DEAD
}


def _safe_pattern(m: edits.AddLoadPatternArgs, b: Binding) -> _Args:
    """0002 section 4.6.2 mapping, plus SuperDead when the profile has joint-load tables (SAFE; AC20)."""
    profile = products.profile(b.target.product)
    table: Mapping[PatternType, str] = SAFE_PATTERN if "joint_loads" in profile.tables else _ETABS_PATTERN
    if m.type not in table:
        raise NotImplementedGap(f"the pattern type {m.type.value} is not implemented", evidence=(_TYPE_GAP,))
    ratio = m.self_weight_ratio
    return {
        "name": m.name,
        "type": table[m.type],
        "self_weight": ratio.value if isinstance(ratio, Quantity) else ratio,
    }


EDIT_MODELS: dict[str, type[ParamModel]] = {"SetPointLoadArgs": SetPointLoadArgs}
EDIT_BUILDERS: dict[str, Builder] = {
    "csi_set_point_load": _builder(SetPointLoadArgs, _point_load),
    "csi_add_load_pattern": _builder(edits.AddLoadPatternArgs, _safe_pattern),
}


@dataclass(frozen=True)
class ImportWarning:
    """A non-issue warning of the joint-load import (spec 0008 A1: `ZERO_LOAD_SKIPPED`)."""

    code: str
    message: str


@dataclass
class ImportResult:
    """How many rows were written and which warnings the import raised."""

    written: int = 0
    warnings: list[ImportWarning] = field(default_factory=list)


def _zero(row: JointLoad) -> bool:
    return all(_num(getattr(row, name)) == 0.0 for name in ("fx_kn", "fy_kn", "fz_kn", "mx_knm", "my_knm", "mz_knm"))


def validate_import(
    payload: JointLoads,
    *,
    joints: set[str],
    patterns: set[str],
    existing: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[ImportWarning]:
    """Validate every row before any write (AC15, AC16). Raises `NOT_FOUND` or `NotImplementedGap` (SG-7, SG-8)."""
    warnings: list[ImportWarning] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(payload.loads):
        key = (row.joint, row.pattern)
        field = f"loads[{index}]"
        if key in seen:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"joint-load rows must be unique on (joint, pattern): {row.joint!r}, {row.pattern!r}",
                field=field,
            )
        seen.add(key)
        if row.punch_x_mm is not None or row.punch_y_mm is not None:
            raise_gap("SG-7")
        if row.joint not in joints:
            raise ContractError(ErrorCode.NOT_FOUND, f"joint {row.joint!r} is not in the model", field=field)
        if row.pattern not in patterns:
            raise ContractError(ErrorCode.NOT_FOUND, f"pattern {row.pattern!r} is not in the model", field=field)
        if _zero(row):
            if key in existing:
                raise_gap("SG-8")
            warnings.append(
                ImportWarning(
                    code="ZERO_LOAD_SKIPPED",
                    message=f"zero load on joint {row.joint!r} pattern {row.pattern!r} skipped: nothing to clear",
                )
            )
    return warnings


def _ordered(loads: Sequence[JointLoad]) -> list[JointLoad]:
    return sorted(loads, key=lambda row: (row.joint, row.pattern))


async def import_joint_loads(
    port: Any,
    host: Any,
    model_key: str,
    payload: JointLoads,
    *,
    op_id_prefix: str,
) -> ImportResult:
    """Import `harness.joint_loads/1`: validate all rows, then one `csi_set_point_load` per non-skipped row (AC14-AC17).

    Each call uses its own `op_id` (`{op_id_prefix}-{n}`). Engineering quantities are stored as a result and passed as
    references (engine invariant 2). The units token is always `kN_m_C`.
    """
    held = await host.locate(model_key)
    if held is None or held.instance_id is None:
        raise ContractError(
            ErrorCode.PRECONDITION_FAILED,
            "no open model for the joint-load import",
            precondition=Precondition.model_open,
        )
    await host.model_state(model_key, held.instance_id)
    state = host.last_read(model_key)
    if state is None:
        raise ContractError(ErrorCode.INTERNAL, "joint-load import: model state was not retained after the read")
    points = state.payloads["harness.model_points/1"].model_dump(mode="json")["points"]
    patterns = state.payloads["model.load_set/1"].model_dump(mode="json")["patterns"]
    joint_rows = state.payloads["harness.joint_loads/1"].model_dump(mode="json")["loads"]
    joints = {str(row["name"]) for row in points}
    pattern_names = {str(row["name"]) for row in patterns}
    existing = {(str(row["joint"]), str(row["pattern"])): row for row in joint_rows}
    warnings = validate_import(payload, joints=joints, patterns=pattern_names, existing=existing)
    skip_keys = {
        (row.joint, row.pattern) for row in payload.loads if _zero(row) and (row.joint, row.pattern) not in existing
    }
    store = port._store  # B-215: same store the tool port validates refs against
    written = 0
    for index, row in enumerate(_ordered(payload.loads)):
        if (row.joint, row.pattern) in skip_keys:
            continue
        before = existing.get((row.joint, row.pattern), {})
        values = {
            "FX_kN": _num(row.fx_kn),
            "FY_kN": _num(row.fy_kn),
            "FZ_kN": _num(row.fz_kn),
            "MX_kNm": _num(row.mx_knm),
            "MY_kNm": _num(row.my_knm),
            "MZ_kNm": _num(row.mz_knm),
        }
        producer = Provenance(
            tool="harness/joint_loads_import",
            tool_version="1",
            inputs={},
            started_at="2026-01-01T00:00:00.000Z",
            duration_ms=0,
        )
        record = store.put("harness.run_input/1", {"value": values}, producer)
        args: _Args = {"model": model_key, "joint": row.joint, "pattern": row.pattern}
        for name in _FORCE_FIELDS:
            args[name] = {"$ref": f"{record.result_id}#/value/{name}"}
        # Pre-write punching dims for AC18 read-back; the builder does not send them (gap SG-7).
        if before.get("punch_x_mm") is not None:
            args["punch_x_mm"] = before["punch_x_mm"]
        if before.get("punch_y_mm") is not None:
            args["punch_y_mm"] = before["punch_y_mm"]
        reply = await port.call("csi_set_point_load", args, op_id=f"{op_id_prefix}-{index}", model=model_key)
        if not isinstance(reply, SuccessEnvelope):
            raise ContractError(ErrorCode.HOST_ERROR, f"joint-load import failed on {row.joint!r}/{row.pattern!r}")
        written += 1
    return ImportResult(written=written, warnings=warnings)
