"""Calc `harness.footing_resize` v1: one step of plan, depth or spacing change (spec 0010 §4.4.4).

Purpose: apply one resize action per footing (enlarge plan, deepen, reduce spacing, engineer set, or none)
using exact fractions. Engineer values are one triple of top-level references per call (calcs §4.7).
Units: millimetres. Errors: `ContractError` for a missing or unusable basis field, a missing action, an
unknown action, or a non-finite dimension.
"""

from enum import StrEnum
from fractions import Fraction
from typing import Literal

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import BasisField, DesignBasis
from eng_contract.params import eng_param
from eng_contract.quantity import Quantity
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.footing import DimRow, FootingDims

__all__ = ["BASIS_FIELDS", "ResizeAction", "ResizeBody", "ResizeInput", "footing_resize"]

_METHOD = "eng-harness spec 0010 §4.4.4"
_PLAN_INC = "foundation.plan_increment_mm"
_PLAN_MIN = "foundation.min_plan_dimension_mm"
_PLAN_MAX = "foundation.max_plan_dimension_mm"
_DEPTH_INC = "foundation.depth_increment_mm"
_DEPTH_MIN = "foundation.min_depth_mm"
_DEPTH_MAX = "foundation.max_depth_mm"
_SPACE_INC = "reinforcement.spacing_increment_mm"
_SPACE_MIN = "reinforcement.min_spacing_mm"
_SPACE_MAX = "reinforcement.max_spacing_mm"
_QUANTITIES = (
    (_PLAN_INC, True),
    (_PLAN_MIN, True),
    (_PLAN_MAX, True),
    (_DEPTH_INC, True),
    (_DEPTH_MIN, True),
    (_DEPTH_MAX, True),
    (_SPACE_INC, True),
    (_SPACE_MIN, True),
    (_SPACE_MAX, True),
)
BASIS_FIELDS = tuple(path for path, _ in _QUANTITIES)
"""The nine design-basis paths of spec 0010 §4.4.4 (amendment B-567, OQ-Q64)."""

ZERO = Cited(value=0, unit="1", source="Spec 0010 §4.4.4: lengths are positive; plans are counted from zero")
ONE = Cited(value=1, unit="1", source="Spec 0010 §4.4.4 R1: next plan multiple is (floor(L/i) + 1)·i")
VERSION = Cited(value=1, unit="1", source="Calc version 1 of spec 0010 §4.4.4; a change of method is a new version")
# Status strings of §4.4.4 / Q13 / Q17 (not Cited: Cited holds numbers only).
_STATUS_OK = "OK"
_STATUS_LIMIT = "LIMIT_REACHED"
_STATUS_OUTSIDE = "OUTSIDE_BASIS_BOUNDS"
_STATUS_OFF = "OFF_INCREMENT"


class ResizeAction(StrEnum):
    """Per-footing resize action (spec 0010 §4.4.4)."""

    ENLARGE_PLAN = "enlarge_plan"
    INCREASE_DEPTH = "increase_depth"
    REDUCE_BAR_SPACING = "reduce_bar_spacing"
    ENGINEER_SET = "engineer_set"
    NONE = "none"


class ResizeInput(CalcInput):
    """Trial dims, one action per footing, the engineer triple, and the nine basis fields.

    Optional `keep`: when set, only those footing ids from `dims` are resized and returned (spec 0010 §4.6
    open-only rounds; closed footings are dropped from the next dims). Every kept id still needs an action.
    """

    dims: FootingDims = eng_param(ref_capable=True, ref_kinds={"harness.footing_dims/1"}, engineering_quantity=True)
    actions: dict[str, ResizeAction] = eng_param()
    engineer_plan: Quantity = eng_param(
        unit="mm",
        gt=ZERO.value,
        bounds_source=ZERO.source,
        ref_capable=True,
        engineering_quantity=True,
    )
    engineer_depth: Quantity = eng_param(
        unit="mm",
        gt=ZERO.value,
        bounds_source=ZERO.source,
        ref_capable=True,
        engineering_quantity=True,
    )
    engineer_spacing: Quantity = eng_param(
        unit="mm",
        gt=ZERO.value,
        bounds_source=ZERO.source,
        ref_capable=True,
        engineering_quantity=True,
    )
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)
    keep: list[str] | None = None


class ResizeBody(BaseModel):
    """The body of `harness.footing_dims/1` before the calc port attaches metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    footings: list[DimRow]


def _basis_field(basis: DesignBasis, path: str) -> BasisField:
    field = basis.fields.get(path)
    if field is None or not field.confirmed:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {path} is missing or not confirmed",
            field="basis",
            hint=f"confirm {path}",
        )
    if field.unit != "mm":
        raise ContractError(
            ErrorCode.UNIT_MISMATCH,
            f"basis field {path} has the wrong unit",
            field="basis",
            expected={"unit": "mm"},
            received=field.unit,
        )
    return field


def _read_quantities(basis: DesignBasis, ref: str, trace: TraceBuilder) -> dict[str, Fraction]:
    quantities: dict[str, Fraction] = {}
    for path, positive in _QUANTITIES:
        raw = _basis_field(basis, path).value
        number = as_fraction(raw)
        if number is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, f"basis field {path} must be a finite number", field="basis"
            )
        if number < ZERO.value or (positive and number == ZERO.value):
            bound = "gt" if positive else "min"
            raise ContractError(
                ErrorCode.OUT_OF_RANGE,
                f"basis field {path} is outside its physical bounds",
                field="basis",
                expected={bound: ZERO.value},
                received=raw,
            )
        name = path.rpartition(".")[2]
        trace.input(name, raw, unit="mm", ref=f"{ref}#/fields/{path}")
        quantities[name] = number
    return quantities


def _fraction_mm(value: float, footing_id: str, field: str) -> Fraction:
    number = as_fraction(value)
    if number is None:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            f"footing {footing_id} has a non-finite {field}",
            field="dims",
        )
    return number


def _row(
    footing_id: str,
    plan: Fraction,
    depth: Fraction,
    spacing: Fraction,
    *,
    source: Literal["calc", "engineer"],
    status: str,
    reason: str | None,
    plan_at_max: bool,
    depth_at_max: bool,
    spacing_at_min: bool,
) -> DimRow:
    return DimRow(
        id=footing_id,
        Lx_mm=float(plan),
        Ly_mm=float(plan),
        h_mm=float(depth),
        s_mm=float(spacing),
        source=source,
        plan_at_max=plan_at_max,
        depth_at_max=depth_at_max,
        spacing_at_min=spacing_at_min,
        status=status,
        reason=reason,
    )


def _enlarge_plan(row: DimRow, quantities: dict[str, Fraction], trace: TraceBuilder, prefix: str) -> DimRow:
    plan = _fraction_mm(row.Lx_mm, row.id, "Lx_mm")
    depth = _fraction_mm(row.h_mm, row.id, "h_mm")
    spacing = _fraction_mm(row.s_mm, row.id, "s_mm")
    increment = quantities["plan_increment_mm"]
    maximum = quantities["max_plan_dimension_mm"]
    nxt = (plan // increment + Fraction(ONE.value)) * increment
    trace.step(
        f"{prefix}_next_plan_mm",
        str(nxt),
        unit="mm",
        formula="(floor(L / i) + 1) * i on exact fractions",
        source=f"{_METHOD} R1",
        uses=[f"{prefix}_L_mm", "plan_increment_mm"],
    )
    if nxt > maximum:
        trace.step(
            f"{prefix}_plan_mm",
            float(plan),
            unit="mm",
            formula="unchanged: next plan above max_plan_dimension_mm",
            source=f"{_METHOD} R1",
            uses=[f"{prefix}_next_plan_mm", "max_plan_dimension_mm"],
        )
        return _row(
            row.id,
            plan,
            depth,
            spacing,
            source=row.source,
            status=_STATUS_LIMIT,
            reason=None,
            plan_at_max=True,
            depth_at_max=row.depth_at_max,
            spacing_at_min=row.spacing_at_min,
        )
    trace.step(
        f"{prefix}_plan_mm",
        float(nxt),
        unit="mm",
        formula="next multiple of plan_increment_mm above L",
        source=f"{_METHOD} R1",
        uses=[f"{prefix}_next_plan_mm"],
    )
    return _row(
        row.id,
        nxt,
        depth,
        spacing,
        source=row.source,
        status=_STATUS_OK,
        reason=None,
        plan_at_max=False,
        depth_at_max=row.depth_at_max,
        spacing_at_min=row.spacing_at_min,
    )


def _increase_depth(row: DimRow, quantities: dict[str, Fraction], trace: TraceBuilder, prefix: str) -> DimRow:
    plan = _fraction_mm(row.Lx_mm, row.id, "Lx_mm")
    depth = _fraction_mm(row.h_mm, row.id, "h_mm")
    spacing = _fraction_mm(row.s_mm, row.id, "s_mm")
    increment = quantities["depth_increment_mm"]
    maximum = quantities["max_depth_mm"]
    nxt = depth + increment
    trace.step(
        f"{prefix}_next_depth_mm",
        str(nxt),
        unit="mm",
        formula="h + depth_increment_mm",
        source=f"{_METHOD} R2",
        uses=[f"{prefix}_h_mm", "depth_increment_mm"],
    )
    if nxt > maximum:
        trace.step(
            f"{prefix}_depth_mm",
            float(depth),
            unit="mm",
            formula="unchanged: next depth above max_depth_mm",
            source=f"{_METHOD} R2",
            uses=[f"{prefix}_next_depth_mm", "max_depth_mm"],
        )
        return _row(
            row.id,
            plan,
            depth,
            spacing,
            source=row.source,
            status=_STATUS_LIMIT,
            reason=None,
            plan_at_max=row.plan_at_max,
            depth_at_max=True,
            spacing_at_min=row.spacing_at_min,
        )
    trace.step(
        f"{prefix}_depth_mm",
        float(nxt),
        unit="mm",
        formula="h + depth_increment_mm",
        source=f"{_METHOD} R2",
        uses=[f"{prefix}_next_depth_mm"],
    )
    return _row(
        row.id,
        plan,
        nxt,
        spacing,
        source=row.source,
        status=_STATUS_OK,
        reason=None,
        plan_at_max=row.plan_at_max,
        depth_at_max=False,
        spacing_at_min=row.spacing_at_min,
    )


def _reduce_spacing(row: DimRow, quantities: dict[str, Fraction], trace: TraceBuilder, prefix: str) -> DimRow:
    plan = _fraction_mm(row.Lx_mm, row.id, "Lx_mm")
    depth = _fraction_mm(row.h_mm, row.id, "h_mm")
    spacing = _fraction_mm(row.s_mm, row.id, "s_mm")
    increment = quantities["spacing_increment_mm"]
    minimum = quantities["min_spacing_mm"]
    nxt = spacing - increment
    trace.step(
        f"{prefix}_next_spacing_mm",
        str(nxt),
        unit="mm",
        formula="s - spacing_increment_mm",
        source=f"{_METHOD} R3",
        uses=[f"{prefix}_s_mm", "spacing_increment_mm"],
    )
    if nxt < minimum:
        trace.step(
            f"{prefix}_spacing_mm",
            float(spacing),
            unit="mm",
            formula="unchanged: next spacing below min_spacing_mm",
            source=f"{_METHOD} R3",
            uses=[f"{prefix}_next_spacing_mm", "min_spacing_mm"],
        )
        return _row(
            row.id,
            plan,
            depth,
            spacing,
            source=row.source,
            status=_STATUS_LIMIT,
            reason=None,
            plan_at_max=row.plan_at_max,
            depth_at_max=row.depth_at_max,
            spacing_at_min=True,
        )
    trace.step(
        f"{prefix}_spacing_mm",
        float(nxt),
        unit="mm",
        formula="s - spacing_increment_mm",
        source=f"{_METHOD} R3",
        uses=[f"{prefix}_next_spacing_mm"],
    )
    return _row(
        row.id,
        plan,
        depth,
        nxt,
        source=row.source,
        status=_STATUS_OK,
        reason=None,
        plan_at_max=row.plan_at_max,
        depth_at_max=row.depth_at_max,
        spacing_at_min=False,
    )


def _engineer_set(
    row: DimRow,
    plan: Fraction,
    depth: Fraction,
    spacing: Fraction,
    quantities: dict[str, Fraction],
    trace: TraceBuilder,
    prefix: str,
) -> DimRow:
    increment = quantities["plan_increment_mm"]
    min_plan = quantities["min_plan_dimension_mm"]
    max_plan = quantities["max_plan_dimension_mm"]
    min_depth = quantities["min_depth_mm"]
    max_depth = quantities["max_depth_mm"]
    min_spacing = quantities["min_spacing_mm"]
    max_spacing = quantities["max_spacing_mm"]
    outside = (
        plan < min_plan
        or plan > max_plan
        or depth < min_depth
        or depth > max_depth
        or spacing < min_spacing
        or spacing > max_spacing
    )
    off_increment = plan % increment != ZERO.value
    if outside:
        status = _STATUS_OUTSIDE
        reason = _STATUS_OFF if off_increment else None
    elif off_increment:
        status = _STATUS_OFF
        reason = None
    else:
        status = _STATUS_OK
        reason = None
    trace.step(
        f"{prefix}_plan_mm",
        float(plan),
        unit="mm",
        formula="engineer L; Lx = Ly = L",
        source=f"{_METHOD} R4",
        uses=[f"{prefix}_engineer_plan_mm"],
    )
    trace.step(
        f"{prefix}_depth_mm",
        float(depth),
        unit="mm",
        formula="engineer h",
        source=f"{_METHOD} R4",
        uses=[f"{prefix}_engineer_depth_mm"],
    )
    trace.step(
        f"{prefix}_spacing_mm",
        float(spacing),
        unit="mm",
        formula="engineer s",
        source=f"{_METHOD} R4",
        uses=[f"{prefix}_engineer_spacing_mm"],
    )
    return _row(
        row.id,
        plan,
        depth,
        spacing,
        source="engineer",
        status=status,
        reason=reason,
        plan_at_max=False,
        depth_at_max=False,
        spacing_at_min=False,
    )


def _apply(
    row: DimRow,
    action: ResizeAction,
    quantities: dict[str, Fraction],
    engineer: tuple[Fraction, Fraction, Fraction],
    meta: InputMeta,
    trace: TraceBuilder,
    index: int,
) -> DimRow:
    prefix = f"footing_{index}"
    if row.Lx_mm != row.Ly_mm:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            f"footing {row.id} is not square (FG-1)",
            field="dims",
        )
    trace.input(f"{prefix}_id", row.id, ref=f"{meta.refs['dims'].result_id}#/footings/{index}/id")
    trace.input(f"{prefix}_L_mm", row.Lx_mm, unit="mm", ref=f"{meta.refs['dims'].result_id}#/footings/{index}/Lx_mm")
    trace.input(f"{prefix}_h_mm", row.h_mm, unit="mm", ref=f"{meta.refs['dims'].result_id}#/footings/{index}/h_mm")
    trace.input(f"{prefix}_s_mm", row.s_mm, unit="mm", ref=f"{meta.refs['dims'].result_id}#/footings/{index}/s_mm")
    trace.input(f"{prefix}_action", action.value)
    if action is ResizeAction.NONE:
        trace.output(f"{prefix}_L_mm", f"{prefix}_h_mm", f"{prefix}_s_mm")
        return row
    if action is ResizeAction.ENLARGE_PLAN:
        out = _enlarge_plan(row, quantities, trace, prefix)
        trace.output(f"{prefix}_plan_mm")
        return out
    if action is ResizeAction.INCREASE_DEPTH:
        out = _increase_depth(row, quantities, trace, prefix)
        trace.output(f"{prefix}_depth_mm")
        return out
    if action is ResizeAction.REDUCE_BAR_SPACING:
        out = _reduce_spacing(row, quantities, trace, prefix)
        trace.output(f"{prefix}_spacing_mm")
        return out
    eng_plan, eng_depth, eng_spacing = engineer
    trace.input(
        f"{prefix}_engineer_plan_mm",
        float(eng_plan),
        unit="mm",
        ref=meta.refs["engineer_plan"].result_id,
    )
    trace.input(
        f"{prefix}_engineer_depth_mm",
        float(eng_depth),
        unit="mm",
        ref=meta.refs["engineer_depth"].result_id,
    )
    trace.input(
        f"{prefix}_engineer_spacing_mm",
        float(eng_spacing),
        unit="mm",
        ref=meta.refs["engineer_spacing"].result_id,
    )
    out = _engineer_set(row, eng_plan, eng_depth, eng_spacing, quantities, trace, prefix)
    trace.output(f"{prefix}_plan_mm", f"{prefix}_depth_mm", f"{prefix}_spacing_mm")
    return out


@calc(
    id="harness.footing_resize",
    version=int(VERSION.value),
    output_kind="harness.footing_dims/1",
    title="One resize step for square isolated footings",
    method_source=f"{_METHOD} (R1 to R4)",
    verification="draft",
)
def footing_resize(inp: ResizeInput, meta: InputMeta, trace: TraceBuilder) -> ResizeBody:
    """Apply one action per footing; engineer_set uses the call's single L, h, s triple."""
    for name in ("dims", "basis", "engineer_plan", "engineer_depth", "engineer_spacing"):
        if name not in meta.refs:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"input {name} must be a record reference",
                field=name,
            )
    basis_ref = meta.refs["basis"].result_id
    quantities = _read_quantities(inp.basis, basis_ref, trace)
    trace.constant("zero", ZERO)
    trace.constant("one", ONE)
    plan = as_fraction(inp.engineer_plan.value)
    depth = as_fraction(inp.engineer_depth.value)
    spacing = as_fraction(inp.engineer_spacing.value)
    if plan is None or depth is None or spacing is None:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            "engineer plan, depth and spacing must be finite numbers",
            field="engineer_plan",
        )
    engineer = (plan, depth, spacing)
    source = list(inp.dims.footings)
    if inp.keep is not None:
        keep_ids = list(dict.fromkeys(inp.keep))
        by_id = {row.id: row for row in source}
        missing = [footing_id for footing_id in keep_ids if footing_id not in by_id]
        if missing:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"keep names unknown footing ids: {', '.join(missing)}",
                field="keep",
            )
        source = [by_id[footing_id] for footing_id in keep_ids]
    rows: list[DimRow] = []
    for index, row in enumerate(source):
        action = inp.actions.get(row.id)
        if action is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"actions has no entry for footing {row.id}",
                field="actions",
            )
        rows.append(_apply(row, action, quantities, engineer, meta, trace, index))
    allowed = {row.id for row in source}
    extra = sorted(set(inp.actions) - allowed)
    if extra:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            f"actions names unknown footing ids: {', '.join(extra)}",
            field="actions",
        )
    return ResizeBody(footings=rows)
