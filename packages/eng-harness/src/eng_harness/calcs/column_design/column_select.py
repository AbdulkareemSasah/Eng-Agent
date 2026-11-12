"""Calc `harness.column_select` v1 (spec 0013 section 4.4.1, rules L1 to L3).

Purpose: resolve the engineer's column scope against the model read, test verticality with `compare.length` and attach
section shape and material. Errors: `ContractError` `INVALID_ARGUMENT` for a missing or unconfirmed basis field.
"""

from __future__ import annotations

import math
from fractions import Fraction
from operator import lt
from typing import Literal, Self

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import Circular, Frame, FramePlacements, FrameSection, OtherShape, Rectangular, Sections
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict, model_validator

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc

_COMPARE_LENGTH = "compare.length"
_TRACE_TOL = "compare_length"
_COLUMN_SHAPE = Literal["rectangular", "circular", "other"]
_PASS_FAIL = Literal["PASS", "FAIL"]
_ISSUE = Literal["UNKNOWN_FRAME", "UNKNOWN_STORY", "UNKNOWN_SECTION"]


class _Select(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    stories: list[str] | None = None
    sections: list[str] | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> Self:
        if self.stories is None and self.sections is None:
            raise ValueError("select needs stories or sections")
        return self


class ColumnSelectScope(BaseModel):
    """Engineer scope answer (spec 0013 section 4.3 `ColumnScopeRequest` fields used by L1)."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    frames: list[str] | None = None
    select: _Select | None = None
    combinations: list[str]

    @model_validator(mode="after")
    def _mode(self) -> Self:
        if (self.frames is None) == (self.select is None):
            raise ValueError("give frames or select, not both and not neither")
        if not self.combinations:
            raise ValueError("combinations must name at least one load combination")
        return self


class ColumnSelectInput(CalcInput):
    """Inputs of `harness.column_select` (spec 0013 section 4.4.1)."""

    scope: ColumnSelectScope = eng_param(ref_capable=True, ref_kinds={"basis.engineer_input/1"})
    frames: FramePlacements = eng_param(ref_capable=True, ref_kinds={"model.frame_placements/1"})
    sections: Sections = eng_param(ref_capable=True, ref_kinds={"model.sections/1"})
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"})


class _Column(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    frame_id: str
    section: str
    shape: _COLUMN_SHAPE
    material: str
    story: str
    length_mm: float


class _Excluded(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    frame_id: str
    reason: Literal["NOT_VERTICAL"]


class _Issue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    code: _ISSUE
    name: str


class ColumnSelectBody(BaseModel):
    """`harness.column_selection/1` without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    status: _PASS_FAIL
    columns: list[_Column]
    excluded: list[_Excluded]
    issues: list[_Issue]


def _coord(frame: Frame, end: Literal["i", "j"], axis: Literal["x_mm", "y_mm", "z_mm"]) -> Fraction:
    point = frame.i if end == "i" else frame.j
    return Fraction(str(getattr(point, axis)))


def _plan_dist_sq(frame: Frame) -> Fraction:
    dx = _coord(frame, "i", "x_mm") - _coord(frame, "j", "x_mm")
    dy = _coord(frame, "i", "y_mm") - _coord(frame, "j", "y_mm")
    return dx * dx + dy * dy


def _length_mm(frame: Frame) -> float:
    dx = _coord(frame, "i", "x_mm") - _coord(frame, "j", "x_mm")
    dy = _coord(frame, "i", "y_mm") - _coord(frame, "j", "y_mm")
    dz = _coord(frame, "i", "z_mm") - _coord(frame, "j", "z_mm")
    span = dx * dx + dy * dy + dz * dz
    return math.sqrt(float(span))


def _shape_name(section: FrameSection) -> _COLUMN_SHAPE:
    shape = section.shape
    if isinstance(shape, Rectangular):
        return "rectangular"
    if isinstance(shape, Circular):
        return "circular"
    if isinstance(shape, OtherShape):
        return "other"
    raise TypeError("unknown section shape")


def _read_tolerance(inp: ColumnSelectInput, meta: InputMeta, trace: TraceBuilder) -> Fraction:
    field = inp.basis.fields.get(_COMPARE_LENGTH)
    if field is None or not field.confirmed:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "compare.length is missing or not confirmed", field="basis")
    if field.unit != "mm":
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "compare.length must be in mm", field="basis")
    tolerance = Fraction(str(field.value))
    if lt(tolerance, Fraction()):
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "compare.length must be non-negative", field="basis")
    basis_ref = meta.refs.get("basis")
    trace.input(
        _TRACE_TOL,
        float(tolerance),
        unit="mm",
        ref=f"{basis_ref.result_id}#/fields/{_COMPARE_LENGTH}" if basis_ref else None,
    )
    return tolerance


def _frames_by_id(frames: FramePlacements) -> dict[str, Frame]:
    return {frame.id: frame for frame in frames.frames}


def _sections_by_name(sections: Sections) -> dict[str, FrameSection]:
    return {row.name: row for row in sections.frame_sections}


def _stories_present(frames: FramePlacements) -> set[str]:
    return {frame.story for frame in frames.frames if frame.story is not None}


def _l1_issues(scope: ColumnSelectScope, frames: FramePlacements, sections: Sections) -> list[_Issue]:
    by_id = _frames_by_id(frames)
    section_names = set(_sections_by_name(sections))
    story_names = _stories_present(frames)
    issues: list[_Issue] = []
    if scope.frames is not None:
        for name in scope.frames:
            if name not in by_id:
                issues.append(_Issue(code="UNKNOWN_FRAME", name=name))
        return sorted(issues, key=lambda row: (row.code, row.name))
    select = scope.select
    if select is None:
        return issues
    if select.stories is not None:
        for name in select.stories:
            if name not in story_names:
                issues.append(_Issue(code="UNKNOWN_STORY", name=name))
    if select.sections is not None:
        for name in select.sections:
            if name not in section_names:
                issues.append(_Issue(code="UNKNOWN_SECTION", name=name))
    return sorted(issues, key=lambda row: (row.code, row.name))


def _resolve(scope: ColumnSelectScope, frames: FramePlacements) -> list[Frame]:
    by_id = _frames_by_id(frames)
    if scope.frames is not None:
        return [by_id[name] for name in scope.frames if name in by_id]
    select = scope.select
    if select is None:
        return []
    rows = frames.frames
    if select.stories is not None:
        wanted = set(select.stories)
        rows = [frame for frame in rows if frame.story in wanted]
    if select.sections is not None:
        wanted = set(select.sections)
        rows = [frame for frame in rows if frame.section in wanted]
    return rows


def _column_row(frame: Frame, section: FrameSection) -> _Column:
    story = frame.story or ""
    return _Column(
        frame_id=frame.id,
        section=frame.section,
        shape=_shape_name(section),
        material=section.material,
        story=story,
        length_mm=_length_mm(frame),
    )


@calc(
    id="harness.column_select",
    version=1,
    output_kind="harness.column_selection/1",
    title="Column scope resolution and verticality",
    method_source="eng-harness spec 0013 §4.4.1 (L1 to L3); eng-harness spec 0003 §4.11 P2",
    verification="draft",
)
def column_select(inp: ColumnSelectInput, meta: InputMeta, trace: TraceBuilder) -> ColumnSelectBody:
    """Resolve scope names (L1), keep vertical frames (L2) and attach section data (L3)."""
    tolerance = _read_tolerance(inp, meta, trace)
    tolerance_sq = tolerance * tolerance
    sections = _sections_by_name(inp.sections)
    issues = _l1_issues(inp.scope, inp.frames, inp.sections)
    trace.step(
        "scope_issues",
        len(issues),
        formula="unknown frame, story and section names in the scope answer",
        source="§4.4.1 L1",
        uses=[_TRACE_TOL],
    )
    selected = _resolve(inp.scope, inp.frames)
    trace.step(
        "selected_frames", len(selected), formula="frames named or filtered by story and section", source="§4.4.1 L1"
    )
    columns: list[_Column] = []
    excluded: list[_Excluded] = []
    for frame in selected:
        if frame.section not in sections:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"frame {frame.id} names an unknown section",
                field="frames",
            )
        vertical = _plan_dist_sq(frame) <= tolerance_sq
        trace.step(
            f"vertical_{frame.id}",
            vertical,
            formula="plan_distance_sq <= compare.length^2",
            source="§4.4.1 L2; §4.11 P2",
            uses=[_TRACE_TOL],
        )
        if vertical:
            columns.append(_column_row(frame, sections[frame.section]))
        else:
            excluded.append(_Excluded(frame_id=frame.id, reason="NOT_VERTICAL"))
    columns.sort(key=lambda row: row.frame_id)
    excluded.sort(key=lambda row: row.frame_id)
    status: _PASS_FAIL = "FAIL" if issues or not columns else "PASS"
    trace.step(
        "status",
        status,
        formula="FAIL when scope issues exist or no vertical column was selected",
        source="§4.4.1 L1, L2",
        uses=["scope_issues", "selected_frames"],
    )
    trace.output("status")
    return ColumnSelectBody(status=status, columns=columns, excluded=excluded, issues=issues)


__all__ = ["ColumnSelectBody", "ColumnSelectInput", "ColumnSelectScope", "column_select"]
