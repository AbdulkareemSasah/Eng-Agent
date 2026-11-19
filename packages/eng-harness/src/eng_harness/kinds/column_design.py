"""Column-workflow kind payloads (spec 0013 sections 4.2 and 4.4). Errors: `pydantic.ValidationError`."""

import re
from collections.abc import Iterable
from typing import Annotated, Any, Literal, Self

from eng_contract.refs import Ref, RefString
from eng_contract.verdicts import CODE_PACK_CHECK_ID, HOST_CHECK_ID, VerdictSource, VerdictStatus
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StringConstraints,
    model_validator,
)

from eng_harness.kinds.calcs import CalcPayload, Top
from eng_harness.kinds.edit_cycle import Label

_Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Count = Annotated[int, Field(ge=0)]
_Ratio = Annotated[float, Field(ge=0)] | None
_CheckId = Annotated[str, StringConstraints(pattern=HOST_CHECK_ID, max_length=200)]
_Fingerprint = Annotated[str, StringConstraints(pattern=r"^fp1:[0-9a-f]{64}$")]
_ColumnShape = Literal["rectangular", "circular", "other"]
_MatchStatus = Literal["matched", "no_section_in_model", "ambiguous"]
_PassFail = Literal["PASS", "FAIL"]
_FiniteFloat = Annotated[StrictFloat, Field(allow_inf_nan=False)]
_ItemInput = StrictInt | _FiniteFloat | Ref | Literal["tied"]
_INT_INPUTS = frozenset(("n_bars_b", "n_bars_h"))
_REF_INPUTS = frozenset(("fc_MPa", "fy_MPa", "k_factor", "ratio_limit"))
_TIED_INPUT = "transverse_kind"
_CheckIds = (
    "aci318_14.22_4_2_1.max_axial_strength",
    "aci318_14.22_4_1_1.axial_flexure_uniaxial",
    "aci318_14.10_6_1_1.longitudinal_reinforcement_limits",
)
_ReinforcementLimitsCheck = _CheckIds[2]


def _ordered(items: Iterable[Any], what: str) -> None:
    keys = list(items)
    if keys != sorted(set(keys)):
        raise ValueError(f"{what} must be sorted and unique")


class _P(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class _Column(_P):
    frame_id: Label
    section: Label
    shape: _ColumnShape
    material: Label
    story: Label
    length_mm: float


class _Excluded(_P):
    frame_id: Label
    reason: Literal["NOT_VERTICAL"]


class _SelIssue(_P):
    code: Literal["UNKNOWN_FRAME", "UNKNOWN_STORY", "UNKNOWN_SECTION"]
    name: Label


class _Subject(_P):
    kind: Literal["frame"]
    id: Label
    station_mm: float | None = None
    case: Label | None = None


class _Item(_P):
    subject: _Subject
    inputs: dict[str, _ItemInput]

    @model_validator(mode="after")
    def _field_shapes(self) -> Self:
        for name, val in self.inputs.items():
            if name in _INT_INPUTS:
                if type(val) is not int:
                    raise ValueError(f"{name} must be a strict integer")
            elif name == _TIED_INPUT:
                if val != "tied":
                    raise ValueError(f"{name} must be 'tied'")
            elif name in _REF_INPUTS:
                if not isinstance(val, Ref):
                    raise ValueError(f"{name} must be a $ref object")
            elif type(val) not in (int, float):
                raise ValueError(f"{name} must be a finite number")
        return self


class _Miss(_P):
    frame_id: Label
    code: Literal["FORCES_MISSING", "AXES_UNDECLARED", "SHAPE_NOT_CHECKED", "LAYOUT_MISSING"]
    gap: Label | None = None


class ColumnGoverning(_P):
    """Governing verdict reference and copied ratio of one reviewed column (spec 0013 section 4.4.3 R3)."""

    ref: RefString
    ratio: _Ratio = None


class ColumnReviewRow(_P):
    """Review summary of one selected column (spec 0013 section 4.4.3)."""

    frame_id: Label
    status: VerdictStatus
    host_status: VerdictStatus
    code_status: VerdictStatus
    governing: ColumnGoverning | None = None
    not_checked: list[Label]
    gaps: list[Label]

    @model_validator(mode="after")
    def _needs_engineer_when_not_checked(self) -> Self:
        if self.not_checked and self.status is not VerdictStatus.NEEDS_ENGINEER:
            raise ValueError("status is NEEDS_ENGINEER when not_checked is set")
        return self


class _ColumnMemberKey(_P):
    frame_id: Label
    source: VerdictSource
    check_id: _CheckId

    @model_validator(mode="after")
    def _check_id_matches_source(self) -> Self:
        pattern = CODE_PACK_CHECK_ID if self.source is VerdictSource.CODE_PACK else HOST_CHECK_ID
        if not re.fullmatch(pattern, self.check_id):
            raise ValueError(f"check_id {self.check_id!r} does not match the {self.source.value} pattern")
        return self


class ColumnMember(_ColumnMemberKey):
    """A column member keyed by `(frame_id, source, check_id)` with its worst status and largest ratio (0003 S5)."""

    status: VerdictStatus
    ratio: _Ratio


class ColumnMemberChange(_ColumnMemberKey):
    """A column member whose status differs from the previous review (spec 0013 section 4.4.3 R4)."""

    previous_status: VerdictStatus
    status: VerdictStatus
    previous_ratio: _Ratio
    ratio: _Ratio


class ColumnReviewChanges(_P):
    """Status transitions and appeared/disappeared members against the previous column review (0003 S5 table)."""

    newly_failing: list[ColumnMemberChange]
    newly_passing: list[ColumnMemberChange]
    other_changes: list[ColumnMemberChange]
    appeared: list[ColumnMember]
    disappeared: list[ColumnMember]

    @model_validator(mode="after")
    def _check(self) -> Self:
        fail, ok = VerdictStatus.FAIL, VerdictStatus.PASS
        bad = (
            any(c.status is not fail or c.previous_status is fail for c in self.newly_failing),
            any(c.status is not ok or c.previous_status is not fail for c in self.newly_passing),
            any(
                c.status is c.previous_status or c.status is fail or (c.previous_status is fail and c.status is ok)
                for c in self.other_changes
            ),
        )
        names = ("newly_failing", "newly_passing", "other_changes")
        if wrong := [n for n, b in zip(names, bad, strict=True) if b]:
            raise ValueError(f"a row of {wrong[0]} does not fit that list")
        for field_name in ("newly_failing", "newly_passing", "other_changes", "appeared", "disappeared"):
            rows = getattr(self, field_name)
            _ordered([(r.frame_id, r.source.value, r.check_id) for r in rows], field_name)
        return self


class _FrameItem(_P):
    id: Label
    kind: Literal["frame_section"]
    frames: list[Label]
    section: Label


class _ChangeIssue(_P):
    frame_id: Label
    code: Literal["NOT_IMPLEMENTED"]
    gap: Literal["CW-G3"]


class _NewType(_P):
    family: Label
    section: Label
    name: Label
    from_unique_id: Label
    origins: list[Literal["preexisting", "changed_in_design"]]
    roles: dict[str, RefString]


class _Same(_P):
    unique_id: Label
    type_id: Label


class _Assign(_P):
    unique_id: Label
    element_id: Label
    from_type_id: Label
    type_id: Label | None = None
    new_type_name: Label | None = None
    origin: Literal["preexisting", "changed_in_design"]

    @model_validator(mode="after")
    def _type_or_name(self) -> Self:
        if (self.type_id is None) == (self.new_type_name is None):
            raise ValueError("give type_id or new_type_name, not both and not neither")
        return self


class _Blocked(_P):
    frame_id: Label
    code: Literal[
        "SHAPE_NOT_SUPPORTED",
        "SECTION_ROLES_UNMAPPED",
        "TYPE_AMBIGUOUS",
        "NAME_CONFLICT",
    ]


class _Orient(_P):
    frame_id: Label
    rotations: tuple[RefString, RefString]


class _ExpectEl(_P):
    unique_id: Label
    type_name: Label


class _ExpectType(_P):
    name: Label
    roles: dict[str, RefString]


class _Expected(_P):
    elements: list[_ExpectEl]
    types: list[_ExpectType]


class _RbIssue(_P):
    unique_id: Label
    code: Literal[
        "ELEMENT_MISSING",
        "TYPE_MISMATCH",
        "VALUE_MISMATCH",
        "UNEXPECTED_TYPE_CHANGE",
        "NOT_READ",
    ]


class _Changed(_P):
    frame_id: Label
    from_section: Label
    to_section: Label


class ColumnSelection(CalcPayload):
    """`harness.column_selection/1` (spec 0013 section 4.4.1)."""

    status: _PassFail
    columns: list[_Column]
    excluded: list[_Excluded]
    issues: list[_SelIssue]

    @model_validator(mode="after")
    def _status_on_failure(self) -> Self:
        failed = bool(self.issues) or not self.columns
        if (self.status == "FAIL") != failed:
            raise ValueError("status is FAIL on an error issue or an empty selection")
        return self


class ColumnCheckItems(CalcPayload):
    """`harness.column_check_items/1` (spec 0013 section 4.4.2)."""

    items: dict[str, list[_Item]]
    not_checked: list[_Miss]

    @model_validator(mode="after")
    def _check_ids_and_subjects(self) -> Self:
        if set(self.items) != set(_CheckIds):
            raise ValueError("items must hold the three check ids")
        for check_id, group in self.items.items():
            for row in group:
                subject = row.subject
                bare = subject.case is None and subject.station_mm is None
                if bare != (check_id == _ReinforcementLimitsCheck):
                    raise ValueError("case and station_mm are null exactly for the reinforcement limits")
        return self


class ColumnReview(CalcPayload):
    """`harness.column_review/1` (spec 0013 section 4.4.3)."""

    columns: list[ColumnReviewRow]
    failing: list[Label]
    attention: list[Label]
    top: Top
    members: list[ColumnMember]
    changes: ColumnReviewChanges
    complete: StrictBool

    @model_validator(mode="after")
    def _check(self) -> Self:
        _ordered([row.frame_id for row in self.columns], "columns")
        _ordered([(m.frame_id, m.source.value, m.check_id) for m in self.members], "members")
        known = {row.frame_id for row in self.columns}
        if unknown := sorted({m.frame_id for m in self.members} - known):
            raise ValueError(f"members name unknown columns: {unknown}")
        want_failing = [row.frame_id for row in self.columns if row.status is VerdictStatus.FAIL]
        if self.failing != want_failing:
            raise ValueError("failing must list the FAIL columns in frame_id order")
        want_attention = [
            row.frame_id for row in self.columns if row.status in (VerdictStatus.NEEDS_ENGINEER, VerdictStatus.ERROR)
        ]
        if self.attention != want_attention:
            raise ValueError("attention must list the NEEDS_ENGINEER and ERROR columns in frame_id order")
        return self


class ColumnMatch(CalcPayload):
    """`harness.column_match/1` (spec 0013 section 4.4.4)."""

    status: _MatchStatus
    section: Label | None = None
    names: list[Label]

    @model_validator(mode="after")
    def _status_agrees_with_names(self) -> Self:
        one = self.section is not None and self.names == [self.section]
        none = self.section is None and not self.names
        several = self.section is None and len(self.names) > 1  # spec 0013 section 4.4.4: several
        agreed = {"matched": one, "no_section_in_model": none, "ambiguous": several}[self.status]
        if not agreed:
            raise ValueError("section and names must agree with status")
        return self


class GeneratedChangeSet(CalcPayload):
    """`harness.generated_change_set/1` (spec 0013 section 4.4.4)."""

    source: Label
    items: list[_FrameItem]
    issues: list[_ChangeIssue]
    note: Label | None = None
    benchmark_request: Label | None = None

    @model_validator(mode="after")
    def _items_sorted_by_frame(self) -> Self:
        frames = [item.frames for item in self.items]
        keys = [row[0] for row in frames if row]
        if len(keys) != len(frames) or keys != sorted(keys):
            raise ValueError("items must name one frame and be sorted by frame id")
        return self


class RevitColumnUpdate(CalcPayload):
    """`harness.revit_column_update/1` (spec 0013 section 4.4.5)."""

    new_types: list[_NewType]
    assignments: list[_Assign]
    no_change: list[_Same]
    not_updatable: list[_Blocked]
    orientation: list[_Orient]
    expected: _Expected
    complete: StrictBool


class RevitColumnReadback(CalcPayload):
    """`harness.revit_column_readback/1` (spec 0013 section 4.4.6)."""

    status: _PassFail
    issues: list[_RbIssue]
    before_revision: _Count
    after_revision: _Count

    @model_validator(mode="after")
    def _status_on_issues(self) -> Self:
        later = self.after_revision > self.before_revision
        want = "PASS" if not self.issues and later else "FAIL"
        if self.status != want:
            raise ValueError("status is PASS only without issues and with a later revision")
        return self


class ColumnDesignRecord(_P):
    """`harness.column_design_record/1` (spec 0013 section 4.2)."""

    revision: Label
    fingerprint: _Fingerprint
    file_sha256: _Sha
    changed: list[_Changed]
    selection: RefString
    review: RefString

    @model_validator(mode="after")
    def _changed_unique(self) -> Self:
        ids = [row.frame_id for row in self.changed]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate frame id in changed")
        return self


COLUMN_DESIGN_KINDS: dict[str, type[BaseModel]] = {
    "harness.column_selection/1": ColumnSelection,
    "harness.column_check_items/1": ColumnCheckItems,
    "harness.column_review/1": ColumnReview,
    "harness.column_match/1": ColumnMatch,
    "harness.generated_change_set/1": GeneratedChangeSet,
    "harness.revit_column_update/1": RevitColumnUpdate,
    "harness.revit_column_readback/1": RevitColumnReadback,
    "harness.column_design_record/1": ColumnDesignRecord,
}
