"""Payload models of the calc kinds (spec 0003 4.6 to 4.11) and `harness.expected_effects/1`.

Purpose: the stored form of each calc result, with the rules a reader may rely on (counts match rows, lists sorted,
fingerprint form, top-N label). Every calc payload also carries `calc` (`CalcMeta`), `draft` and the `trace`.
Units: fields with a unit suffix are in the unit the suffix names; `Quantity` fields carry their own unit.
Errors: `pydantic.ValidationError` for every violated rule.
"""

from collections import Counter
from collections.abc import Iterable
from fractions import Fraction
from typing import Annotated, Any, Literal, Self

from eng_contract.ids import ModelId, ResultId
from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.quantity import Quantity
from eng_contract.refs import RefString
from eng_contract.trace import Trace
from eng_contract.verdicts import HOST_CHECK_ID, SubjectKind, VerdictStatus
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StringConstraints, model_validator

from eng_harness.calc import CalcStatus

__all__ = [
    "CALC_KINDS",
    "CalcMeta",
    "CalcPayload",
    "DesignSummary",
    "ExpectedEffects",
    "ModelDiff",
    "ModelFingerprint",
    "PlacementComparison",
    "ReadbackCheck",
    "SectionSize",
]

_Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Str = Annotated[str, StringConstraints(min_length=1, max_length=200)]
_Ptr = Annotated[str, StringConstraints(pattern=r"^(/([^~/]|~[01])*)*$")]
_Count = Annotated[int, Field(ge=0)]
_Ratio = Annotated[float, Field(ge=0)] | None


class _P(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


def _ordered(items: Iterable[Any], what: str) -> None:
    keys = list(items)
    if keys != sorted(set(keys)):
        raise ValueError(f"{what} must be sorted and unique")


class CalcMeta(_P):
    """Identity of the calc that made a result: id, version, content hash and status at run time."""

    id: Annotated[str, StringConstraints(pattern=r"^harness\.[a-z][a-z0-9_]*$")]
    version: Annotated[int, Field(ge=1, le=9999)]
    content_sha256: _Sha
    status: CalcStatus


class CalcPayload(_P):
    """Base of the calc payloads; the trace must belong to the calc named in `calc`."""

    calc: CalcMeta
    draft: StrictBool
    trace: Trace

    @model_validator(mode="after")
    def _trace_is_the_calcs(self) -> Self:
        t, c = self.trace, self.calc
        if (t.calc_id, t.calc_version, t.content_sha256) != (c.id, str(c.version), c.content_sha256):
            raise ValueError("trace calc_id, calc_version and content_sha256 must be those of calc")
        return self


class FpSection(_P):
    """One hashed section of a fingerprint."""

    kind: _Str
    result_id: ResultId
    items: _Count
    sha256: _Sha
    complete: StrictBool


class ModelFingerprint(CalcPayload):
    """`harness.model_fingerprint/1` (4.6)."""

    method: Literal["harness.fp/1"]
    model_id: ModelId
    model_revision: _Count
    sections: list[FpSection]
    covered: list[_Str]
    complete: StrictBool
    fingerprint: Annotated[str, StringConstraints(pattern=r"^fp1:[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def _check(self) -> Self:
        kinds = [s.kind for s in self.sections]
        _ordered(kinds, "sections")
        if self.covered != kinds:
            raise ValueError("covered must list the kinds of sections")
        if self.complete != all(s.complete for s in self.sections):
            raise ValueError("complete must be the conjunction of the sections")
        return self


class Side(_P):
    """One side of a comparison."""

    model_id: ModelId
    model_revision: _Count
    covered: list[_Str]


class Tolerance(_P):
    """A tolerance taken from the design basis."""

    value: Annotated[float, Field(ge=0)]
    unit: _Str
    ref: RefString


class PropertyRow(_P):
    """One compared property (rule D3 to D5)."""

    pointer: _Ptr
    before: JsonValue
    after: JsonValue
    unit: str | None
    quantity_kind: str | None
    tolerance: _Ratio
    rule: _Str


class WithinRow(PropertyRow):
    """A property equal within tolerance, with its object."""

    section: _Str
    key: list[str]


class Change(_P):
    """An object that was added, removed, changed or ambiguous."""

    section: _Str
    key: list[str]
    change: Literal["added", "removed", "changed", "ambiguous"]
    before: JsonValue
    after: JsonValue
    properties: list[PropertyRow]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.change == "changed") != bool(self.properties):
            raise ValueError("properties are set exactly for a changed object")
        return self


class SectionCounts(_P):
    """Per section tally of a difference report."""

    added: _Count
    removed: _Count
    changed: _Count
    ambiguous: _Count
    unchanged: _Count
    within_tolerance: _Count


class DiffBody(_P):
    """The difference report without calc fields; embedded in the read-back check."""

    before: Side
    after: Side
    tolerances: dict[str, Tolerance]
    changes: list[Change]
    within_tolerance: list[WithinRow]
    not_compared: list[_Str]
    counts: dict[str, SectionCounts]
    identical: StrictBool
    complete: StrictBool

    @model_validator(mode="after")
    def _check(self) -> Self:
        _ordered([(c.section, tuple(c.key)) for c in self.changes], "changes")
        tally = Counter((c.section, c.change) for c in self.changes)
        within = Counter(w.section for w in self.within_tolerance)
        for section in {c.section for c in self.changes} | set(within) | set(self.counts):
            row = self.counts.get(section)
            got = (row.added, row.removed, row.changed, row.ambiguous, row.within_tolerance) if row else None
            want = (*(tally[section, k] for k in ("added", "removed", "changed", "ambiguous")), within[section])
            if got != want:
                raise ValueError(f"counts of {section} do not match the rows")
        if self.identical != (not self.changes and not self.not_compared and self.complete):
            raise ValueError("identical needs no changes, nothing not compared and complete sides")
        return self


class ModelDiff(CalcPayload, DiffBody):
    """`harness.model_diff/1` (4.7)."""


class Effect(_P):
    """One expected effect of a change set on a model section."""

    item_id: _Str
    section: _Str
    key: list[str]
    op: Literal["set", "add", "remove"]
    pointer: _Ptr | None = None
    value: JsonValue = None
    unit: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.section not in NEUTRAL_KINDS or not self.section.startswith("model."):
            raise ValueError(f"section {self.section!r} is not a neutral model kind")
        if self.op == "set" and self.pointer is None:
            raise ValueError("set needs a pointer (a null value is valid)")
        if self.op == "add" and (self.pointer is not None or not isinstance(self.value, dict)):
            raise ValueError("add needs an object value and no pointer")
        if self.op == "remove" and (self.pointer is not None or self.value is not None):
            raise ValueError("remove takes neither pointer nor value")
        return self


class ExpectedEffects(_P):
    """`harness.expected_effects/1` (4.8): what a change set should have done; made by spec 0007."""

    change_set: RefString
    model_id: ModelId
    effects: list[Effect]

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [e.item_id for e in self.effects]
        if duplicated := sorted({i for i in ids if ids.count(i) > 1}):
            raise ValueError(f"duplicate item_id: {duplicated}")
        return self


class ReadbackItem(_P):
    """The read-back result of one effect."""

    item_id: _Str
    result: Literal["match", "mismatch", "missing", "not_read"]
    expected: JsonValue
    read: JsonValue
    tolerance: _Ratio
    rule: _Str


class Unexpected(_P):
    """A difference that no effect explains."""

    section: _Str
    key: list[str]
    pointer: _Ptr | None


class ReadbackCheck(CalcPayload):
    """`harness.readback_check/1` (4.8)."""

    status: Literal[VerdictStatus.PASS, VerdictStatus.FAIL, VerdictStatus.NEEDS_ENGINEER]
    items: list[ReadbackItem]
    unexpected: list[Unexpected]
    diff: DiffBody
    complete: StrictBool

    @model_validator(mode="after")
    def _check(self) -> Self:
        results = {i.result for i in self.items}
        if results & {"mismatch", "missing"} or self.unexpected:
            want = VerdictStatus.FAIL
        elif (
            "not_read" in results
            or not self.complete
            or self.diff.not_compared
            or any(c.change == "ambiguous" for c in self.diff.changes)
        ):
            want = VerdictStatus.NEEDS_ENGINEER
        else:
            want = VerdictStatus.PASS
        if self.status is not want:
            raise ValueError(f"status must be {want.value} by rule R4")
        return self


_CheckId = Annotated[str, StringConstraints(pattern=HOST_CHECK_ID, max_length=200)]


class _Key(_P):
    subject_kind: SubjectKind
    subject_id: _Str
    check_id: _CheckId


class VerdictRow(_Key):
    """A host verdict as listed in the summary."""

    case: str | None
    station_mm: _Ratio
    ratio: _Ratio
    ratio_limit: Annotated[float, Field(gt=0)]
    status: VerdictStatus

    @model_validator(mode="after")
    def _ratio_agrees(self) -> Self:
        if self.status in (VerdictStatus.PASS, VerdictStatus.FAIL):
            if self.ratio is None:
                raise ValueError(f"status {self.status.value} requires a ratio")
            if (self.ratio <= self.ratio_limit) != (self.status is VerdictStatus.PASS):
                raise ValueError(f"status {self.status.value} contradicts ratio and ratio_limit")
        return self


class Member(_Key):
    """A member (subject kind, subject id, check id) with its worst status and largest ratio (S5)."""

    status: VerdictStatus
    ratio: _Ratio


class MemberChange(_Key):
    """A member whose status differs from the previous summary."""

    previous_status: VerdictStatus
    status: VerdictStatus
    previous_ratio: _Ratio
    ratio: _Ratio


class GroupRow(_P):
    """The governing verdict of one subject kind and check id."""

    subject_kind: SubjectKind
    check_id: _CheckId
    row: VerdictRow

    @model_validator(mode="after")
    def _row_in_group(self) -> Self:
        if (self.row.subject_kind, self.row.check_id) != (self.subject_kind, self.check_id):
            raise ValueError("row does not match its group (subject_kind, check_id)")
        return self


class SubjectRef(_P):
    """A distinct subject."""

    kind: _Str
    id: _Str


class Top(_P):
    """The first `n` verdicts by ratio, stated as "top N of M by ratio"."""

    n: _Count
    of_total: _Count
    rows: list[VerdictRow]
    label: str

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.n != len(self.rows) or self.n > self.of_total:
            raise ValueError("n must be the number of rows and at most of_total")
        if self.label != f"top {self.n} of {self.of_total} by ratio":
            raise ValueError("label must state N and M: 'top N of M by ratio'")
        return self


class SummaryChanges(_P):
    """Changes from the previous summary (S5 table)."""

    newly_failing: list[MemberChange]
    newly_passing: list[MemberChange]
    other_changes: list[MemberChange]
    appeared: list[Member]
    disappeared: list[Member]

    @model_validator(mode="after")
    def _check(self) -> Self:
        fail, ok = VerdictStatus.FAIL, VerdictStatus.PASS
        bad = (
            any(c.status is not fail or c.previous_status is fail for c in self.newly_failing),
            any(c.status is not ok or c.previous_status is not fail for c in self.newly_passing),
            any(c.status is c.previous_status for c in self.other_changes),
        )
        names = ("newly_failing", "newly_passing", "other_changes")
        if wrong := [n for n, b in zip(names, bad, strict=True) if b]:
            raise ValueError(f"a row of {wrong[0]} does not fit that list")
        return self


class DesignSummary(CalcPayload):
    """`harness.design_summary/1` (4.9)."""

    status: VerdictStatus
    counts: dict[VerdictStatus, _Count]
    governing: VerdictRow | None
    governing_by_group: list[GroupRow]
    failing: list[VerdictRow]
    failing_members: list[SubjectRef]
    attention: list[VerdictRow]
    top: Top
    not_designed: list[_Str]
    members: list[Member]
    changes: SummaryChanges
    complete: StrictBool

    @model_validator(mode="after")
    def _check(self) -> Self:
        c = self.counts
        if set(c) != set(VerdictStatus):
            raise ValueError("counts needs one entry per status")
        needs = c[VerdictStatus.NEEDS_ENGINEER] + c[VerdictStatus.ERROR]
        if len(self.failing) != c[VerdictStatus.FAIL] or len(self.attention) != needs:
            raise ValueError("counts must match failing and attention")
        if self.top.of_total != sum(c.values()):
            raise ValueError("counts must add up to top.of_total")
        ratios = [r.ratio or 0 for r in self.failing]
        if ratios != sorted(ratios, reverse=True):
            raise ValueError("failing must be sorted by ratio, descending")
        _ordered([(m.subject_kind, m.subject_id, m.check_id) for m in self.members], "members")
        _ordered([(g.subject_kind, g.check_id) for g in self.governing_by_group], "governing_by_group")
        _ordered(self.not_designed, "not_designed")
        _ordered([(s.kind, s.id) for s in self.failing_members], "failing_members")
        if c[VerdictStatus.FAIL]:
            want = VerdictStatus.FAIL
        elif needs or self.not_designed or not self.top.of_total or not self.complete:
            want = VerdictStatus.NEEDS_ENGINEER
        else:
            want = VerdictStatus.PASS
        if self.status is not want:
            raise ValueError(f"status must be {want.value} by rule S6")
        return self


class SectionSize(CalcPayload):
    """`harness.section_size/1` (4.10): the required size rounded up to a multiple of the increment."""

    required: Quantity
    increment: Quantity
    multiple: Annotated[int, Field(ge=1)]
    size: Quantity
    status: Literal[VerdictStatus.PASS]

    @model_validator(mode="after")
    def _check(self) -> Self:
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


Element = Literal["frame", "area"]
_TYPES: dict[str, set[str]] = {
    "frame": {"column", "beam", "brace", "other"},
    "area": {"slab", "wall", "deck", "other"},
}


class CountRow(_P):
    """Element counts of both sides for one element type or story (`unassigned` for no story)."""

    element: Element
    by: Literal["type", "story"]
    name: _Str
    a: _Count
    b: _Count
    difference: int

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.difference != self.b - self.a:
            raise ValueError("difference must be b - a")
        if self.by == "type" and self.name not in _TYPES[self.element]:
            raise ValueError(f"{self.name!r} is not a type of {self.element}")
        return self


class ByIdRow(_P):
    """Comparison of one id present on both sides; `distance_mm` is for display."""

    element: Element
    id: _Str
    result: Literal["same", "reversed", "moved", "reshaped"]
    distance_mm: _Ratio


class Renamed(_P):
    """A pair matched by geometry."""

    element: Element
    a_id: _Str
    b_id: _Str


class Ambiguous(_P):
    """An id with several geometric candidates on the other side."""

    element: Element
    side: Literal["a", "b"]
    id: _Str
    candidates: Annotated[list[_Str], Field(min_length=2)]


class OneSided(_P):
    """An id found on one side only."""

    element: Element
    id: _Str


class PlacementComparison(CalcPayload):
    """`harness.placement_comparison/1` (4.11)."""

    counts: list[CountRow]
    by_id: list[ByIdRow]
    renamed: list[Renamed]
    ambiguous: list[Ambiguous]
    only_in_a: list[OneSided]
    only_in_b: list[OneSided]
    equal: StrictBool
    complete: StrictBool

    @model_validator(mode="after")
    def _check(self) -> Self:
        _ordered([(c.element, c.by, c.name) for c in self.counts], "counts")
        _ordered([(r.element, r.id) for r in self.by_id], "by_id")
        same = (
            all(c.difference == 0 for c in self.counts)
            and all(r.result == "same" for r in self.by_id)
            and not (self.renamed or self.ambiguous or self.only_in_a or self.only_in_b)
        )
        if self.equal != same:
            raise ValueError("equal must follow rule P6")
        return self


CALC_KINDS: dict[str, type[BaseModel]] = {
    "harness.model_fingerprint/1": ModelFingerprint,
    "harness.model_diff/1": ModelDiff,
    "harness.expected_effects/1": ExpectedEffects,
    "harness.readback_check/1": ReadbackCheck,
    "harness.design_summary/1": DesignSummary,
    "harness.section_size/1": SectionSize,
    "harness.placement_comparison/1": PlacementComparison,
}
"""The calc kinds by name, registered in `eng_harness._kinds`."""
