"""Calc `harness.column_review` v1: member statuses, governing references and cycle changes (spec 0013 4.4.3, R1 to R4).

Purpose: combine host design verdicts (`harness.host_design_verdicts/1`) and the three optional code-check verdict
sets (`verdicts.set/1`) for the selected columns, apply `items.not_checked`, pick each column's governing verdict by
reference without recomputing any ratio, build the complete `(frame_id, source, check_id)` member snapshot, and
compare against `previous.members` per spec 0003 section 4.9 S5.
Units: dimensionless ratios copied from the referenced verdicts; `station_mm` in mm.
Errors: `ContractError` `INVALID_ARGUMENT` (with `field`) for a non-reference input, duplicate selected `frame_id`,
mismatched verdict source or check id, or `report.top_n` missing, unconfirmed, with a unit or not an integer >= 1.
"""

from typing import Annotated, Any

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.params import eng_param
from eng_contract.verdicts import SubjectKind, Verdict, VerdictSource, VerdictStatus
from pydantic import BaseModel, ConfigDict, PositiveInt, Strict, StrictBool, TypeAdapter, ValidationError

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs.design_summary import SEVERITY, order_key
from eng_harness.kinds.calcs import Top, VerdictRow
from eng_harness.kinds.column_design import (
    ColumnCheckItems,
    ColumnGoverning,
    ColumnMember,
    ColumnMemberChange,
    ColumnReview,
    ColumnReviewChanges,
    ColumnReviewRow,
    ColumnSelection,
)
from eng_harness.kinds.edit_cycle import HostDesignVerdicts, Label

__all__ = ["BASIS_FIELDS", "CODE_CHECKS", "ReviewBody", "ReviewInput", "column_review"]

TOP_N = "report.top_n"
BASIS_FIELDS = (TOP_N,)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""
CODE_CHECKS = (
    ("max_axial_strength", "aci318_14.22_4_2_1.max_axial_strength"),
    ("axial_flexure_uniaxial", "aci318_14.22_4_1_1.axial_flexure_uniaxial"),
    ("longitudinal_reinforcement_limits", "aci318_14.10_6_1_1.longitudinal_reinforcement_limits"),
)
"""Optional code-check verdict-set fields and their expected check ids (spec 0013 4.4.3, 4.5)."""
FAIL, NEEDS, PASS, NOT_APP = (
    VerdictStatus.FAIL,
    VerdictStatus.NEEDS_ENGINEER,
    VerdictStatus.PASS,
    VerdictStatus.NOT_APPLICABLE,
)
_TOP_N = TypeAdapter(Annotated[PositiveInt, Strict()])
_MemberKey = tuple[str, str, str]
_RULE = "spec 0013 4.4.3"


def _ref(kind: str) -> Any:
    return eng_param(ref_capable=True, ref_kinds={kind}, engineering_quantity=True)


def _optional(kind: str) -> Any:
    return eng_param(None, ref_capable=True, ref_kinds={kind}, engineering_quantity=True)


class ReviewInput(CalcInput):
    """Selection, host verdicts, the three optional code-check verdict sets, check items, previous review and basis."""

    selection: ColumnSelection = _ref("harness.column_selection/1")
    host: HostDesignVerdicts = _ref("harness.host_design_verdicts/1")
    max_axial_strength: VerdictSet | None = _optional("verdicts.set/1")
    axial_flexure_uniaxial: VerdictSet | None = _optional("verdicts.set/1")
    longitudinal_reinforcement_limits: VerdictSet | None = _optional("verdicts.set/1")
    items: ColumnCheckItems = _ref("harness.column_check_items/1")
    previous: ColumnReview | None = _optional("harness.column_review/1")
    basis: DesignBasis = _ref("basis.design_basis/1")


class ReviewBody(BaseModel):
    """The payload of `harness.column_review/1` without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    columns: list[ColumnReviewRow]
    failing: list[Label]
    attention: list[Label]
    top: Top
    members: list[ColumnMember]
    changes: ColumnReviewChanges
    complete: StrictBool


def _refuse_basis(why: str) -> ContractError:
    return ContractError(
        ErrorCode.INVALID_ARGUMENT,
        f"basis field {TOP_N} {why}",
        field=f"basis.fields.{TOP_N}",
        hint=f"set and confirm {TOP_N} in the design basis",
    )


def _read_top_n(basis: DesignBasis, basis_id: str, trace: TraceBuilder) -> int:
    """Spec 0003 4.4: `report.top_n` present, confirmed, without a unit and an integer >= 1."""
    field = basis.fields.get(TOP_N)
    if field is None:
        raise _refuse_basis("is missing (no default)")
    if not field.confirmed:
        raise _refuse_basis("is not confirmed")
    if field.unit is not None:
        raise _refuse_basis(f"must have no unit, not {field.unit}")
    try:
        top_n = _TOP_N.validate_python(field.value)
    except ValidationError:
        raise _refuse_basis("must be an integer >= 1") from None
    trace.input("report_top_n", top_n, ref=f"{basis_id}#/fields/{TOP_N}")
    return top_n


def _require_refs(inp: ReviewInput, meta: InputMeta) -> dict[str, str]:
    """Ensure every provided input has a record reference and return its `result_id`."""
    required = ("selection", "host", "items", "basis")
    optional = ("max_axial_strength", "axial_flexure_uniaxial", "longitudinal_reinforcement_limits", "previous")
    refs: dict[str, str] = {}
    for name in (*required, *(n for n in optional if getattr(inp, n) is not None)):
        ref = meta.refs.get(name)
        if ref is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{name} must be a record reference", field=name)
        refs[name] = ref.result_id
    return refs


def _row(verdict: Verdict) -> VerdictRow:
    s, fields = verdict.subject, verdict.model_dump(include={"check_id", "ratio", "ratio_limit", "status"})
    return VerdictRow(subject_kind=s.kind, subject_id=s.id, case=s.case, station_mm=s.station_mm, **fields)


def _member_key(member: ColumnMember) -> _MemberKey:
    return member.frame_id, member.source.value, member.check_id


def _collect_verdicts(inp: ReviewInput, refs: dict[str, str], selected_ids: set[str]) -> list[tuple[Verdict, str, int]]:
    """R1: validate verdict sources/check ids and keep only verdicts on selected `(frame, id)` columns."""
    kept: list[tuple[Verdict, str, int]] = []
    for index, verdict in enumerate(inp.host.verdicts):
        if verdict.source is not VerdictSource.HOST:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"host verdict {index} must have source host", field="host")
        if verdict.subject.kind is SubjectKind.FRAME and verdict.subject.id in selected_ids:
            kept.append((verdict, refs["host"], index))
    for field_name, check_id in CODE_CHECKS:
        vset: VerdictSet | None = getattr(inp, field_name)
        if vset is None:
            continue
        for index, verdict in enumerate(vset.verdicts):
            if verdict.source is not VerdictSource.CODE_PACK or verdict.check_id != check_id:
                raise ContractError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"{field_name} verdict {index} must be code_pack for {check_id}",
                    field=field_name,
                )
            if verdict.subject.kind is SubjectKind.FRAME and verdict.subject.id in selected_ids:
                kept.append((verdict, refs[field_name], index))
    return kept


def _build_members(ordered: list[tuple[Verdict, str, int]]) -> list[ColumnMember]:
    """R2 and 0003 S5: aggregate verdicts by `(frame_id, source, check_id)` in sorted key order."""
    groups: dict[_MemberKey, list[Verdict]] = {}
    for verdict, _, _ in ordered:
        key = (verdict.subject.id, verdict.source.value, verdict.check_id)
        groups.setdefault(key, []).append(verdict)
    members: list[ColumnMember] = []
    for frame_id, source_val, check_id in sorted(groups):
        group = groups[frame_id, source_val, check_id]
        members.append(
            ColumnMember(
                frame_id=frame_id,
                source=VerdictSource(source_val),
                check_id=check_id,
                status=min((v.status for v in group), key=SEVERITY.index),
                ratio=max((v.ratio for v in group if v.ratio is not None), default=None),
            )
        )
    return members


def _compare_members(current: list[ColumnMember], previous: list[ColumnMember]) -> ColumnReviewChanges:
    """R4 and 0003 S5 table: status changes on both sides, and appeared/disappeared members."""
    now, old = {_member_key(m): m for m in current}, {_member_key(m): m for m in previous}
    newly_failing: list[ColumnMemberChange] = []
    newly_passing: list[ColumnMemberChange] = []
    other_changes: list[ColumnMemberChange] = []
    for key in sorted(now.keys() & old.keys()):
        before, after = old[key], now[key]
        if before.status is after.status:
            continue
        change = ColumnMemberChange(
            frame_id=after.frame_id,
            source=after.source,
            check_id=after.check_id,
            previous_status=before.status,
            status=after.status,
            previous_ratio=before.ratio,
            ratio=after.ratio,
        )
        if after.status is FAIL:
            newly_failing.append(change)
        elif (before.status, after.status) == (FAIL, PASS):
            newly_passing.append(change)
        else:
            other_changes.append(change)
    appeared = [now[key] for key in sorted(now.keys() - old.keys())]
    disappeared = [old[key] for key in sorted(old.keys() - now.keys())]
    return ColumnReviewChanges(
        newly_failing=newly_failing,
        newly_passing=newly_passing,
        other_changes=other_changes,
        appeared=appeared,
        disappeared=disappeared,
    )


def _worst(statuses: list[VerdictStatus]) -> VerdictStatus:
    return min(statuses, key=SEVERITY.index) if statuses else NOT_APP


@calc(
    id="harness.column_review",
    version=1,
    output_kind="harness.column_review/1",
    title="Column review: host and code verdicts, governing references and changes",
    method_source="eng-harness spec 0013 §4.4.3 (R1 to R4); eng-harness spec 0003 §4.9 (S2, S5)",
    verification="draft",
)
def column_review(inp: ReviewInput, meta: InputMeta, trace: TraceBuilder) -> ReviewBody:
    """Summarize host and code verdicts for selected columns (R1 to R4).

    Raises:
        ContractError: see the module docstring.
    """
    refs = _require_refs(inp, meta)
    selected_cols = sorted(inp.selection.columns, key=lambda col: col.frame_id)
    selected_ids = {col.frame_id for col in selected_cols}
    if len(selected_ids) != len(selected_cols):
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "selection contains duplicate frame_id", field="selection")
    top_n = _read_top_n(inp.basis, refs["basis"], trace)
    trace.input("selection", len(selected_cols), ref=refs["selection"])
    trace.input("host_verdicts", len(inp.host.verdicts), ref=refs["host"])
    verdict_uses = ["selection", "host_verdicts"]
    for field_name, _ in CODE_CHECKS:
        vset: VerdictSet | None = getattr(inp, field_name)
        if vset is not None:
            trace.input(field_name, len(vset.verdicts), ref=refs[field_name])
            verdict_uses.append(field_name)
    trace.input("not_checked", len(inp.items.not_checked), ref=refs["items"])
    if inp.previous is not None:
        trace.input("previous_members", len(inp.previous.members), ref=refs["previous"])

    ordered = sorted(
        _collect_verdicts(inp, refs, selected_ids),
        key=lambda item: (order_key(item[0]), item[1], item[2]),
    )
    verdict_rows = [_row(verdict) for verdict, _, _ in ordered]
    top_rows = verdict_rows[:top_n]
    members = _build_members(ordered)
    columns: list[ColumnReviewRow] = []
    for col in selected_cols:
        fid = col.frame_id
        col_members = [m for m in members if m.frame_id == fid]
        host_status = _worst([m.status for m in col_members if m.source is VerdictSource.HOST])
        code_status = _worst([m.status for m in col_members if m.source is VerdictSource.CODE_PACK])
        col_misses = [miss for miss in inp.items.not_checked if miss.frame_id == fid]
        not_checked: list[str] = sorted({str(miss.code) for miss in col_misses})
        gaps = sorted({miss.gap for miss in col_misses if miss.gap is not None})
        status = NEEDS if (not_checked or not col_members) else _worst([m.status for m in col_members])
        gov_entry = next(
            ((v, rid, idx) for v, rid, idx in ordered if v.subject.id == fid and v.ratio is not None),
            None,
        )
        governing = (
            ColumnGoverning(ref=f"{gov_entry[1]}#/verdicts/{gov_entry[2]}", ratio=gov_entry[0].ratio)
            if gov_entry is not None
            else None
        )
        columns.append(
            ColumnReviewRow(
                frame_id=fid,
                status=status,
                host_status=host_status,
                code_status=code_status,
                governing=governing,
                not_checked=not_checked,
                gaps=gaps,
            )
        )
    failing = [row.frame_id for row in columns if row.status is FAIL]
    attention = [row.frame_id for row in columns if row.status in (NEEDS, VerdictStatus.ERROR)]
    changes = (
        _compare_members(members, inp.previous.members)
        if inp.previous is not None
        else ColumnReviewChanges(newly_failing=[], newly_passing=[], other_changes=[], appeared=[], disappeared=[])
    )
    complete = all(ref.complete for ref in meta.refs.values())
    change_count = (
        len(changes.newly_failing)
        + len(changes.newly_passing)
        + len(changes.other_changes)
        + len(changes.appeared)
        + len(changes.disappeared)
    )
    trace.step(
        "selected_verdicts",
        len(verdict_rows),
        formula="verdicts whose subject is (frame, id) in selection",
        source=f"{_RULE} R1",
        uses=verdict_uses,
    )
    trace.step(
        "member_count",
        len(members),
        formula="distinct (frame_id, source, check_id) members",
        source=f"{_RULE} R2",
        uses=["selected_verdicts"],
    )
    trace.step(
        "failing_columns",
        len(failing),
        formula="selected columns with status FAIL",
        source=f"{_RULE} R2",
        uses=["member_count", "not_checked"],
    )
    trace.step(
        "attention_columns",
        len(attention),
        formula="selected columns with status NEEDS_ENGINEER or ERROR",
        source=f"{_RULE} R2",
        uses=["member_count", "not_checked"],
    )
    trace.step(
        "top_rows",
        len(top_rows),
        formula="first report.top_n selected verdicts by S2 order",
        source=f"{_RULE} R3",
        uses=["report_top_n", "selected_verdicts"],
    )
    trace.step(
        "change_count",
        change_count,
        formula="member status changes and appeared/disappeared members vs previous",
        source=f"{_RULE} R4",
        uses=["member_count", *(["previous_members"] if inp.previous is not None else [])],
    )
    trace.output("failing_columns", "attention_columns", "top_rows")
    return ReviewBody(
        columns=columns,
        failing=failing,
        attention=attention,
        top=Top(
            n=len(top_rows),
            of_total=len(verdict_rows),
            rows=top_rows,
            label=f"top {len(top_rows)} of {len(verdict_rows)} by ratio",
        ),
        members=members,
        changes=changes,
        complete=complete,
    )
