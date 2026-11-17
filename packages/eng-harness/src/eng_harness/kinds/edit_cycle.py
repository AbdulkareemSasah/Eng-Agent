"""Payload models of the edit-cycle kinds (spec 0007 section 4.2, 4.4.1, 4.4.3, 4.4.4, 4.10).

Purpose: the stored form of `harness.change_set_check/1`, `harness.host_design_verdicts/1`,
`harness.analysis_summary/1` and `harness.csi_name_lists/1`, with the rules a reader may rely on (status follows issues
and counts, lists sorted, values only by reference, the verdict set's rules for the host design verdicts).
Units: drift ratios are dimensionless; resolved values name their unit.
Errors: `pydantic.ValidationError` for every violated rule.
"""

from collections.abc import Iterable
from typing import Annotated, Any, Literal, Self

from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.refs import RefString
from eng_contract.trace import Trace
from eng_contract.verdicts import Verdict, VerdictStatus
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

from eng_harness.kinds.calcs import CalcPayload

__all__ = [
    "EDIT_CYCLE_KINDS",
    "LABEL_MAX",
    "NONEMPTY",
    "AnalysisSummary",
    "ChangeSetCheck",
    "CsiNameLists",
    "HostDesignVerdicts",
    "Label",
]

NONEMPTY = 1
"""Minimum length of a list that may not be empty."""
LABEL_MAX = 200
"""Maximum length of a name or short text (spec 0007 section 5)."""

Label = Annotated[str, StringConstraints(min_length=NONEMPTY, max_length=LABEL_MAX)]
"""A name or short text: 1 to `LABEL_MAX` characters."""
_Str = Label
_Ptr = Annotated[str, StringConstraints(pattern=r"^(/([^~/]|~[01])*)*$")]
_Count = Annotated[int, Field(ge=0)]
_Code = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z_]*$")]


class _P(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


def _ordered(items: Iterable[Any], what: str) -> None:
    keys = list(items)
    if keys != sorted(set(keys)):
        raise ValueError(f"{what} must be sorted and unique")


class ResolvedValue(_P):
    """A value of a resolved item: where it goes, and the reference to its source (never the number)."""

    pointer: _Ptr
    ref: RefString
    unit: _Str


class ResolvedItem(_P):
    """One change-set item with its explicit targets sorted by code point."""

    item_id: _Str
    kind: _Str
    targets: list[_Str]
    values: list[ResolvedValue]

    @model_validator(mode="after")
    def _sorted(self) -> Self:
        _ordered(self.targets, "targets")
        return self


class Issue(_P):
    """One finding of the check; `gap` is set exactly for `NOT_IMPLEMENTED`."""

    item_id: _Str
    severity: Literal["error", "warning"]
    code: _Code
    detail: Annotated[str, StringConstraints(max_length=500)]
    gap: _Str | None = None

    @model_validator(mode="after")
    def _gap(self) -> Self:
        if (self.code == "NOT_IMPLEMENTED") != (self.gap is not None):
            raise ValueError("gap is set exactly for NOT_IMPLEMENTED")
        return self


class ChangeSetCheck(CalcPayload):
    """`harness.change_set_check/1` (spec 0007 4.4.1): `FAIL` exactly when an issue is an error (rule K7)."""

    status: Literal["PASS", "FAIL"]
    resolved: list[ResolvedItem]
    issues: list[Issue]
    complete: StrictBool

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [r.item_id for r in self.resolved]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate item_id in resolved")
        failed = any(i.severity == "error" for i in self.issues)
        if (self.status == "FAIL") != failed:
            raise ValueError("status is FAIL exactly when an issue is an error")
        return self


class SeverityCounts(_P):
    """Messages by the severity the host reports."""

    error: _Count
    warning: _Count
    info: _Count
    unclassified: _Count


class Governing(_P):
    """The governing drift of one direction."""

    story: _Str
    case: _Str
    ratio: Annotated[float, Field(ge=0)]


class Exceeding(Governing):
    """A story whose drift ratio exceeds the limit, in one direction."""

    direction: _Str


class AnalysisSummary(CalcPayload):
    """`harness.analysis_summary/1` (spec 0007 4.4.4)."""

    status: Literal["PASS", "NEEDS_ENGINEER", "FAIL"]
    counts: SeverityCounts
    has_errors: StrictBool
    has_unclassified: StrictBool
    limit_ratio: Annotated[float, Field(ge=0)]
    limit_ref: RefString
    governing_drift: dict[_Str, Governing]
    exceeding: list[Exceeding]

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.has_errors != (self.counts.error > 0):
            raise ValueError("has_errors must match the error count")
        if self.has_unclassified != (self.counts.unclassified > 0):
            raise ValueError("has_unclassified must match the unclassified count")
        _ordered([(e.direction, e.story, e.case) for e in self.exceeding], "exceeding")
        if any(e.ratio <= self.limit_ratio for e in self.exceeding):
            raise ValueError("an exceeding row must be above the limit")
        want = "FAIL" if self.has_errors else "NEEDS_ENGINEER" if self.has_unclassified or self.exceeding else "PASS"
        if self.status != want:
            raise ValueError(f"status must be {want} for these counts and rows")
        return self


class HostDesignVerdicts(CalcPayload):
    """`harness.host_design_verdicts/1` (spec 0007 4.4.3): the members of `verdicts.set/1` and the calc port's three.

    The rules of the verdict set (trace references, counts) are those of `VerdictSet`, which this model validates.
    """

    verdicts: list[Verdict]
    traces: list[Trace]
    counts: dict[VerdictStatus, int]

    @model_validator(mode="after")
    def _verdict_set_rules(self) -> Self:
        VerdictSet.model_validate(
            {"verdicts": self.verdicts, "traces": self.traces, "counts": self.counts, "draft": self.draft}
        )
        return self


class CsiNameLists(_P):
    """`harness.csi_name_lists/1` (spec 0007 4.10): the names of the model, each list sorted and unique."""

    frame_sections: list[_Str]
    area_sections: list[_Str]
    materials: list[_Str]
    patterns: list[_Str]
    combinations: list[_Str]

    @model_validator(mode="after")
    def _sorted(self) -> Self:
        for what in ("frame_sections", "area_sections", "materials", "patterns", "combinations"):
            _ordered(getattr(self, what), what)
        return self


EDIT_CYCLE_KINDS: dict[str, type[BaseModel]] = {
    "harness.change_set_check/1": ChangeSetCheck,
    "harness.analysis_summary/1": AnalysisSummary,
    "harness.host_design_verdicts/1": HostDesignVerdicts,
    "harness.csi_name_lists/1": CsiNameLists,
}
"""The edit-cycle kinds by registered name."""
