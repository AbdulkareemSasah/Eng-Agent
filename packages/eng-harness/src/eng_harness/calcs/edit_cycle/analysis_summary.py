"""Calc `harness.analysis_summary` v1: the analysis messages and story drifts of one cycle (spec 0007 4.4.4).

Purpose: count the host's analysis messages by severity, give the governing drift of each direction and the stories
above the drift limit, and a status for the analysis-messages decision (D-3).
Method: the severity column of the `Analysis Messages` table is not known from the sources (gap EC-G3), so every message
is `unclassified` and no column is read. One row per direction, story and case holds the highest ratio of its points.
The governing drift of a direction is its highest row, a tie going to the first by story then case; a row exceeds the
limit when its ratio is above it, compared exactly. Both are by ordering only, nothing is computed.
Status: `FAIL` on an error message, else `NEEDS_ENGINEER` on an unclassified message or a row above the limit,
else `PASS`.
Units: a drift ratio and its limit are dimensionless, as stored. The case is named by its case name; its type and step
are not part of the key.
Errors: `ContractError` `INVALID_ARGUMENT` (with `field`) for an input given without a record and for a limit that is
missing, unconfirmed or not a number.
"""

from collections.abc import Mapping
from fractions import Fraction
from typing import Any, Literal

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.forces import StoryDrifts
from eng_contract.params import eng_param
from eng_contract.refs import RefString
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.csi import CsiRows
from eng_harness.kinds.edit_cycle import Exceeding, Governing, SeverityCounts

__all__ = ["BASIS_FIELDS", "SEVERITIES", "SummaryBody", "SummaryInput", "analysis_summary"]

BASIS_FIELDS = ("limits.drift_ratio",)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""
SEVERITIES = ("error", "warning", "info", "unclassified")
"""The severities of an analysis message, in the order of the counts."""
_LIMIT = "limits_drift_ratio"
_REFS = ("messages", "drifts", "basis")

Severity = Literal["error", "warning", "info", "unclassified"]


def _ref(kind: str) -> Any:
    return eng_param(ref_capable=True, ref_kinds={kind}, engineering_quantity=True)


class SummaryInput(CalcInput):
    """The host's analysis messages, the story drifts and the basis."""

    messages: CsiRows = _ref("harness.csi_analysis_messages/1")
    drifts: StoryDrifts = _ref("forces.story_drifts/1")
    basis: DesignBasis = _ref("basis.design_basis/1")


class SummaryBody(BaseModel):
    """The payload of `harness.analysis_summary/1` without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["PASS", "NEEDS_ENGINEER", "FAIL"]
    counts: SeverityCounts
    has_errors: bool
    has_unclassified: bool
    limit_ratio: float
    limit_ref: RefString
    governing_drift: dict[str, Governing]
    exceeding: list[Exceeding]


def _severity(row: Mapping[str, Any]) -> Severity:
    """The severity of one message row: gap EC-G3, the column is unconfirmed, so no row is classified."""
    del row
    return "unclassified"


def _limit(basis: DesignBasis, basis_id: str, trace: TraceBuilder) -> Fraction:
    """The drift limit: present, confirmed and a number, with no default."""
    path = BASIS_FIELDS[0]
    field = basis.fields.get(path)
    if field is None or not field.confirmed:
        raise _refuse(f"basis.fields.{path}", f"basis field {path} is missing or not confirmed")
    if (exact := as_fraction(field.value)) is None:
        raise _refuse(f"basis.fields.{path}", f"basis field {path} is not a number")
    trace.input(_LIMIT, float(exact), unit=field.unit, ref=f"{basis_id}#/fields/{path}")
    return exact


def _refuse(field: str, message: str) -> ContractError:
    return ContractError(ErrorCode.INVALID_ARGUMENT, message, field=field)


@calc(
    id="harness.analysis_summary",
    version=1,
    output_kind="harness.analysis_summary/1",
    title="Analysis messages and story drifts of one cycle",
    method_source="eng-harness spec 0007 §4.4.4; 18 §4 step 14",
    verification="draft",
)
def analysis_summary(inp: SummaryInput, meta: InputMeta, trace: TraceBuilder) -> SummaryBody:
    """Count the messages, find the governing drift of each direction and the rows above the limit."""
    refs: dict[str, str] = {}
    for name in _REFS:
        if (ref := meta.refs.get(name)) is None:
            raise _refuse(name, "each input must be a record reference")
        refs[name] = ref.result_id
    limit = _limit(inp.basis, refs["basis"], trace)
    trace.input("messages", len(inp.messages.rows), ref=f"{refs['messages']}#/rows")
    trace.input("drifts", len(inp.drifts.rows), ref=f"{refs['drifts']}#/rows")
    found: list[str] = [_severity(row) for row in inp.messages.rows]
    counted = {name: found.count(name) for name in SEVERITIES}
    for name in SEVERITIES:
        trace.step(
            f"{name}_messages",
            counted[name],
            formula=f"messages of severity {name}",
            source="spec 0007 4.4.4 EC-G3",
            uses=["messages"],
        )
    highest: dict[tuple[str, str, str], float] = {}
    for row in inp.drifts.rows:
        key = (row.direction, row.story, row.case.case)
        highest[key] = max(highest.get(key, row.drift_ratio), row.drift_ratio)
    rows = [Exceeding(direction=d, story=s, case=c, ratio=r) for (d, s, c), r in sorted(highest.items())]
    governing: dict[str, Governing] = {}
    for direction in sorted({row.direction for row in rows}):
        top = max((row for row in rows if row.direction == direction), key=lambda row: row.ratio)
        governing[direction] = Governing(story=top.story, case=top.case, ratio=top.ratio)
    trace.step(
        "governing_directions",
        len(governing),
        formula="highest drift ratio per direction, first on a tie",
        source="spec 0007 4.4.4",
        uses=["drifts"],
    )
    exceeding = [row for row in rows if Fraction(row.ratio) > limit]
    trace.step(
        "exceeding_rows",
        len(exceeding),
        formula="rows with drift ratio above the limit",
        source="spec 0007 4.4.4",
        uses=["drifts", _LIMIT],
    )
    status: Literal["PASS", "NEEDS_ENGINEER", "FAIL"] = "PASS"
    if counted["error"]:
        status = "FAIL"
    elif counted["unclassified"] or exceeding:
        status = "NEEDS_ENGINEER"
    trace.step(
        "status",
        status,
        formula="FAIL on an error message; else NEEDS_ENGINEER on an unclassified message or a row over the limit",
        source="spec 0007 4.4.4",
        uses=["error_messages", "unclassified_messages", "exceeding_rows"],
    )
    trace.output("status")
    return SummaryBody(
        status=status,
        counts=SeverityCounts(**counted),
        has_errors=bool(counted["error"]),
        has_unclassified=bool(counted["unclassified"]),
        limit_ratio=float(limit),
        limit_ref=f"{refs['basis']}#/fields/{BASIS_FIELDS[0]}",
        governing_drift=governing,
        exceeding=exceeding,
    )
