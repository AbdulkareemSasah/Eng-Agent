"""Column-workflow kind payloads (spec 0013 sections 4.2 and 4.4). Errors: `pydantic.ValidationError`."""

from typing import Annotated, Literal, Self

from eng_contract.refs import RefString
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

from eng_harness.kinds.calcs import CalcPayload, SummaryChanges, Top
from eng_harness.kinds.edit_cycle import Label

_Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Count = Annotated[int, Field(ge=0)]
_Fingerprint = Annotated[str, StringConstraints(pattern=r"^fp1:[0-9a-f]{64}$")]
_ColumnShape = Literal["rectangular", "circular", "other"]
_MatchStatus = Literal["matched", "no_section_in_model", "ambiguous"]
_PassFail = Literal["PASS", "FAIL"]
_CheckIds = (
    "aci318_14.22_4_2_1.max_axial_strength",
    "aci318_14.22_4_1_1.axial_flexure_uniaxial",
    "aci318_14.10_6_1_1.longitudinal_reinforcement_limits",
)
_ReinforcementLimitsCheck = _CheckIds[2]


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
    inputs: dict[str, RefString]


class _Miss(_P):
    frame_id: Label
    code: Literal["FORCES_MISSING", "AXES_UNDECLARED", "SHAPE_NOT_CHECKED", "LAYOUT_MISSING"]
    gap: Label | None = None


class _Gov(_P):
    ref: RefString
    ratio: float | None = None


class _ReviewRow(_P):
    frame_id: Label
    status: VerdictStatus
    host_status: VerdictStatus
    code_status: VerdictStatus
    governing: _Gov | None = None
    not_checked: list[Label]
    gaps: list[Label]

    @model_validator(mode="after")
    def _needs_engineer_when_not_checked(self) -> Self:
        if self.not_checked and self.status is not VerdictStatus.NEEDS_ENGINEER:
            raise ValueError("status is NEEDS_ENGINEER when not_checked is set")
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

    columns: list[_ReviewRow]
    failing: list[Label]
    attention: list[Label]
    top: Top
    changes: SummaryChanges
    complete: StrictBool


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
