"""Calc `harness.footing_subjects` v1: which support joints are footing subjects (spec 0010 4.4.1).

Purpose: a subject is a support joint (one with reaction rows) under exactly one rectangular column whose axes lie
along the global axes; every other support joint is excluded with a reason, never dropped.
Units: lengths in mm, angles in deg. Angle comparisons are exact (`Fraction` of the stored binary value).
Errors: `ContractError` `INVALID_ARGUMENT` (basis field missing, unconfirmed or not a number; a column's section is not
in the sections), `UNIT_MISMATCH` (basis field not in deg), `OUT_OF_RANGE` (basis field below zero).
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum
from fractions import Fraction
from typing import Any

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.forces import JointReactions
from eng_contract.kinds.model import Frame, FrameKind, FramePlacements, Rectangular, Sections
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.kinds.footing import Excluded, Subject

BASIS_FIELDS = ("compare.angle",)
"""The basis paths this calc reads (spec 0003 4.4); the workflow declares them required."""
ZERO_TURN = Cited(
    value=0, unit="deg", source="Geometry: zero rotation; also the lower bound of compare.angle (spec 0003 4.4)"
)
QUARTER_TURN = Cited(value=90, unit="deg", source="Geometry: a right angle is 90 degrees")
HALF_TURN = Cited(value=180, unit="deg", source="Geometry: a straight angle is 180 degrees")
THREE_QUARTER_TURN = Cited(value=270, unit="deg", source="Geometry: three right angles are 270 degrees")
FULL_TURN = Cited(value=360, unit="deg", source="Geometry: a full turn is 360 degrees")
VERSION = Cited(value=1, unit="1", source="Calc version 1 of spec 0010 4.4.1; a change of method is a new version")
_ANGLE = "compare.angle"


class ExclusionReason(StrEnum):
    """Why a support joint is no subject (spec 0010 AC6)."""

    NO_COLUMN_AT_JOINT = "NO_COLUMN_AT_JOINT"
    TWO_COLUMNS_AT_JOINT = "TWO_COLUMNS_AT_JOINT"
    SECTION_NOT_RECTANGULAR = "SECTION_NOT_RECTANGULAR"
    COLUMN_ROTATED = "COLUMN_ROTATED"


class SubjectsInput(CalcInput):
    """Input: the frames, the sections, the joint reactions and the design basis, all by reference."""

    placements: FramePlacements = eng_param(
        ref_capable=True, ref_kinds={"model.frame_placements/1"}, engineering_quantity=True
    )
    sections: Sections = eng_param(ref_capable=True, ref_kinds={"model.sections/1"}, engineering_quantity=True)
    reactions: JointReactions = eng_param(
        ref_capable=True, ref_kinds={"forces.joint_reactions/1"}, engineering_quantity=True
    )
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)


class SubjectsBody(BaseModel):
    """The payload of `harness.footing_subjects/1` without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subjects: list[Subject]
    excluded: list[Excluded]


def _refuse(code: ErrorCode, message: str, **fields: Any) -> ContractError:
    return ContractError(code, f"basis field {_ANGLE} {message}", field="basis", **fields)


def _angle_value(basis: DesignBasis) -> int | float:
    """The stored value of the basis angle tolerance, after the checks of spec 0003 4.4 (confirmed, deg, >= 0)."""
    field = basis.fields.get(_ANGLE)
    if field is None or not field.confirmed:
        raise _refuse(ErrorCode.INVALID_ARGUMENT, "is missing or not confirmed", hint=f"confirm {_ANGLE}")
    if field.unit != ZERO_TURN.unit:
        raise _refuse(ErrorCode.UNIT_MISMATCH, "must be in deg", expected={"unit": ZERO_TURN.unit}, received=field.unit)
    value = field.value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _refuse(ErrorCode.INVALID_ARGUMENT, "is not a number")
    if value < ZERO_TURN.value:
        raise _refuse(ErrorCode.OUT_OF_RANGE, "is below zero", expected={"min": ZERO_TURN.value}, received=value)
    return value


def _lower_end(frame: Frame) -> tuple[str | None, float, float] | None:
    """S1: the joint name, x and y of the end with the smaller z, or None when both ends are at one height."""
    if frame.i.z_mm == frame.j.z_mm:
        return None
    end, joint = (frame.i, frame.i_joint) if frame.i.z_mm < frame.j.z_mm else (frame.j, frame.j_joint)
    return joint, end.x_mm, end.y_mm


def _within(angle: Fraction, targets: Iterable[Cited], tolerance: Fraction) -> bool:
    """Whether `angle` (in [0, full turn)) is within `tolerance` of a target, by circular distance (S5)."""
    full = Fraction(FULL_TURN.value)
    gaps = (abs(angle - Fraction(t.value)) for t in targets)
    return any(min(gap, full - gap) <= tolerance for gap in gaps)


def _orientation(rotation_deg: float, tolerance: Fraction) -> bool | None:
    """S5: True when the section width lies along global X, False when across, None when undecided or rotated."""
    angle = Fraction(rotation_deg) % Fraction(FULL_TURN.value)
    along = _within(angle, (ZERO_TURN, HALF_TURN), tolerance)
    across = _within(angle, (QUARTER_TURN, THREE_QUARTER_TURN), tolerance)
    return along if along != across else None


def _decide(
    joint: str, found: list[tuple[Frame, float, float]], shapes: Mapping[str, object], tolerance: Fraction
) -> Subject | Excluded:
    """S3 to S6 for one support joint: the subject, or the exclusion with its reason."""
    if len(found) > 1:
        return Excluded(joint=joint, column=None, reason=ExclusionReason.TWO_COLUMNS_AT_JOINT.value)
    if not found:
        return Excluded(joint=joint, column=None, reason=ExclusionReason.NO_COLUMN_AT_JOINT.value)
    frame, x_mm, y_mm = found[0]
    if frame.section not in shapes:
        message = f"section {frame.section} of column {frame.id} is not in the sections"
        raise ContractError(ErrorCode.INVALID_ARGUMENT, message, field="sections", received=frame.section[:200])
    shape = shapes[frame.section]
    along = _orientation(frame.rotation_deg, tolerance)
    if not isinstance(shape, Rectangular):
        return Excluded(joint=joint, column=frame.id, reason=ExclusionReason.SECTION_NOT_RECTANGULAR.value)
    if along is None:
        return Excluded(joint=joint, column=frame.id, reason=ExclusionReason.COLUMN_ROTATED.value)
    cx_mm, cy_mm = (shape.b_mm, shape.h_mm) if along else (shape.h_mm, shape.b_mm)
    return Subject(id=joint, joint=joint, column=frame.id, x_mm=x_mm, y_mm=y_mm, cx_mm=cx_mm, cy_mm=cy_mm)


@calc(
    id="harness.footing_subjects",
    version=int(VERSION.value),
    output_kind="harness.footing_subjects/1",
    title="Footing subjects: support joints under one rectangular column",
    method_source="eng-harness spec 0010 §4.4.1 (S1 to S6)",
    verification="draft",
)
def footing_subjects(inp: SubjectsInput, meta: InputMeta, trace: TraceBuilder) -> SubjectsBody:
    """Find the footing subjects among the support joints and give each excluded joint its reason.

    Raises:
        ContractError: see the module docstring.
    """
    angle_value = _angle_value(inp.basis)
    frames, rows = inp.placements.frames, inp.reactions.rows
    ref = {name: meta.refs[name].result_id for name in ("placements", "sections", "reactions", "basis")}
    trace.input("frames", len(frames), ref=ref["placements"])
    trace.input("frame_sections", len(inp.sections.frame_sections), ref=ref["sections"])
    trace.input("reaction_rows", len(rows), ref=ref["reactions"])
    trace.input("compare_angle", angle_value, unit="deg", ref=f"{ref['basis']}#/fields/{_ANGLE}")
    constants = (ZERO_TURN, QUARTER_TURN, HALF_TURN, THREE_QUARTER_TURN, FULL_TURN)
    names = ("zero_turn", "quarter_turn", "half_turn", "three_quarter_turn", "full_turn")
    for name, cited in zip(names, constants, strict=True):
        trace.constant(name, cited)
    columns: dict[str, list[tuple[Frame, float, float]]] = {}
    for frame in frames:
        end = _lower_end(frame) if frame.kind is FrameKind.COLUMN else None
        if end is not None and end[0] is not None:
            columns.setdefault(end[0], []).append((frame, end[1], end[2]))
    joints = sorted({row.joint for row in rows})
    shapes = {s.name: s.shape for s in inp.sections.frame_sections}
    outcomes = [_decide(joint, columns.get(joint, []), shapes, Fraction(angle_value)) for joint in joints]
    subjects = [o for o in outcomes if isinstance(o, Subject)]
    excluded = [o for o in outcomes if isinstance(o, Excluded)]
    rule = "spec 0010 4.4.1"
    for name, value, formula, part, uses in (
        ("columns", sum(len(v) for v in columns.values()), "column frames with a named lower joint", "S1", ["frames"]),
        ("support_joints", len(joints), "distinct joints in the reaction rows", "S2", ["reaction_rows"]),
        (
            "subjects",
            len(subjects),
            "joints under one rectangular column along the axes",
            "S3 to S6",
            ["columns", "support_joints", "frame_sections", "compare_angle", *names],
        ),
        ("excluded", len(excluded), "support_joints - subjects", "S3 to S5", ["support_joints", "subjects"]),
    ):
        trace.step(name, value, formula=formula, source=f"{rule} {part}", uses=uses)
    trace.output("subjects", "excluded")
    return SubjectsBody(subjects=subjects, excluded=excluded)
