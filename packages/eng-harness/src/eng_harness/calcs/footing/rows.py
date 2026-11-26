"""Copy selected rows from two same-kind footing records (spec 0010 §4.4.7)."""

import json

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import CalcDef, CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.kinds.footing import (
    DesignRow,
    DimRow,
    Excluded,
    FootingDesign,
    FootingDims,
    FootingStatus,
    FootingSubjects,
    StatusRow,
    Subject,
)

VERSION = Cited(value=1, unit="1", source="Calc version 1 of spec 0010 §4.4.7")
_METHOD = "eng-harness spec 0010 §4.4.7"
_DIMS = "harness.footing_dims/1"
_DESIGN = "harness.footing_design/1"
_STATUS = "harness.footing_status/1"
_SUBJECTS = "harness.footing_subjects/1"


class _RowsInput(CalcInput):
    ids: list[str]


class _DimsInput(_RowsInput):
    base: FootingDims = eng_param(ref_capable=True, ref_kinds={_DIMS}, engineering_quantity=True)
    extra: FootingDims = eng_param(ref_capable=True, ref_kinds={_DIMS}, engineering_quantity=True)


class _DesignInput(_RowsInput):
    base: FootingDesign = eng_param(ref_capable=True, ref_kinds={_DESIGN}, engineering_quantity=True)
    extra: FootingDesign = eng_param(ref_capable=True, ref_kinds={_DESIGN}, engineering_quantity=True)


class _StatusInput(_RowsInput):
    base: FootingStatus = eng_param(ref_capable=True, ref_kinds={_STATUS}, engineering_quantity=True)
    extra: FootingStatus = eng_param(ref_capable=True, ref_kinds={_STATUS}, engineering_quantity=True)


class _SubjectsInput(_RowsInput):
    base: FootingSubjects = eng_param(ref_capable=True, ref_kinds={_SUBJECTS}, engineering_quantity=True)
    extra: FootingSubjects = eng_param(ref_capable=True, ref_kinds={_SUBJECTS}, engineering_quantity=True)


class _FootingRows[Row](BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    footings: list[Row]


class _SubjectRows(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    subjects: list[Subject]
    excluded: list[Excluded]


def _select_rows[Row: DimRow | StatusRow | Subject](
    ids: list[str], base: list[Row], extra: list[Row], meta: InputMeta, trace: TraceBuilder
) -> list[Row]:
    """Select unchanged rows by id, recording the source of each selection."""
    base_rows = {row.id: row for row in base}
    extra_rows = {row.id: row for row in extra}
    rows = base_rows | extra_rows
    for footing_id in ids:
        if footing_id not in rows:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"requested footing id {footing_id} is in neither input",
                field="ids",
                received=footing_id,
            )

    selected = sorted(set(ids))
    trace.input("base", list(base_rows), ref=meta.refs["base"].ref)
    trace.input("extra", list(extra_rows), ref=meta.refs["extra"].ref)
    trace.input("ids", list(ids))
    trace.step(
        "selected_rows",
        json.dumps({footing_id: "extra" if footing_id in extra_rows else "base" for footing_id in selected}),
        formula="Keep requested ids in sorted order, using extra where present and base otherwise",
        source=_METHOD,
        uses=("base", "extra", "ids"),
    )
    trace.output("selected_rows")
    return [rows[footing_id] for footing_id in selected]


@calc(
    id="harness.footing_rows_dims",
    version=int(VERSION.value),
    output_kind=_DIMS,
    title="Copy selected footing dimensions",
    method_source=_METHOD,
    verification="draft",
)
def footing_rows_dims(inp: _DimsInput, meta: InputMeta, trace: TraceBuilder) -> _FootingRows[DimRow]:
    """Copy the requested dimension rows."""
    return _FootingRows[DimRow](footings=_select_rows(inp.ids, inp.base.footings, inp.extra.footings, meta, trace))


@calc(
    id="harness.footing_rows_design",
    version=int(VERSION.value),
    output_kind=_DESIGN,
    title="Copy selected footing designs",
    method_source=_METHOD,
    verification="draft",
)
def footing_rows_design(inp: _DesignInput, meta: InputMeta, trace: TraceBuilder) -> _FootingRows[DesignRow]:
    """Copy the requested design rows."""
    return _FootingRows[DesignRow](footings=_select_rows(inp.ids, inp.base.footings, inp.extra.footings, meta, trace))


@calc(
    id="harness.footing_rows_status",
    version=int(VERSION.value),
    output_kind=_STATUS,
    title="Copy selected footing statuses",
    method_source=_METHOD,
    verification="draft",
)
def footing_rows_status(inp: _StatusInput, meta: InputMeta, trace: TraceBuilder) -> _FootingRows[StatusRow]:
    """Copy the requested status rows."""
    return _FootingRows[StatusRow](footings=_select_rows(inp.ids, inp.base.footings, inp.extra.footings, meta, trace))


@calc(
    id="harness.footing_rows_subjects",
    version=int(VERSION.value),
    output_kind=_SUBJECTS,
    title="Copy selected footing subjects",
    method_source=_METHOD,
    verification="draft",
)
def footing_rows_subjects(inp: _SubjectsInput, meta: InputMeta, trace: TraceBuilder) -> _SubjectRows:
    """Copy the requested subject rows and preserve the base exclusions."""
    return _SubjectRows(
        subjects=_select_rows(inp.ids, inp.base.subjects, inp.extra.subjects, meta, trace), excluded=inp.base.excluded
    )


FOOTING_ROW_CALCS: tuple[CalcDef, ...] = (
    footing_rows_dims,
    footing_rows_design,
    footing_rows_status,
    footing_rows_subjects,
)
