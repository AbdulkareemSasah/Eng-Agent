"""Calc `harness.footing_layout` v1: bar counts, areas, effective depths, cover and reaction height (spec 0010 4.4.3).

Purpose: given trial footing dimensions (`harness.footing_dims/1`), subjects and design basis, compute bottom-layer
bar counts and actual spacing (L1), steel areas (L2), effective depths (L3), cover (L4) and reaction height (L5).
Units: lengths in mm, steel areas in mm2. Span and depth comparisons are exact (`Fraction`).
Errors: `ContractError` `INVALID_ARGUMENT` (missing/unconfirmed/non-numeric/invalid-choice basis field, input without
record reference, or footing id not in `subjects`), `UNIT_MISMATCH` (wrong basis unit), `OUT_OF_RANGE` (non-positive
bar diameter, negative cover, or depth with no room for both bottom layers or unrepresentable bar count / float output
on field `dims`).
"""

import math
from enum import StrEnum
from fractions import Fraction
from typing import Any

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import BasisField, DesignBasis
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.footing import DesignRow, DimRow, FootingDims, FootingSubjects

__all__ = ["BASIS_FIELDS", "BottomLayer", "LayoutBody", "LayoutInput", "ReactionPoint", "footing_layout"]

_BAR_DIAMETER = "reinforcement.bar_diameter_mm"
_BOTTOM_LAYER = "reinforcement.bottom_layer"
_COVER = "durability.cover_footing_mm"
_REACTION_POINT = "foundation.reaction_point"
_REFS = ("dims", "subjects", "basis")
_NEEDS_ENGINEER = "NEEDS_ENGINEER"
_WIDTH_TOO_SMALL = "WIDTH_TOO_SMALL"

BASIS_FIELDS: tuple[str, ...] = (_BAR_DIAMETER, _BOTTOM_LAYER, _COVER, _REACTION_POINT)
"""The basis paths this calc reads (spec 0010 4.4.3); the workflow declares them required."""
ZERO_MM = Cited(value=0, unit="mm", source="Geometry: zero length and zero reaction height at base_of_footing")
ZERO_COUNT = Cited(value=0, unit="1", source="Geometry: zero bar count on an unusable span")
ZERO_AREA = Cited(value=0.0, unit="mm2", source="Geometry: zero bars give zero steel area")
ONE = Cited(value=1, unit="1", source="Geometry: fencepost bar count and spacing count (n bars have n - 1 spaces)")
TWO = Cited(value=2, unit="1", source="Geometry: two opposite covers, half-diameter, and average of two depths")
THREE = Cited(value=3, unit="1", source="Geometry: second-layer centre at cover + 3*db/2")
FOUR = Cited(value=4, unit="1", source="Geometry: circle area pi * db^2 / 4")
PI = Cited(value=math.pi, unit="1", source="Mathematical constant, area of a circle")
MAX_SAFE_INT = Cited(
    value=9007199254740991,
    unit="1",
    source="RFC 8785 3.2.2.3 and eng-contract canonical.py: maximum exact I-JSON integer 2^53 - 1",
)
VERSION = Cited(value=1, unit="1", source="Calc version 1 of spec 0010 4.4.3; a change of method is a new version")


class BottomLayer(StrEnum):
    """Which bottom reinforcement direction lies closest to the footing soffit (spec 0010 4.4.3 L3)."""

    X_BOTTOM = "x_bottom"
    Y_BOTTOM = "y_bottom"


class ReactionPoint(StrEnum):
    """Elevation where the column reaction enters the footing (spec 0010 4.4.3 L5)."""

    TOP_OF_FOOTING = "top_of_footing"
    BASE_OF_FOOTING = "base_of_footing"


class LayoutInput(CalcInput):
    """Input: trial footing dimensions, subjects and the design basis, all by reference."""

    dims: FootingDims = eng_param(ref_capable=True, ref_kinds={"harness.footing_dims/1"}, engineering_quantity=True)
    subjects: FootingSubjects = eng_param(
        ref_capable=True, ref_kinds={"harness.footing_subjects/1"}, engineering_quantity=True
    )
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)


class LayoutBody(BaseModel):
    """The payload of `harness.footing_design/1` without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    footings: list[DesignRow]


def _refuse_basis(code: ErrorCode, path: str, message: str, **fields: Any) -> ContractError:
    return ContractError(code, f"basis field {path} {message}", field="basis", **fields)


def _require_basis_field(basis: DesignBasis, path: str) -> BasisField:
    field = basis.fields.get(path)
    if field is None or not field.confirmed:
        raise _refuse_basis(ErrorCode.INVALID_ARGUMENT, path, "is missing or not confirmed", hint=f"confirm {path}")
    return field


def _read_length_basis(basis: DesignBasis, path: str, *, allow_zero: bool) -> Fraction:
    field = _require_basis_field(basis, path)
    if field.unit != ZERO_MM.unit:
        raise _refuse_basis(
            ErrorCode.UNIT_MISMATCH,
            path,
            f"must be in {ZERO_MM.unit}",
            expected={"unit": ZERO_MM.unit},
            received=field.unit,
        )
    if (exact := as_fraction(field.value)) is None:
        raise _refuse_basis(ErrorCode.INVALID_ARGUMENT, path, "is not a finite number")
    limit = Fraction(ZERO_MM.value)
    if exact < limit if allow_zero else exact <= limit:
        bound_key = "min" if allow_zero else "min_exclusive"
        why = "is below zero" if allow_zero else "must be positive"
        raise _refuse_basis(
            ErrorCode.OUT_OF_RANGE, path, why, expected={bound_key: ZERO_MM.value}, received=field.value
        )
    return exact


def _read_choice_basis[E: StrEnum](basis: DesignBasis, path: str, enum_type: type[E]) -> E:
    field = _require_basis_field(basis, path)
    if field.unit is not None:
        raise _refuse_basis(
            ErrorCode.UNIT_MISMATCH, path, "must have no unit", expected={"unit": None}, received=field.unit
        )
    if not isinstance(field.value, str):
        raise _refuse_basis(
            ErrorCode.INVALID_ARGUMENT,
            path,
            "is not a choice string",
            expected={"choices": [member.value for member in enum_type]},
            received=field.value,
        )
    try:
        return enum_type(field.value)
    except ValueError as exc:
        raise _refuse_basis(
            ErrorCode.INVALID_ARGUMENT,
            path,
            f"has unsupported choice {field.value!r}",
            expected={"choices": [member.value for member in enum_type]},
            received=field.value,
        ) from exc


def _to_finite_float(exact: Fraction, row: DimRow, what: str, *, positive: bool = False) -> float:
    """Convert `exact` once to binary64, refusing overflow or underflow-to-zero as `OUT_OF_RANGE` on `dims`."""
    try:
        value = float(exact)
    except OverflowError as exc:
        raise ContractError(
            ErrorCode.OUT_OF_RANGE,
            f"footing {row.id} {what} is outside binary64 range",
            field="dims",
            expected={"finite_binary64": True},
            received=row.id,
        ) from exc
    if not math.isfinite(value) or (positive and value <= float(ZERO_MM.value)):
        raise ContractError(
            ErrorCode.OUT_OF_RANGE,
            f"footing {row.id} {what} cannot be represented as a valid binary64 number",
            field="dims",
            expected={"finite_binary64": True, "positive": positive},
            received=row.id,
        )
    return value


def _direction_layout(row: DimRow, span: Fraction, s: Fraction, db: Fraction) -> tuple[int, float, float]:
    """L1 and L2 for one bar direction with positive `span`: `(count, actual_spacing_mm, area_mm2)`."""
    spaces = math.ceil(span / s)
    count = spaces + int(ONE.value)
    if count > MAX_SAFE_INT.value:
        raise ContractError(
            ErrorCode.OUT_OF_RANGE,
            f"footing {row.id} bar count exceeds contract integer limit",
            field="dims",
            expected={"max_count": MAX_SAFE_INT.value},
            received=str(count),
        )
    spacing = _to_finite_float(span / spaces, row, "actual bar spacing", positive=True)
    area_exact = Fraction(count) * db * db * Fraction(PI.value) / Fraction(FOUR.value)
    area = _to_finite_float(area_exact, row, "steel area")
    return count, spacing, area


def _layout_row(
    row: DimRow,
    db: Fraction,
    cover: Fraction,
    bottom_layer: BottomLayer,
    reaction_point: ReactionPoint,
) -> tuple[DesignRow, bool]:
    """Rules L1 to L5 for one footing; returns `(DesignRow, width_too_small)`."""
    h = Fraction(row.h_mm)
    two = Fraction(TWO.value)
    d_lower = h - cover - db / two
    d_upper = h - cover - Fraction(THREE.value) * db / two
    if d_upper <= Fraction(ZERO_MM.value):
        try:
            min_depth_val: float | str = float(cover + Fraction(THREE.value) * db / two)
        except OverflowError:
            min_depth_val = "outside_binary64"
        if isinstance(min_depth_val, float) and not math.isfinite(min_depth_val):
            min_depth_val = "outside_binary64"
        raise ContractError(
            ErrorCode.OUT_OF_RANGE,
            f"footing {row.id} depth {row.h_mm} mm leaves no room for both bottom layers",
            field="dims",
            expected={"min_depth_exclusive_mm": min_depth_val},
            received=row.h_mm,
        )
    d_x, d_y = (d_lower, d_upper) if bottom_layer is BottomLayer.X_BOTTOM else (d_upper, d_lower)
    d = (d_x + d_y) / two
    d_x_float = _to_finite_float(d_x, row, "effective depth d_x", positive=True)
    d_y_float = _to_finite_float(d_y, row, "effective depth d_y", positive=True)
    d_float = _to_finite_float(d, row, "effective depth d", positive=True)
    db_float = _to_finite_float(db, row, "bar diameter", positive=True)
    cover_float = _to_finite_float(cover, row, "cover")
    two_c_plus_db = two * cover + db
    span_x = Fraction(row.Ly_mm) - two_c_plus_db
    span_y = Fraction(row.Lx_mm) - two_c_plus_db
    zero_mm = Fraction(ZERO_MM.value)
    reason: str | None
    if span_x <= zero_mm or span_y <= zero_mm:
        too_small = True
        n_x = n_y = int(ZERO_COUNT.value)
        s_x = s_y = row.s_mm
        as_x = as_y = float(ZERO_AREA.value)
        status, reason = _NEEDS_ENGINEER, _WIDTH_TOO_SMALL
    else:
        too_small = False
        s_frac = Fraction(row.s_mm)
        n_x, s_x, as_x = _direction_layout(row, span_x, s_frac, db)
        n_y, s_y, as_y = _direction_layout(row, span_y, s_frac, db)
        status, reason = row.status, row.reason
    reaction_height = row.h_mm if reaction_point is ReactionPoint.TOP_OF_FOOTING else float(ZERO_MM.value)
    return (
        DesignRow(
            id=row.id,
            Lx_mm=row.Lx_mm,
            Ly_mm=row.Ly_mm,
            h_mm=row.h_mm,
            s_mm=row.s_mm,
            source=row.source,
            plan_at_max=row.plan_at_max,
            depth_at_max=row.depth_at_max,
            spacing_at_min=row.spacing_at_min,
            status=status,
            reason=reason,
            db_mm=db_float,
            n_x=n_x,
            n_y=n_y,
            s_x_mm=s_x,
            s_y_mm=s_y,
            As_x_mm2=as_x,
            As_y_mm2=as_y,
            d_x_mm=d_x_float,
            d_y_mm=d_y_float,
            d_mm=d_float,
            cover_mm=cover_float,
            end_cover_mm=cover_float,
            reaction_height_mm=reaction_height,
        ),
        too_small,
    )


@calc(
    id="harness.footing_layout",
    version=int(VERSION.value),
    output_kind="harness.footing_design/1",
    title="Footing bar layout, effective depths, cover and reaction height",
    method_source="eng-harness spec 0010 §4.4.3 (L1 to L5)",
    verification="draft",
)
def footing_layout(inp: LayoutInput, meta: InputMeta, trace: TraceBuilder) -> LayoutBody:
    """Compute bar counts, actual spacing, steel areas, effective depths, cover and reaction height per footing.

    Raises:
        ContractError: see the module docstring.
    """
    refs: dict[str, str] = {}
    for name in _REFS:
        if (ref := meta.refs.get(name)) is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"input {name} must be a record reference", field=name)
        refs[name] = ref.result_id
    db = _read_length_basis(inp.basis, _BAR_DIAMETER, allow_zero=False)
    bottom_layer = _read_choice_basis(inp.basis, _BOTTOM_LAYER, BottomLayer)
    cover = _read_length_basis(inp.basis, _COVER, allow_zero=True)
    reaction_point = _read_choice_basis(inp.basis, _REACTION_POINT, ReactionPoint)

    known_subjects = {subject.id for subject in inp.subjects.subjects}
    for row in inp.dims.footings:
        if row.id not in known_subjects:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"footing {row.id} is not in subjects",
                field="dims",
                received=row.id[:200],
            )

    trace.input("dims", len(inp.dims.footings), ref=refs["dims"])
    trace.input("subjects", len(inp.subjects.subjects), ref=refs["subjects"])
    trace.input("bar_diameter_mm", float(db), unit="mm", ref=f"{refs['basis']}#/fields/{_BAR_DIAMETER}")
    trace.input("bottom_layer", bottom_layer.value, unit=None, ref=f"{refs['basis']}#/fields/{_BOTTOM_LAYER}")
    trace.input("cover_footing_mm", float(cover), unit="mm", ref=f"{refs['basis']}#/fields/{_COVER}")
    trace.input("reaction_point", reaction_point.value, unit=None, ref=f"{refs['basis']}#/fields/{_REACTION_POINT}")

    const_pairs = (
        ("zero_mm", ZERO_MM),
        ("zero_count", ZERO_COUNT),
        ("zero_area", ZERO_AREA),
        ("one", ONE),
        ("two", TWO),
        ("three", THREE),
        ("four", FOUR),
        ("pi", PI),
        ("max_safe_int", MAX_SAFE_INT),
    )
    for const_name, cited in const_pairs:
        trace.constant(const_name, cited)

    outcomes = [_layout_row(row, db, cover, bottom_layer, reaction_point) for row in inp.dims.footings]
    designs = [design for design, _ in outcomes]
    too_small_count = sum(bad for _, bad in outcomes)

    trace.step(
        "footings",
        len(designs),
        formula="bar counts, steel areas, effective depths, cover and reaction height per footing",
        source="spec 0010 4.4.3 L1 to L5",
        uses=[
            "dims",
            "subjects",
            "bar_diameter_mm",
            "bottom_layer",
            "cover_footing_mm",
            "reaction_point",
            *(name for name, _ in const_pairs),
        ],
    )
    trace.step(
        "width_too_small",
        too_small_count,
        formula="footings with span_x <= 0 or span_y <= 0 (NEEDS_ENGINEER WIDTH_TOO_SMALL)",
        source="spec 0010 4.4.3 L1",
        uses=["dims", "bar_diameter_mm", "cover_footing_mm", "zero_mm", "two"],
    )
    trace.output("footings")
    return LayoutBody(footings=designs)
