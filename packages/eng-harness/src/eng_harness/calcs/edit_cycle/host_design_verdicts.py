"""Calc `harness.host_design_verdicts` v1: the host's design results as verdicts (spec 0007 4.4.3).

Purpose: map the raw rows of `harness.csi_design_results/1` to host verdicts the design summary reads (spec 0003 4.9).
Method: one verdict per row, in the row order: `source` host, `check_id` `host.<kind>_design_ratio`, `code`
`host_<kind>_design`, `subject` the frame of the row with the row's `combo` as the case (none when the row has no
`combo`, as every concrete row). Steel: the host's `ratio` and the basis `limits.ratio_limit_ratio` as `ratio_limit`;
the status is `PASS` when the ratio is at most the limit, else `FAIL`, compared exactly, never recomputed (contract
4.9.1).
Concrete (gap EC-G2): the host reply holds no single ratio, so every row is `NEEDS_ENGINEER` with no ratio and the
message "host concrete design output not mapped" in the verdict's `assumptions`; the basis limit is its `ratio_limit`.
The column names are those of the S-12 inventory and need the local test (spec 0007 section 12).
Units: a ratio and its limit are dimensionless, as stored; the row's `location` and other columns are not read.
Errors: `ContractError` `INVALID_ARGUMENT` (with `field`) for an input given without a record, a limit that is missing,
unconfirmed, not a number or not above zero, and a row whose `frame`, `combo` or (steel) `ratio` cannot be used.
"""

from collections.abc import Mapping
from fractions import Fraction
from typing import Any, Literal

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.params import eng_param
from eng_contract.trace import Trace
from eng_contract.verdicts import Subject, SubjectKind, Verdict, VerdictSource, VerdictStatus
from pydantic import BaseModel, ConfigDict, ValidationError

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.csi import CsiRows

__all__ = ["BASIS_FIELDS", "NOT_MAPPED", "VerdictsBody", "VerdictsInput", "host_design_verdicts"]

BASIS_FIELDS = ("limits.ratio_limit_ratio",)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""
NOT_MAPPED = "host concrete design output not mapped"
"""The message of a concrete verdict (spec 0007 4.4.3, gap EC-G2)."""
_LIMIT = "limits_ratio_limit_ratio"
_REFS = ("results", "basis")
_SOURCE = "spec 0007 4.4.3"


def _ref(kind: str) -> Any:
    return eng_param(ref_capable=True, ref_kinds={kind}, engineering_quantity=True)


class VerdictsInput(CalcInput):
    """The host's design result rows, the design kind of the call that read them and the basis."""

    results: CsiRows = _ref("harness.csi_design_results/1")
    kind: Literal["steel", "concrete"]
    basis: DesignBasis = _ref("basis.design_basis/1")


class VerdictsBody(BaseModel):
    """The members of `harness.host_design_verdicts/1` without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdicts: list[Verdict]
    traces: list[Trace]
    counts: dict[VerdictStatus, int]


def _refuse(field: str, message: str) -> ContractError:
    return ContractError(ErrorCode.INVALID_ARGUMENT, message, field=field)


def _limit(basis: DesignBasis, basis_id: str, trace: TraceBuilder) -> Fraction:
    """The ratio limit: present, confirmed, a number and above zero, with no default."""
    path = BASIS_FIELDS[0]
    field = basis.fields.get(path)
    where = f"basis.fields.{path}"
    if field is None or not field.confirmed:
        raise _refuse(where, f"basis field {path} is missing or not confirmed")
    if (exact := as_fraction(field.value)) is None:
        raise _refuse(where, f"basis field {path} is not a number")
    if exact <= Fraction():  # Fraction() is zero: contract 4.9.1 asks the limit of a verdict to be above it
        raise _refuse(where, f"basis field {path} must be above zero")
    trace.input(_LIMIT, float(exact), unit=field.unit, ref=f"{basis_id}#/fields/{path}")
    return exact


def _subject(row: Mapping[str, Any], index: int) -> Subject:
    """The frame of the row, the case its `combo` when it has one; the contract's own limits on both names."""
    try:
        return Subject.model_validate({"kind": SubjectKind.FRAME, "id": row.get("frame"), "case": row.get("combo")})
    except ValidationError as error:
        name, what = (
            ("frame", "subject id") if ("id",) in [e["loc"] for e in error.errors()] else ("combo", "case name")
        )
        raise _refuse(
            f"results.rows[{index}].{name}", f"design result row {index}: {name} is not a valid {what}"
        ) from None


def _ratio(row: Mapping[str, Any], index: int) -> Fraction:
    """The host's steel ratio: a finite number of at least zero."""
    exact = as_fraction(row.get("ratio"))
    if exact is None or exact < Fraction():
        raise _refuse(
            f"results.rows[{index}].ratio", f"design result row {index}: ratio is not a finite number of at least zero"
        )
    return exact


def _verdict(kind: str, row: Mapping[str, Any], index: int, limit: Fraction) -> Verdict:
    """The verdict of one row: the contract's comparison for steel, `NEEDS_ENGINEER` for concrete (gap EC-G2)."""
    common: dict[str, Any] = {
        "source": VerdictSource.HOST,
        "check_id": f"host.{kind}_design_ratio",
        "code": f"host_{kind}_design",
        "subject": _subject(row, index),
        "ratio_limit": float(limit),
    }
    if kind == "concrete":
        return Verdict(**common, status=VerdictStatus.NEEDS_ENGINEER, assumptions=[NOT_MAPPED])
    ratio = _ratio(row, index)
    return Verdict(**common, ratio=float(ratio), status=VerdictStatus.PASS if ratio <= limit else VerdictStatus.FAIL)


@calc(
    id="harness.host_design_verdicts",
    version=1,
    output_kind="harness.host_design_verdicts/1",
    title="Host design results as verdicts",
    method_source="eng-harness spec 0007 §4.4.3; 18 §4 step 14",
    verification="draft",
)
def host_design_verdicts(inp: VerdictsInput, meta: InputMeta, trace: TraceBuilder) -> VerdictsBody:
    """Map each design row to a host verdict: steel by comparison with the limit, concrete as not mapped."""
    refs: dict[str, str] = {}
    for name in _REFS:
        if (ref := meta.refs.get(name)) is None:
            raise _refuse(name, "each input must be a record reference")
        refs[name] = ref.result_id
    limit = _limit(inp.basis, refs["basis"], trace)
    rows = inp.results.rows
    trace.input("rows", len(rows), ref=f"{refs['results']}#/rows")
    verdicts = [_verdict(inp.kind, row, index, limit) for index, row in enumerate(rows)]
    counted = {status: [v.status for v in verdicts].count(status) for status in VerdictStatus}
    trace.step("verdict_count", len(verdicts), formula="one verdict per host design row", source=_SOURCE, uses=["rows"])
    trace.step(
        "fail_verdicts",
        counted[VerdictStatus.FAIL],
        formula="steel rows with a ratio above the limit",
        source=_SOURCE,
        uses=["rows", _LIMIT],
    )
    trace.step(
        "needs_engineer_verdicts",
        counted[VerdictStatus.NEEDS_ENGINEER],
        formula="concrete rows: host design output not mapped (gap EC-G2)",
        source=_SOURCE,
        uses=["rows"],
    )
    trace.output("verdict_count")
    return VerdictsBody(verdicts=verdicts, traces=[], counts=counted)
