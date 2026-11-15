"""Calc 4, design results summary `harness.design_summary` v1 (spec 0003 4.9, rules S1 to S6).

Purpose: for the engineer turn and the run report (18 §4 step 14), list the governing verdict, every failing verdict
and member, every verdict that needs attention, the top N by ratio, the frames without design results and the member
changes from a previous summary, and give `PASS`, `FAIL` or `NEEDS_ENGINEER`.
Inputs: `verdicts` (`verdicts.set/1`, host verdicts as spec 0002 maps them), optional `frames`
(`model.frame_placements/1`), optional `previous` (`harness.design_summary/1`) and `basis` (`report.top_n`).
Units: ratios have none and `station_mm` is in millimetres; statuses and ratios are taken as the host reported them,
nothing is recomputed or converted and no limit of the summary's own is applied (S1).
Errors: `ContractError` `INVALID_ARGUMENT` (with `field`) for a basis given without a record and for `report.top_n`
missing, unconfirmed, with a unit or not an integer >= 1 (no default).
"""

from fractions import Fraction
from typing import Annotated, Any

from eng_contract.canonical import canonical_json
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import FramePlacements
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.params import eng_param
from eng_contract.verdicts import SubjectKind, Verdict, VerdictStatus
from pydantic import BaseModel, ConfigDict, PositiveInt, Strict, TypeAdapter, ValidationError

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.kinds.calcs import (
    DesignSummary,
    GroupRow,
    Member,
    MemberChange,
    SubjectRef,
    SummaryChanges,
    Top,
    VerdictRow,
)

__all__ = ["BASIS_FIELDS", "SEVERITY", "SummaryBody", "SummaryInput", "compare_members", "design_summary", "order_key"]

TOP_N = "report.top_n"
BASIS_FIELDS = (TOP_N,)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""
FAIL, ERROR, NEEDS, PASS = VerdictStatus.FAIL, VerdictStatus.ERROR, VerdictStatus.NEEDS_ENGINEER, VerdictStatus.PASS
SEVERITY = (FAIL, ERROR, NEEDS, PASS, VerdictStatus.NOT_APPLICABLE)
"""Member status order of S5, worst first."""
STATUS_RULE = "FAIL: any FAIL verdict; else NEEDS_ENGINEER: any reason of S6; else PASS"
_TOP_N = TypeAdapter(Annotated[PositiveInt, Strict()])
Key = tuple[SubjectKind, str, str]


def _ref(kind: str) -> Any:
    return eng_param(ref_capable=True, ref_kinds={kind}, engineering_quantity=True)


def _optional(kind: str) -> Any:
    return eng_param(None, ref_capable=True, ref_kinds={kind}, engineering_quantity=True)


class SummaryInput(CalcInput):
    """The host verdicts, the frames that should have results, the previous summary and the design basis."""

    verdicts: VerdictSet = _ref("verdicts.set/1")
    frames: FramePlacements | None = _optional("model.frame_placements/1")
    previous: DesignSummary | None = _optional("harness.design_summary/1")
    basis: DesignBasis = _ref("basis.design_basis/1")


class SummaryBody(BaseModel):
    """The `harness.design_summary/1` payload without `calc`, `draft` and `trace` (the framework adds them)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: VerdictStatus
    counts: dict[VerdictStatus, int]
    governing: VerdictRow | None
    governing_by_group: list[GroupRow]
    failing: list[VerdictRow]
    failing_members: list[SubjectRef]
    attention: list[VerdictRow]
    top: Top
    not_designed: list[str]
    members: list[Member]
    changes: SummaryChanges
    complete: bool


def order_key(verdict: Verdict) -> tuple[Any, ...]:
    """S2: ratio descending (none last), kind, id, check, station and case ascending (null first), canonical bytes."""
    subject = verdict.subject
    ratio = (True,) if verdict.ratio is None else (False, -Fraction(verdict.ratio))
    station = () if subject.station_mm is None else (Fraction(subject.station_mm),)
    case = () if subject.case is None else (subject.case,)
    tail = (verdict.check_id, station, case, canonical_json(verdict.model_dump(mode="json")))
    return (ratio, subject.kind.value, subject.id, *tail)


def _row(verdict: Verdict) -> VerdictRow:
    s, fields = verdict.subject, verdict.model_dump(include={"check_id", "ratio", "ratio_limit", "status"})
    return VerdictRow(subject_kind=s.kind, subject_id=s.id, case=s.case, station_mm=s.station_mm, **fields)


def _key(row: VerdictRow | Member) -> Key:
    return row.subject_kind, row.subject_id, row.check_id


def _members(rows: list[VerdictRow]) -> list[Member]:
    """S5: per (subject kind, subject id, check id) the worst status and the largest ratio, sorted by the key."""
    groups: dict[Key, list[VerdictRow]] = {}
    for row in rows:
        groups.setdefault(_key(row), []).append(row)
    return [
        Member(
            subject_kind=kind,
            subject_id=subject_id,
            check_id=check_id,
            status=min((row.status for row in groups[kind, subject_id, check_id]), key=SEVERITY.index),
            ratio=max((r.ratio for r in groups[kind, subject_id, check_id] if r.ratio is not None), default=None),
        )
        for kind, subject_id, check_id in sorted(groups)
    ]


def compare_members(current: list[Member], previous: list[Member]) -> SummaryChanges:
    """S5 table: status changes of the members on both sides, and the members of one side only."""
    now, old = {_key(m): m for m in current}, {_key(m): m for m in previous}
    lists: dict[str, list[MemberChange]] = {"newly_failing": [], "newly_passing": [], "other_changes": []}
    for key in sorted(now.keys() & old.keys()):
        before, after = old[key], now[key]
        if before.status is after.status:
            continue  # a ratio change alone is not a status change
        if after.status is FAIL:
            name = "newly_failing"
        else:
            name = "newly_passing" if (before.status, after.status) == (FAIL, PASS) else "other_changes"
        lists[name].append(
            MemberChange(**after.model_dump(), previous_status=before.status, previous_ratio=before.ratio)
        )
    appeared = [now[key] for key in sorted(now.keys() - old.keys())]
    return SummaryChanges(**lists, appeared=appeared, disappeared=[old[key] for key in sorted(old.keys() - now.keys())])


def _refuse(why: str) -> ContractError:
    return ContractError(
        ErrorCode.INVALID_ARGUMENT,
        f"basis field {TOP_N} {why}",
        field=f"basis.fields.{TOP_N}",
        hint=f"set and confirm {TOP_N} in the design basis",
    )


def _read_top_n(basis: DesignBasis, basis_id: str, trace: TraceBuilder) -> int:
    """Spec 4.4: `report.top_n` present, confirmed, without a unit and an integer >= 1."""
    field = basis.fields.get(TOP_N)
    if field is None:
        raise _refuse("is missing (no default)")
    if not field.confirmed:
        raise _refuse("is not confirmed")
    if field.unit is not None:
        raise _refuse(f"must have no unit, not {field.unit}")
    try:
        top_n = _TOP_N.validate_python(field.value)
    except ValidationError:
        raise _refuse("must be an integer >= 1") from None
    trace.input("report_top_n", top_n, ref=f"{basis_id}#/fields/{TOP_N}")
    return top_n


@calc(
    id="harness.design_summary",
    version=1,
    output_kind="harness.design_summary/1",
    title="Design results summary of the host verdicts",
    method_source="eng-harness spec 0003 §4.9 (S1 to S6); 18 §4 step 14",
    verification="draft",
)
def design_summary(inp: SummaryInput, meta: InputMeta, trace: TraceBuilder) -> SummaryBody:
    """Order the verdicts (S2), select the lists (S3, S4), build and compare the members (S5) and the status (S6)."""
    if (basis := meta.refs.get("basis")) is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "the basis must be a record reference", field="basis")
    top_n = _read_top_n(inp.basis, basis.result_id, trace)
    rows = [_row(verdict) for verdict in sorted(inp.verdicts.verdicts, key=order_key)]
    failing = [row for row in rows if row.status is FAIL]
    attention = [row for row in rows if row.status in (NEEDS, ERROR)]
    groups: dict[tuple[SubjectKind, str], VerdictRow] = {}
    for row in rows:
        if row.ratio is not None:  # S2: a verdict without a ratio never governs
            groups.setdefault((row.subject_kind, row.check_id), row)
    designed = {row.subject_id for row in rows if row.subject_kind is SubjectKind.FRAME}
    frames = inp.frames.frames if inp.frames is not None else []
    not_designed = sorted(frame.id for frame in frames if frame.id not in designed)
    members = _members(rows)
    previous = inp.previous.members if inp.previous is not None else members  # no previous: nothing changed
    complete = all(ref.complete for ref in meta.refs.values())
    top = rows[:top_n]
    both = ["report_top_n", "verdict_count"]
    for name, value, formula, source, uses in (
        ("verdict_count", len(rows), "host verdicts, statuses and ratios as reported", "S1", []),
        ("failing_verdicts", len(failing), "verdicts with status FAIL", "S3", ["verdict_count"]),
        ("attention_verdicts", len(attention), "verdicts with status NEEDS_ENGINEER or ERROR", "S3", ["verdict_count"]),
        ("top_rows", len(top), "the first report.top_n verdicts by S2, at most all", "S3", both),
        ("not_designed_frames", len(not_designed), "frames without a verdict on (frame, id)", "S4", []),
        ("member_count", len(members), "distinct (subject kind, subject id, check id)", "S5", ["verdict_count"]),
    ):
        trace.step(name, value, formula=formula, source=f"§4.9 {source}", uses=uses)
    reasons = [
        text
        for text, holds in (
            ("FAIL verdicts", failing),
            ("NEEDS_ENGINEER or ERROR verdicts", attention),
            ("frames without design results", not_designed),
            ("no design results", not rows),
            ("incomplete input", not complete),
        )
        if holds
    ]
    status = FAIL if failing else NEEDS if reasons else PASS
    counted = ["failing_verdicts", "attention_verdicts", "not_designed_frames", "verdict_count"]
    message = "; ".join(reasons) or "none"
    trace.step("status_reasons", message, formula="the reasons of S6 that hold", source="§4.9 S6", uses=counted)
    trace.step("status", status.value, formula=STATUS_RULE, source="§4.9 S6", uses=["status_reasons"])
    trace.output("status")
    return SummaryBody(
        status=status,
        counts={each: [row.status for row in rows].count(each) for each in VerdictStatus},
        governing=next((row for row in rows if row.ratio is not None), None),
        governing_by_group=[GroupRow(subject_kind=k, check_id=c, row=groups[k, c]) for k, c in sorted(groups)],
        failing=failing,
        failing_members=[
            SubjectRef(kind=k.value, id=i) for k, i in sorted({(r.subject_kind, r.subject_id) for r in failing})
        ],
        attention=attention,
        top=Top(n=len(top), of_total=len(rows), rows=top, label=f"top {len(top)} of {len(rows)} by ratio"),
        not_designed=not_designed,
        members=members,
        changes=compare_members(members, previous),
        complete=complete,
    )
