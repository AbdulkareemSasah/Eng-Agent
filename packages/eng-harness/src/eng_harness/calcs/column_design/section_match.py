"""Calc `harness.column_section_match` v1: match rounded sizes to a model section (spec 0013 4.4.4, M1, M2).

Purpose: given one selected column row, the rounded sizes from `harness.section_round` (`harness.section_size/1` body
per dimension: `b` and `h`, or `D`), the model sections and `compare.length_mm`, find frame sections of the column's
shape and material whose every dimension differs from the rounded size by at most the tolerance (exact `Fraction`).
One candidate is `matched`; none is `no_section_in_model` (CW-G3, H-G1); several are `ambiguous` with all names sorted.
Units: lengths in mm. Errors: `ContractError` `INVALID_ARGUMENT` for a basis field that is missing, unconfirmed, not a
number or negative, for sizes that do not name `b` and `h` or `D`, for sizes that disagree with the column shape, and
for a non-reference `column`, `sections` or `basis`.
"""

from fractions import Fraction
from typing import Annotated, Literal, Self

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import Circular, Rectangular, Sections
from eng_contract.params import eng_param
from eng_contract.quantity import Quantity
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict, Field, model_validator

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs.column_design.column_select import read_tolerance
from eng_harness.kinds.edit_cycle import Label

__all__ = ["BASIS_FIELDS", "ColumnRow", "MatchBody", "MatchInput", "MatchSizes", "SizeBody", "column_section_match"]

_LENGTH = "compare.length_mm"
BASIS_FIELDS = (_LENGTH,)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""
_Shape = Literal["rectangular", "circular", "other"]
_Status = Literal["matched", "no_section_in_model", "ambiguous"]


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ColumnRow(_M):
    """One row of `harness.column_selection/1` (spec 0013 4.4.1 L3), resolved by a pointer into the selection."""

    frame_id: Label
    section: Label
    shape: _Shape
    material: Label
    story: Label
    length_mm: float


class SizeBody(_M):
    """The body of `harness.section_size/1` without `calc`, `draft` and `trace` (spec 0003 4.10)."""

    required: Quantity
    increment: Quantity
    multiple: Annotated[int, Field(ge=1)]
    size: Quantity
    status: Literal[VerdictStatus.PASS]

    @model_validator(mode="after")
    def _mm_and_round(self) -> Self:
        if {self.required.unit, self.increment.unit, self.size.unit} != {"mm"}:
            raise ValueError("required, increment and size must be in mm")
        required, increment = Fraction(self.required.value), Fraction(self.increment.value)
        exact = self.multiple * increment
        if self.size.value != float(exact):
            raise ValueError("size must be multiple times increment, converted to float once (N2)")
        if exact < required:
            raise ValueError("size must be at least required (N2)")
        if exact - required >= increment:
            raise ValueError("size must be less than required plus increment (N2)")
        return self


class MatchSizes(_M):
    """One `harness.section_size/1` body per dimension: `b` and `h`, or `D` (spec 0013 4.4.4)."""

    b: SizeBody | None = None
    h: SizeBody | None = None
    D: SizeBody | None = None

    @model_validator(mode="after")
    def _b_h_or_d(self) -> Self:
        rectangular = self.b is not None and self.h is not None and self.D is None
        circular = self.D is not None and self.b is None and self.h is None
        if not (rectangular or circular):
            raise ValueError("sizes must give b and h, or D")
        return self


class MatchInput(CalcInput):
    """The column row, rounded sizes, model sections and the design basis."""

    column: ColumnRow = eng_param(
        ref_capable=True, ref_kinds={"harness.column_selection/1"}, engineering_quantity=True
    )
    sizes: MatchSizes
    sections: Sections = eng_param(ref_capable=True, ref_kinds={"model.sections/1"}, engineering_quantity=True)
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)


class MatchBody(_M):
    """The payload of `harness.column_match/1` without `calc`, `draft` and `trace`."""

    status: _Status
    section: str | None = None
    names: list[str]


def _require_refs(meta: InputMeta) -> dict[str, str]:
    refs: dict[str, str] = {}
    for name in ("column", "sections", "basis"):
        ref = meta.refs.get(name)
        if ref is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{name} must be a record reference", field=name)
        refs[name] = ref.result_id
    return refs


def _within(actual: float, target: Fraction, tolerance: Fraction) -> bool:
    """M1: |actual - target| <= tolerance as exact Fractions of the stored values."""
    return abs(Fraction(actual) - target) <= tolerance


def _candidates(inp: MatchInput, tolerance: Fraction) -> list[str]:
    """M1: names of frame sections of the column's shape and material within the tolerance on every dimension."""
    column, sizes = inp.column, inp.sizes
    if column.shape == "rectangular":
        if sizes.b is None or sizes.h is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                "rectangular column needs sizes b and h",
                field="sizes",
            )
        b_mm, h_mm = Fraction(sizes.b.size.value), Fraction(sizes.h.size.value)
        names: list[str] = []
        for row in inp.sections.frame_sections:
            if row.material != column.material or not isinstance(row.shape, Rectangular):
                continue
            if _within(row.shape.b_mm, b_mm, tolerance) and _within(row.shape.h_mm, h_mm, tolerance):
                names.append(row.name)
        return sorted(names)
    if column.shape == "circular":
        if sizes.D is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                "circular column needs size D",
                field="sizes",
            )
        d_mm = Fraction(sizes.D.size.value)
        names = []
        for row in inp.sections.frame_sections:
            if row.material != column.material or not isinstance(row.shape, Circular):
                continue
            if _within(row.shape.D_mm, d_mm, tolerance):
                names.append(row.name)
        return sorted(names)
    return []  # shape other: no model section type to match (M1)


@calc(
    id="harness.column_section_match",
    version=1,
    output_kind="harness.column_match/1",
    title="Match rounded column sizes to an existing model section",
    method_source="eng-harness spec 0013 §4.4.4 (M1, M2); eng-harness spec 0003 §4.11 P2",
    verification="draft",
)
def column_section_match(inp: MatchInput, meta: InputMeta, trace: TraceBuilder) -> MatchBody:
    """Find candidates (M1) and set matched, no_section_in_model or ambiguous (M2).

    Raises:
        ContractError: see the module docstring.
    """
    refs = _require_refs(meta)
    tolerance = read_tolerance(inp.basis)
    trace.input("column", inp.column.frame_id, ref=refs["column"])
    trace.input("frame_sections", len(inp.sections.frame_sections), ref=refs["sections"])
    trace.input("compare_length_mm", float(tolerance), unit="mm", ref=f"{refs['basis']}#/fields/{_LENGTH}")
    if inp.sizes.D is not None:
        trace.input("size_D_mm", inp.sizes.D.size.value, unit="mm")
    else:
        assert inp.sizes.b is not None and inp.sizes.h is not None
        trace.input("size_b_mm", inp.sizes.b.size.value, unit="mm")
        trace.input("size_h_mm", inp.sizes.h.size.value, unit="mm")
    names = _candidates(inp, tolerance)
    if len(names) == 1:
        status: _Status = "matched"
        section: str | None = names[0]
    elif not names:
        status, section = "no_section_in_model", None
    else:
        status, section = "ambiguous", None
    rule = "spec 0013 4.4.4"
    trace.step("candidates", len(names), formula="same shape and material within compare.length_mm", source=f"{rule} M1")
    trace.step("status", status, formula="one matched, none no_section_in_model, several ambiguous", source=f"{rule} M2")
    trace.step(
        "section",
        section or "",
        formula="the sole candidate name, or empty",
        source=f"{rule} M2",
        uses=["candidates"],
    )
    trace.step(
        "names",
        len(names),
        formula="candidate names sorted (count)",
        source=f"{rule} M2",
        uses=["candidates"],
    )
    trace.output("status", "section", "names")
    return MatchBody(status=status, section=section, names=names)
