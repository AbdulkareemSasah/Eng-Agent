# ruff: noqa: N815  # B-392: field names with unit capitals are fixed by spec 0010 section 4.2
"""Payload models of the isolated-footing kinds (spec 0010 section 4.2); validation only.

Units: suffixes name the unit (`_mm`, `_mm2`, `_kN`); ratios are dimensionless. Errors: `pydantic.ValidationError`.
"""

from collections.abc import Iterable, Sequence
from typing import Annotated, Any, Literal, Self

from eng_contract.kinds.model import Combination
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

from eng_harness.kinds.calcs import CalcPayload

__all__ = ["FOOTING_KINDS"]

_Str = Annotated[str, StringConstraints(min_length=1, max_length=200)]
_Pos = Annotated[float, Field(gt=0)]
_Count = Annotated[int, Field(ge=0)]
_Ratio = Annotated[float, Field(ge=0)] | None
_Result = Annotated[str, StringConstraints(pattern=r"^res_[0-7][0-9A-HJKMNP-TV-Z]{25}$")]
_FAMILIES = ("bearing", "one_way_shear", "punching", "flexure", "min_steel", "development")
_Closure = Literal["passed", "failing", "needs_engineer"]


class _P(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


def _ordered(ids: Iterable[str], what: str) -> None:
    keys = list(ids)
    if keys != sorted(set(keys)):
        raise ValueError(f"{what} must be sorted and unique by id")


class Subject(_P):
    """A footing subject: a support joint under exactly one rectangular column (positions and sizes in mm)."""

    id: _Str
    joint: _Str
    column: _Str
    x_mm: float
    y_mm: float
    cx_mm: _Pos
    cy_mm: _Pos


class Excluded(_P):
    """A support joint that is not a subject, with the reason code."""

    joint: _Str
    column: _Str | None
    reason: _Str


class FootingSubjects(CalcPayload):
    """`harness.footing_subjects/1`."""

    subjects: list[Subject]
    excluded: list[Excluded]

    @model_validator(mode="after")
    def _check(self) -> Self:
        _ordered((s.id for s in self.subjects), "subjects")
        return self


class DimRow(_P):
    """Plan size, depth and bar spacing of one footing, with the origin of the sizes."""

    id: _Str
    Lx_mm: _Pos
    Ly_mm: _Pos
    h_mm: _Pos
    s_mm: _Pos
    source: Literal["calc", "engineer"]
    plan_at_max: StrictBool
    depth_at_max: StrictBool
    spacing_at_min: StrictBool
    status: _Str
    reason: _Str | None


class DesignRow(DimRow):
    """A footing with its layout: bars, effective depths, covers and reaction height (mm, mm2)."""

    db_mm: _Pos
    n_x: _Count
    n_y: _Count
    s_x_mm: _Pos
    s_y_mm: _Pos
    As_x_mm2: Annotated[float, Field(ge=0)]
    As_y_mm2: Annotated[float, Field(ge=0)]
    d_x_mm: _Pos
    d_y_mm: _Pos
    d_mm: _Pos
    cover_mm: Annotated[float, Field(ge=0)]
    end_cover_mm: Annotated[float, Field(ge=0)]
    reaction_height_mm: Annotated[float, Field(ge=0)]


class _ByFooting(CalcPayload):
    footings: Sequence[Any]

    @model_validator(mode="after")
    def _check(self) -> Self:
        _ordered((f.id for f in self.footings), "footings")
        return self


class FootingDims(_ByFooting):
    """`harness.footing_dims/1`."""

    footings: list[DimRow]


class FootingDesign(_ByFooting):
    """`harness.footing_design/1`."""

    footings: list[DesignRow]


class Family(_P):
    """Status of one check family with the governing ratio for display."""

    status: VerdictStatus
    ratio: _Ratio


class Families(_P):
    """The six check families (bearing, one-way shear, punching, flexure, minimum steel, development)."""

    bearing: Family
    one_way_shear: Family
    punching: Family
    flexure: Family
    min_steel: Family
    development: Family

    def closure(self) -> _Closure:
        """Spec 4.4.5: `passed` when all PASS, `failing` when any FAIL, else `needs_engineer`."""
        statuses = [getattr(self, name).status for name in _FAMILIES]
        if all(s == VerdictStatus.PASS for s in statuses):
            return "passed"
        return "failing" if VerdictStatus.FAIL in statuses else "needs_engineer"


class FailureState(_P):
    """`FootingFailureState` (spec 4.5): the six family statuses and four flags."""

    bearing: VerdictStatus
    one_way_shear: VerdictStatus
    punching: VerdictStatus
    flexure: VerdictStatus
    min_steel: VerdictStatus
    development: VerdictStatus
    plan_at_max: StrictBool
    depth_at_max: StrictBool
    spacing_at_min: StrictBool
    engineer_sized: StrictBool


class _Closed(_P):
    """Family statuses with the closure they imply."""

    families: Families
    closure: _Closure

    @model_validator(mode="after")
    def _closure_follows(self) -> Self:
        if self.closure != self.families.closure():
            raise ValueError("closure must follow the family statuses")
        return self


class StatusRow(_Closed):
    """Per footing: family statuses, closure and decision state."""

    id: _Str
    state: FailureState

    @model_validator(mode="after")
    def _check(self) -> Self:
        if any(getattr(self.state, n) != getattr(self.families, n).status for n in _FAMILIES):
            raise ValueError("state statuses must be those of families")
        return self


class FootingStatus(_ByFooting):
    """`harness.footing_status/1`."""

    footings: list[StatusRow]


class ScheduleRow(_Closed):
    """One footing of the schedule: design, statuses, reasons, references and the clearance neighbour."""

    design: DesignRow
    reasons: list[_Str]
    verdict_sets: list[_Result]
    decisions: list[_Str]
    neighbour: _Str | None


class FootingSchedule(CalcPayload):
    """`harness.footing_schedule/1` (spec 4.4.6)."""

    footings: list[ScheduleRow]

    @model_validator(mode="after")
    def _check(self) -> Self:
        _ordered((f.design.id for f in self.footings), "footings")
        return self


class PatternRow(_P):
    """One transferred pattern: applied FZ and base reaction FZ in kN, and the comparison outcome."""

    pattern: _Str
    self_weight: StrictBool
    applied_kN: float
    reaction_kN: float
    status: Literal["PASS", "FAIL", "NOT_COMPARED"]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.status == "NOT_COMPARED") != self.self_weight:
            raise ValueError("self_weight patterns, and only they, are NOT_COMPARED")
        return self


class SafeEquilibrium(CalcPayload):
    """`harness.safe_equilibrium/1` (spec 4.9 step 6); `tolerance` is the relative basis tolerance."""

    tolerance: Annotated[float, Field(ge=0)]
    patterns: list[PatternRow]


class JointLoadRow(_P):
    """One load row of `harness.reactions_to_joint_loads/1` (same shape as `harness.joint_loads/1` rows)."""

    joint: _Str
    pattern: _Str
    FX_kN: float
    FY_kN: float
    FZ_kN: float
    MX_kNm: float
    MY_kNm: float
    MZ_kNm: float
    punch_x_mm: Annotated[float, Field(gt=0)] | None = None
    punch_y_mm: Annotated[float, Field(gt=0)] | None = None


class JointLoads(_P):
    """Calc-facing shape of `harness.joint_loads/1` (spec 0008 §4.3; registered in `_kinds`).

    Allowed import for footing calcs (spec 0003 §4.3: `eng_harness.kinds.footing`).
    """

    axes: Literal["global"] = "global"
    loads: list[JointLoadRow]


class ModelPoint(_P):
    """One point of `harness.model_points/1` (spec 0008 §4.4); calc-facing input for T10."""

    name: _Str
    x_mm: float
    y_mm: float
    z_mm: float


class ModelPoints(_P):
    """Calc-facing shape of `harness.model_points/1` (spec 0008 §4.4; registered in `_kinds`)."""

    points: list[ModelPoint]


class HarnessCaseRef(_P):
    """Case reference on `harness.base_reactions/1` rows (spec 0008 §4.6)."""

    case: _Str
    case_type: Literal["load_pattern", "load_case", "load_combination"]
    step: str | None = None


class BaseReactionRow(_P):
    """One row of `harness.base_reactions/1` (spec 0008 §4.6); calc-facing input for T10."""

    case: HarnessCaseRef
    FX_kN: float
    FY_kN: float
    FZ_kN: float
    MX_kNm: float
    MY_kNm: float
    MZ_kNm: float


class BaseReactions(_P):
    """Calc-facing shape of `harness.base_reactions/1` (spec 0008 §4.6; registered in `_kinds`)."""

    moment_reference: Literal["host_unconfirmed/1"]
    rows: list[BaseReactionRow]


class ReactionsToJointLoads(CalcPayload):
    """Result of `harness.reactions_to_joint_loads` (spec 0010 4.9): loads plus combinations to add.

    `status` / `reason` carry engineering outcomes of §4.9 (M2 unmatched, M4 missing pattern, step-2 combo
    conflict) as payload statuses per spec 0003 §4.2; `OK` has `reason` null.
    """

    axes: Literal["global"] = "global"
    loads: list[JointLoadRow]
    combinations_to_add: list[Combination]
    status: _Str
    reason: _Str | None


FOOTING_KINDS: dict[str, type[BaseModel]] = {
    "harness.footing_subjects/1": FootingSubjects,
    "harness.footing_dims/1": FootingDims,
    "harness.footing_design/1": FootingDesign,
    "harness.footing_status/1": FootingStatus,
    "harness.footing_schedule/1": FootingSchedule,
    "harness.safe_equilibrium/1": SafeEquilibrium,
    "harness.reactions_to_joint_loads/1": ReactionsToJointLoads,
}
"""The footing kinds by name, registered in `eng_harness._kinds`."""
