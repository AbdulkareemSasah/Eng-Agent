"""Calc `harness.footing_schedule` v1: the assembled footing schedule with the clearance check (spec 0010 4.4.6).

Purpose: join, for each footing of the last design, its design row, family statuses and closure (from the last status),
the reasons it was closed, the verdict sets that judged it, the decisions taken for it and its size source, and mark the
footings whose plans come too close to a neighbour.
Clearance: plans are centred on their joints (the column is centred, BP 2). For two footings,
`gx = |xi - xj| - (Lxi + Lxj)/2` and `gy` likewise with `y` and `Ly`. Both gaps negative is an overlap, which is
always a conflict; one gap negative gives the other as the distance; otherwise the distance is `sqrt(gx^2 + gy^2)`. A
distance below `foundation.min_clear_distance_mm` is a conflict, compared as squares of exact fractions, so a distance
equal to the clear distance is none. Both footings of a conflict are marked: the design status becomes
`NEEDS_ENGINEER` with the reason `CLEARANCE` (a design that already says `NEEDS_ENGINEER` keeps its own reason), the
reasons gain `CLEARANCE`, and the neighbour is named: an overlapping neighbour before one at a distance, then the
smaller distance, then the smaller id.
Reasons of a footing, without repeats and in this order: the reason of its design row, the closure reasons given for
it, `CLEARANCE`. References and decisions keep the order given, without repeats.
Units: lengths in mm; the squares are in mm2 and are not recorded.
Errors: `ContractError` `INVALID_ARGUMENT` (basis field missing, unconfirmed or not a number; a footing of the design
that is no subject, a subject without a design row, a footing without a status row or a status row outside the design,
a closure, verdict-set or decision row that names a footing outside the design), `OUT_OF_RANGE` (basis field below
zero). A basis field in a unit other than mm is refused by the basis kind itself (the unit suffix of its path).
"""

from collections.abc import Iterable, Sequence
from enum import StrEnum
from fractions import Fraction
from itertools import product
from typing import Annotated, Any

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.params import eng_param
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict, StringConstraints

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.kinds.footing import (
    DesignRow,
    FootingDesign,
    FootingStatus,
    FootingSubjects,
    ScheduleRow,
    Subject,
)

BASIS_FIELDS = ("foundation.min_clear_distance_mm",)
"""The basis paths this calc reads (spec 0003 4.4); the workflow declares them required."""
HALVING = Cited(value=2, unit="1", source="Geometry: a plan centred on its joint reaches half its length to each side")
ZERO_DISTANCE = Cited(
    value=0, unit="mm", source="Geometry: zero length; also the lower bound of foundation.min_clear_distance_mm"
)
VERSION = Cited(value=1, unit="1", source="Calc version 1 of spec 0010 4.4.6; a change of method is a new version")
_FIELD = "foundation.min_clear_distance_mm"
_RULE = "spec 0010 4.4.6"


class Reason(StrEnum):
    """The reason this calc adds to a footing (spec 0010 4.4.6)."""

    CLEARANCE = "CLEARANCE"


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Closure(_Row):
    """A reason the block closed a footing (for example `ATTEMPTS_EXHAUSTED`, `COMBINE_REQUESTED`, `LIMIT_REACHED`)."""

    id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class SetRef(_Row):
    """A verdict-set record that judged a footing."""

    id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    result: Annotated[str, StringConstraints(pattern=r"^res_[0-7][0-9A-HJKMNP-TV-Z]{25}$")]


class DecisionRef(_Row):
    """A decision record taken for a footing."""

    id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    decision: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class ScheduleInput(CalcInput):
    """The subjects, last design and last status and the design basis by reference; closures and references as data."""

    subjects: FootingSubjects = eng_param(
        ref_capable=True, ref_kinds={"harness.footing_subjects/1"}, engineering_quantity=True
    )
    design: FootingDesign = eng_param(
        ref_capable=True, ref_kinds={"harness.footing_design/1"}, engineering_quantity=True
    )
    status: FootingStatus = eng_param(
        ref_capable=True, ref_kinds={"harness.footing_status/1"}, engineering_quantity=True
    )
    closures: list[Closure]
    verdict_sets: list[SetRef]
    decisions: list[DecisionRef]
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)


class ScheduleBody(BaseModel):
    """The payload of `harness.footing_schedule/1` without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    footings: list[ScheduleRow]


def _refuse(field: str, received: str, message: str) -> ContractError:
    return ContractError(ErrorCode.INVALID_ARGUMENT, message, field=field, received=received)


def _basis_error(code: ErrorCode, message: str, **fields: Any) -> ContractError:
    return ContractError(code, f"basis field {_FIELD} {message}", field="basis", **fields)


def _clear_distance(basis: DesignBasis) -> int | float:
    """The stored minimum clear distance, after the checks of spec 0003 4.4 (confirmed, mm, >= 0)."""
    field = basis.fields.get(_FIELD)
    if field is None or not field.confirmed:
        raise _basis_error(ErrorCode.INVALID_ARGUMENT, "is missing or not confirmed", hint=f"confirm {_FIELD}")
    value = field.value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _basis_error(ErrorCode.INVALID_ARGUMENT, "is not a number")
    if value < ZERO_DISTANCE.value:
        raise _basis_error(
            ErrorCode.OUT_OF_RANGE, "is below zero", expected={"min": ZERO_DISTANCE.value}, received=value
        )
    return value


def _clearance(one: tuple[Subject, DesignRow], other: tuple[Subject, DesignRow]) -> tuple[bool, Fraction]:
    """Whether two centred plans overlap and, if not, the square of their distance (exact, mm2); 0 for an overlap."""
    zero, half = Fraction(ZERO_DISTANCE.value), Fraction(HALVING.value)
    (a, plan_a), (b, plan_b) = one, other
    gx = abs(Fraction(a.x_mm) - Fraction(b.x_mm)) - (Fraction(plan_a.Lx_mm) + Fraction(plan_b.Lx_mm)) / half
    gy = abs(Fraction(a.y_mm) - Fraction(b.y_mm)) - (Fraction(plan_a.Ly_mm) + Fraction(plan_b.Ly_mm)) / half
    if gx < zero and gy < zero:
        return True, zero
    if gx < zero:
        return False, gy * gy
    if gy < zero:
        return False, gx * gx
    return False, gx * gx + gy * gy


def _by_footing(field: str, rows: Sequence[Any], footings: Iterable[str], member: str) -> dict[str, list[str]]:
    """The `member` of each row by footing, in the order given, without repeats; a row outside the design is refused."""
    found: dict[str, list[str]] = {footing: [] for footing in footings}
    for row in rows:
        if row.id not in found:
            raise _refuse(field, row.id, f"{field} names footing {row.id}, which is not in the design")
        found[row.id].append(getattr(row, member))
    return {footing: list(dict.fromkeys(values)) for footing, values in found.items()}


def _consistent(subjects: FootingSubjects, design: FootingDesign, status: FootingStatus) -> None:
    """The three records must describe the same footings: design rows are subjects and have status rows, and back."""
    subject_ids = {s.id for s in subjects.subjects}
    design_ids = {row.id for row in design.footings}
    status_ids = {row.id for row in status.footings}
    for footing in sorted(design_ids - subject_ids):
        raise _refuse("design", footing, f"footing {footing} of the design is not a subject")
    for footing in sorted(subject_ids - design_ids):
        raise _refuse("design", footing, f"subject {footing} has no design row")
    for footing in sorted(design_ids - status_ids):
        raise _refuse("status", footing, f"footing {footing} has no status row")
    for footing in sorted(status_ids - design_ids):
        raise _refuse("status", footing, f"status row {footing} is not a footing of the design")


@calc(
    id="harness.footing_schedule",
    version=int(VERSION.value),
    output_kind="harness.footing_schedule/1",
    title="Footing schedule with the clearance check",
    method_source="eng-harness spec 0010 §4.4.6",
    verification="draft",
)
def footing_schedule(inp: ScheduleInput, meta: InputMeta, trace: TraceBuilder) -> ScheduleBody:
    """Assemble the schedule rows and mark the footings that violate the clear distance.

    Raises:
        ContractError: see the module docstring.
    """
    clear = _clear_distance(inp.basis)
    _consistent(inp.subjects, inp.design, inp.status)
    design = sorted(inp.design.footings, key=lambda row: row.id)
    ids = [row.id for row in design]
    positions = {s.id: s for s in inp.subjects.subjects}
    plans = {row.id: (positions[row.id], row) for row in design}
    closed = _by_footing("closures", inp.closures, ids, "reason")
    judged = _by_footing("verdict_sets", inp.verdict_sets, ids, "result")
    decided = _by_footing("decisions", inp.decisions, ids, "decision")
    ref = {name: meta.refs[name].result_id for name in ("subjects", "design", "status", "basis")}
    trace.input("subjects", len(inp.subjects.subjects), ref=ref["subjects"])
    trace.input("design", len(design), ref=ref["design"])
    trace.input("status", len(inp.status.footings), ref=ref["status"])
    trace.input("closures", len(inp.closures))
    trace.input("verdict_sets", len(inp.verdict_sets))
    trace.input("decisions", len(inp.decisions))
    trace.input("min_clear_distance", clear, unit=ZERO_DISTANCE.unit, ref=f"{ref['basis']}#/fields/{_FIELD}")
    trace.constant("halving", HALVING)
    trace.constant("zero_distance", ZERO_DISTANCE)
    limit = Fraction(clear) * Fraction(clear)
    pairs = [(a, b, *_clearance(plans[a], plans[b])) for a, b in product(ids, ids) if a < b]
    overlapping = [pair for pair in pairs if pair[2]]
    close = [pair for pair in pairs if not pair[2] and pair[3] < limit]
    nearest: dict[str, tuple[bool, Fraction, str]] = {}
    for a, b, overlap, squared in [*overlapping, *close]:
        for footing, other in ((a, b), (b, a)):
            key = (not overlap, squared, other)
            if footing not in nearest or key < nearest[footing]:
                nearest[footing] = key
    states = {row.id: row for row in inp.status.footings}
    rows: list[ScheduleRow] = []
    for row in design:
        marked = row.id in nearest
        own = [] if row.reason is None else [row.reason]
        reasons = list(dict.fromkeys([*own, *closed[row.id], *([Reason.CLEARANCE.value] if marked else [])]))
        shown = row
        if marked and row.status != VerdictStatus.NEEDS_ENGINEER.value:
            shown = row.model_copy(
                update={"status": VerdictStatus.NEEDS_ENGINEER.value, "reason": Reason.CLEARANCE.value}
            )
        state = states[row.id]
        rows.append(
            ScheduleRow(
                design=shown,
                families=state.families,
                closure=state.closure,
                reasons=reasons,
                verdict_sets=judged[row.id],
                decisions=decided[row.id],
                neighbour=nearest[row.id][2] if marked else None,
            )
        )
    trace.step("footings", len(rows), formula="footings of the design", source=f"{_RULE} schedule", uses=["design"])
    trace.step(
        "pairs", len(pairs), formula="unordered pairs of footings", source=f"{_RULE} clearance", uses=["footings"]
    )
    trace.step(
        "overlapping_pairs",
        len(overlapping),
        formula="pairs whose plans overlap in both axes",
        source=f"{_RULE} clearance",
        uses=["pairs", "subjects", "design", "halving", "zero_distance"],
    )
    trace.step(
        "close_pairs",
        len(close),
        formula="pairs that do not overlap with a squared distance below the squared clear distance",
        source=f"{_RULE} clearance",
        uses=["overlapping_pairs", "min_clear_distance"],
    )
    trace.step(
        "marked_footings",
        len(nearest),
        formula="footings in an overlapping or close pair",
        source=f"{_RULE} clearance",
        uses=["overlapping_pairs", "close_pairs"],
    )
    trace.output("footings", "pairs", "overlapping_pairs", "close_pairs", "marked_footings")
    return ScheduleBody(footings=rows)
