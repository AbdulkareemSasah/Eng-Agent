"""Calc `harness.column_section_match` v1: match rounded sizes to a model section (spec 0013 4.4.4, M1, M2).

Purpose: given one selected column row, the rounded sizes as `harness.section_size/1` references (`size_b` and
`size_h`, or `size_d`, pointing to `#/size` of `harness.section_round` results), the model sections and
`compare.length_mm`, find frame sections of the column's shape and material whose every dimension differs from the
rounded size by at most the tolerance (exact `Fraction`). One candidate is `matched`; none is `no_section_in_model`
(CW-G3, H-G1); several are `ambiguous` with all names sorted.
Units: lengths in mm. Errors: `ContractError` `INVALID_ARGUMENT` for a basis field that is missing, unconfirmed, not a
number or negative, for missing or conflicting size parameters (`size_b`+`size_h` vs `size_d`), for size dimensions
that disagree with the column shape, for a size reference whose JSON pointer is not exactly `/size`
(amendment B-580), and for a non-reference `column`, `size_b`, `size_h`, `size_d`, `sections` or `basis`.
"""

from fractions import Fraction
from typing import Any, Literal, Self

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.refs import parse_ref
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import Circular, Rectangular, Sections
from eng_contract.params import eng_param
from eng_contract.quantity import Quantity
from pydantic import BaseModel, ConfigDict, model_validator

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs.column_design.column_select import read_tolerance
from eng_harness.kinds.edit_cycle import Label

__all__ = ["BASIS_FIELDS", "ColumnRow", "MatchBody", "MatchInput", "column_section_match"]

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


def _size_param() -> Any:
    return eng_param(None, unit="mm", ref_capable=True, ref_kinds={"harness.section_size/1"}, engineering_quantity=True)


class MatchInput(CalcInput):
    """The column row, rounded size references (`harness.section_size/1`), model sections and the design basis."""

    column: ColumnRow = eng_param(ref_capable=True, ref_kinds={"harness.column_selection/1"}, engineering_quantity=True)
    size_b: Quantity | None = _size_param()
    size_h: Quantity | None = _size_param()
    size_d: Quantity | None = _size_param()
    sections: Sections = eng_param(ref_capable=True, ref_kinds={"model.sections/1"}, engineering_quantity=True)
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)

    @model_validator(mode="after")
    def _b_h_or_d(self) -> Self:
        rectangular = self.size_b is not None and self.size_h is not None and self.size_d is None
        circular = self.size_d is not None and self.size_b is None and self.size_h is None
        if not (rectangular or circular):
            raise ValueError("give size_b and size_h, or size_d")
        return self


class MatchBody(_M):
    """The payload of `harness.column_match/1` without `calc`, `draft` and `trace`."""

    status: _Status
    section: str | None = None
    names: list[str]


_SIZE_POINTER = ("size",)
"""The only accepted JSON pointer for size_b, size_h and size_d (spec 0013 §4.4.4; amendment B-580)."""


def _require_refs(meta: InputMeta, *names: str) -> dict[str, str]:
    refs: dict[str, str] = {}
    for name in names:
        entry = meta.refs.get(name)
        if entry is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{name} must be a record reference", field=name)
        refs[name] = entry.result_id
    return refs


def _require_size_ref(meta: InputMeta, name: str) -> str:
    """Return the validated original size reference; its pointer must be exactly `/size`."""
    entry = meta.refs.get(name)
    if entry is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{name} must be a record reference", field=name)
    _result_id, tokens = parse_ref(entry.ref, field=name)
    if tokens != _SIZE_POINTER:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            f"{name} pointer must be /size",
            field=name,
        )
    return entry.ref


def _within(actual: float, target: Fraction, tolerance: Fraction) -> bool:
    """M1: |actual - target| <= tolerance as exact Fractions of the stored values."""
    return abs(Fraction(actual) - target) <= tolerance


def _candidates(inp: MatchInput, tolerance: Fraction) -> list[str]:
    """M1: names of frame sections of the column's shape and material within the tolerance on every dimension."""
    column = inp.column
    if column.shape == "rectangular":
        if inp.size_b is None or inp.size_h is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                "rectangular column needs size_b and size_h",
                field="size_b",
            )
        b_mm, h_mm = Fraction(inp.size_b.value), Fraction(inp.size_h.value)
        names: list[str] = []
        for row in inp.sections.frame_sections:
            if row.material != column.material or not isinstance(row.shape, Rectangular):
                continue
            if _within(row.shape.b_mm, b_mm, tolerance) and _within(row.shape.h_mm, h_mm, tolerance):
                names.append(row.name)
        return sorted(names)
    if column.shape == "circular":
        if inp.size_d is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                "circular column needs size_d",
                field="size_d",
            )
        d_mm = Fraction(inp.size_d.value)
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
    size_names = ("size_d",) if inp.size_d is not None else ("size_b", "size_h")
    refs = _require_refs(meta, "column", "sections", "basis")
    size_refs = {name: _require_size_ref(meta, name) for name in size_names}
    tolerance = read_tolerance(inp.basis)
    trace.input("column", inp.column.frame_id, ref=refs["column"])
    trace.input("frame_sections", len(inp.sections.frame_sections), ref=refs["sections"])
    trace.input("compare_length_mm", float(tolerance), unit="mm", ref=f"{refs['basis']}#/fields/{_LENGTH}")
    if inp.size_d is not None:
        trace.input("size_D_mm", inp.size_d.value, unit="mm", ref=size_refs["size_d"])
    else:
        size_b, size_h = inp.size_b, inp.size_h
        if size_b is None or size_h is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                "give size_b and size_h, or size_d",
                field="size_b",
            )
        trace.input("size_b_mm", size_b.value, unit="mm", ref=size_refs["size_b"])
        trace.input("size_h_mm", size_h.value, unit="mm", ref=size_refs["size_h"])
    names = _candidates(inp, tolerance)
    if len(names) == 1:
        status: _Status = "matched"
        section: str | None = names[0]
    elif not names:
        status, section = "no_section_in_model", None
    else:
        status, section = "ambiguous", None
    rule = "spec 0013 4.4.4"
    trace.step(
        "candidates", len(names), formula="same shape and material within compare.length_mm", source=f"{rule} M1"
    )
    trace.step(
        "status", status, formula="one matched, none no_section_in_model, several ambiguous", source=f"{rule} M2"
    )
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
