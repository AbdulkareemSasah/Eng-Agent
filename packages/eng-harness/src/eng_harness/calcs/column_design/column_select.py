"""Calc `harness.column_select` v1: which frames of the engineer's scope are columns (spec 0013 4.4.1, L1 to L3).

Purpose: resolve the scope answer (frame names, or a story and section selection) against the model read; a frame is
a column when the plan distance between its ends is within `compare.length_mm` (exact, spec 0003 4.11 P2), otherwise
it is excluded `NOT_VERTICAL`; each column carries its section shape, material, story and length. The contract frame
`kind` is not used (the CSI reader gives `other`, spec 0013 C3). Unknown names are error issues.
Units: lengths in mm. The tolerance test is exact (`Fraction` of the stored values); `length_mm` is for display.
Errors: `ContractError` `INVALID_ARGUMENT` for a basis field that is missing, unconfirmed, not a number or negative
(`field` names it), for a column whose section is not in the sections or that has no story, and for an unrepresentable
column length (`field="frames"`).
"""

import math
from fractions import Fraction
from typing import Annotated, Literal, Self

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import Circular, Frame, FramePlacements, FrameSection, Rectangular, Sections
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.edit_cycle import NONEMPTY, Label

__all__ = ["BASIS_FIELDS", "ColumnScope", "SelectBody", "SelectInput", "column_select"]

_LENGTH = "compare.length_mm"
BASIS_FIELDS = (_LENGTH,)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""
_RADIX = Cited(value=2, unit="1", source="IEEE 754 binary64 radix for even-power-of-two scaling before sqrt")
_Names = Annotated[list[Label], Field(min_length=NONEMPTY)]
_Issue = Literal["UNKNOWN_FRAME", "UNKNOWN_STORY", "UNKNOWN_SECTION"]


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class _Select(_M):
    stories: _Names | None = None
    sections: _Names | None = None

    @model_validator(mode="after")
    def _some(self) -> Self:
        if self.stories is None and self.sections is None:
            raise ValueError("a selection names stories or sections")
        return self


class ColumnScope(_M):
    """The scope answer, the stored `ColumnScopeRequest` of spec 0013 4.3 (L1 reads `frames` or `select`)."""

    frames: _Names | None = None
    select: _Select | None = None
    combinations: _Names
    special_seismic: StrictBool

    @model_validator(mode="after")
    def _one(self) -> Self:
        if (self.frames is None) == (self.select is None):
            raise ValueError("give frames or select, not both and not neither")
        return self


class SelectInput(CalcInput):
    """The scope answer, the frame placements, the sections and the design basis, all by reference."""

    scope: ColumnScope = eng_param(ref_capable=True, ref_kinds={"basis.engineer_input/1"}, engineering_quantity=True)
    frames: FramePlacements = eng_param(
        ref_capable=True, ref_kinds={"model.frame_placements/1"}, engineering_quantity=True
    )
    sections: Sections = eng_param(ref_capable=True, ref_kinds={"model.sections/1"}, engineering_quantity=True)
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)


class _Column(_M):
    frame_id: str
    section: str
    shape: Literal["rectangular", "circular", "other"]
    material: str
    story: str
    length_mm: float


class _Excluded(_M):
    frame_id: str
    reason: Literal["NOT_VERTICAL"]


class _SelIssue(_M):
    code: _Issue
    name: str


class SelectBody(_M):
    """The payload of `harness.column_selection/1` without `calc`, `draft` and `trace`."""

    status: Literal["PASS", "FAIL"]
    columns: list[_Column]
    excluded: list[_Excluded]
    issues: list[_SelIssue]


def _refuse(why: str) -> ContractError:
    return ContractError(
        ErrorCode.INVALID_ARGUMENT,
        f"basis field {_LENGTH} {why}",
        field=f"basis.fields.{_LENGTH}",
        hint=f"set and confirm {_LENGTH} in the design basis",
    )


def read_tolerance(basis: DesignBasis) -> Fraction:
    """Spec 0003 4.4: `compare.length_mm` present, confirmed and a number >= 0 (its unit is fixed by the suffix)."""
    field = basis.fields.get(_LENGTH)
    if field is None:
        raise _refuse("is missing (no default)")
    if not field.confirmed:
        raise _refuse("is not confirmed")
    value = as_fraction(field.value)
    if value is None or abs(value) != value:
        raise _refuse("must be a number >= 0")
    return value


def plan_distance_sq(frame: Frame) -> Fraction:
    """L2 and 0003 P2: the exact squared plan distance between the frame's ends."""
    dx = Fraction(frame.j.x_mm) - Fraction(frame.i.x_mm)
    dy = Fraction(frame.j.y_mm) - Fraction(frame.i.y_mm)
    return dx * dx + dy * dy


def length_mm(frame: Frame) -> float:
    """L3: distance between ends from exact squared distance, scaled by 2^(2k) for display float (0003 P2)."""
    dz = Fraction(frame.j.z_mm) - Fraction(frame.i.z_mm)
    d_sq = plan_distance_sq(frame) + dz * dz
    radix = int(_RADIX.value)
    half_shift = (d_sq.numerator.bit_length() - d_sq.denominator.bit_length()) // radix
    scaled = d_sq * (Fraction(radix) ** (-(radix * half_shift)))
    try:
        return math.ldexp(math.sqrt(float(scaled)), half_shift)
    except OverflowError as exc:
        message = f"length of column {frame.id} exceeds representable float range"
        raise ContractError(ErrorCode.INVALID_ARGUMENT, message, field="frames") from exc


def _shape(section: FrameSection) -> Literal["rectangular", "circular", "other"]:
    if isinstance(section.shape, Rectangular):
        return "rectangular"
    return "circular" if isinstance(section.shape, Circular) else "other"


def resolve(scope: ColumnScope, frames: list[Frame], section_names: set[str]) -> tuple[list[Frame], list[_SelIssue]]:
    """L1: the frames in scope, in model order, and the unknown names as issues sorted by code and name."""
    select = scope.select
    if select is None:  # ColumnScope holds frames or select
        wanted = set(scope.frames or ())
        unknown = sorted(wanted - {frame.id for frame in frames})
        return [f for f in frames if f.id in wanted], [_SelIssue(code="UNKNOWN_FRAME", name=n) for n in unknown]
    stories = None if select.stories is None else set(select.stories)
    sections = None if select.sections is None else set(select.sections)
    known_stories = {frame.story for frame in frames}
    found: list[tuple[_Issue, str]] = [("UNKNOWN_STORY", name) for name in (stories or set()) - known_stories]
    found += [("UNKNOWN_SECTION", name) for name in (sections or set()) - section_names]
    chosen = [
        frame
        for frame in frames
        if (stories is None or frame.story in stories) and (sections is None or frame.section in sections)
    ]
    return chosen, [_SelIssue(code=c, name=n) for c, n in sorted(found)]


def _scope_names(scope: ColumnScope) -> int:
    """How many names the scope gives: frames, or selected stories and sections (a trace input)."""
    if scope.select is None:
        return len(scope.frames or ())
    return len(scope.select.stories or ()) + len(scope.select.sections or ())


def _column(frame: Frame, sections: dict[str, FrameSection]) -> _Column:
    """L3 for one column; refuses a section that is not in the sections and a frame without a story."""
    section = sections.get(frame.section)
    if section is None:
        message = f"section {frame.section} of column {frame.id} is not in the sections"
        raise ContractError(ErrorCode.INVALID_ARGUMENT, message, field="sections", received=frame.section)
    if frame.story is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, f"column {frame.id} has no story", field="frames")
    return _Column(
        frame_id=frame.id,
        section=frame.section,
        shape=_shape(section),
        material=section.material,
        story=frame.story,
        length_mm=length_mm(frame),
    )


@calc(
    id="harness.column_select",
    version=1,
    output_kind="harness.column_selection/1",
    title="Column selection: scope names, verticality, shape and material",
    method_source="eng-harness spec 0013 §4.4.1 (L1 to L3); eng-harness spec 0003 §4.11 P2",
    verification="draft",
)
def column_select(inp: SelectInput, meta: InputMeta, trace: TraceBuilder) -> SelectBody:
    """Resolve the scope (L1), keep the vertical frames (L2) and describe each column (L3).

    Raises:
        ContractError: see the module docstring.
    """
    tolerance = read_tolerance(inp.basis)
    ref = {name: meta.refs[name].result_id for name in ("scope", "frames", "sections", "basis")}
    frames, rows = inp.frames.frames, inp.sections.frame_sections
    trace.input("scope", _scope_names(inp.scope), ref=ref["scope"])
    trace.input("frames", len(frames), ref=ref["frames"])
    trace.input("frame_sections", len(rows), ref=ref["sections"])
    trace.input("compare_length_mm", float(tolerance), unit="mm", ref=f"{ref['basis']}#/fields/{_LENGTH}")
    sections = {row.name: row for row in rows}
    chosen, issues = resolve(inp.scope, frames, set(sections))
    limit = tolerance * tolerance
    vertical = {frame.id for frame in chosen if plan_distance_sq(frame) <= limit}
    columns = sorted((_column(f, sections) for f in chosen if f.id in vertical), key=lambda row: row.frame_id)
    excluded = sorted(
        (_Excluded(frame_id=f.id, reason="NOT_VERTICAL") for f in chosen if f.id not in vertical),
        key=lambda row: row.frame_id,
    )
    status: Literal["PASS", "FAIL"] = "FAIL" if issues or not columns else "PASS"
    rule = "spec 0013 4.4.1"
    for name, value, formula, part, uses in (
        ("in_scope", len(chosen), "frames named, or of a selected story and section", "L1", ["scope", "frames"]),
        ("issues", len(issues), "names in the scope that the model lacks", "L1", ["scope", "frames", "frame_sections"]),
        (
            "columns",
            len(columns),
            "in_scope with plan distance^2 <= compare_length_mm^2",
            "L2",
            ["in_scope", "compare_length_mm"],
        ),
        ("excluded", len(excluded), "in_scope - columns (NOT_VERTICAL)", "L2", ["in_scope", "columns"]),
        ("status", status, "FAIL when issues > 0 or columns = 0, else PASS", "L1 to L3", ["issues", "columns"]),
    ):
        trace.step(name, value, formula=formula, source=f"{rule} {part}", uses=uses)
    trace.output("status", "columns", "excluded", "issues")
    return SelectBody(status=status, columns=columns, excluded=excluded, issues=issues)
