"""Calc `harness.footing_status` v1: family statuses, closure and decision state of each footing (spec 0010 4.4.5).

Purpose: for every footing of a round's design, reduce the verdicts of each of the six check families (bearing,
one-way shear, punching, flexure, minimum steel, development) to one status with the governing ratio for display,
then give the closure and the `FootingFailureState` the decision point of spec 0010 4.5 reads.
Family status (spec 0010 4.4.5): `FAIL` if any verdict fails, else `ERROR`, else `NEEDS_ENGINEER`, else
`NOT_APPLICABLE`, else `PASS`. Governing ratio: the largest ratio of the verdicts that carry `governing` (the code pack
marks, for each subject, the PASS or FAIL verdict with the largest ratio), or null when there is none.
Closure: `passed` when all six are `PASS`, `failing` when any is `FAIL`, else `needs_engineer`.
State: the six family statuses, `plan_at_max`, `depth_at_max` and `spacing_at_min` as the design row sets them, and
`engineer_sized` when the size source is `engineer`.
Units: ratios are dimensionless; no length or force enters.
Errors: `ContractError` `INVALID_ARGUMENT` (a footing of the design that is no subject; a verdict about a subject that
is not a footing, or about a footing outside the design; a footing without any verdict in one of the six sets).
"""

from collections.abc import Sequence
from typing import Any

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.params import eng_param
from eng_contract.verdicts import SubjectKind, Verdict, VerdictStatus
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.kinds.footing import FailureState, Families, Family, FootingDesign, FootingSubjects, StatusRow

BASIS_FIELDS: tuple[str, ...] = ()
"""The basis paths this calc reads (spec 0003 4.4): none."""
FAMILIES = ("bearing", "one_way_shear", "punching", "flexure", "min_steel", "development")
"""The six check families, in the order of `harness.footing_status/1`."""
PRECEDENCE = (VerdictStatus.FAIL, VerdictStatus.ERROR, VerdictStatus.NEEDS_ENGINEER, VerdictStatus.NOT_APPLICABLE)
"""The statuses that decide a family before `PASS`, strongest first (spec 0010 4.4.5)."""
VERSION = Cited(value=1, unit="1", source="Calc version 1 of spec 0010 4.4.5; a change of method is a new version")
_RULE = "spec 0010 4.4.5"


def _verdicts() -> Any:
    return eng_param(ref_capable=True, ref_kinds={"verdicts.set/1"}, engineering_quantity=True)


class StatusInput(CalcInput):
    """The round's subjects and design and the six verdict sets (one per family), all by reference."""

    subjects: FootingSubjects = eng_param(
        ref_capable=True, ref_kinds={"harness.footing_subjects/1"}, engineering_quantity=True
    )
    design: FootingDesign = eng_param(
        ref_capable=True, ref_kinds={"harness.footing_design/1"}, engineering_quantity=True
    )
    bearing: VerdictSet = _verdicts()
    one_way_shear: VerdictSet = _verdicts()
    punching: VerdictSet = _verdicts()
    flexure: VerdictSet = _verdicts()
    min_steel: VerdictSet = _verdicts()
    development: VerdictSet = _verdicts()


class StatusBody(BaseModel):
    """The payload of `harness.footing_status/1` without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    footings: list[StatusRow]


def _refuse(field: str, received: str, message: str) -> ContractError:
    return ContractError(ErrorCode.INVALID_ARGUMENT, message, field=field, received=received)


def _group(family: str, verdict_set: VerdictSet, footings: Sequence[str]) -> dict[str, list[Verdict]]:
    """The verdicts of one set by footing; every footing of the design must have one."""
    groups: dict[str, list[Verdict]] = {footing: [] for footing in footings}
    for verdict in verdict_set.verdicts:
        subject = verdict.subject
        if subject.kind is not SubjectKind.FOOTING:
            raise _refuse(
                family, subject.id, f"a verdict of the {family} set is about a {subject.kind.value}, not a footing"
            )
        if subject.id not in groups:
            raise _refuse(
                family,
                subject.id,
                f"a verdict of the {family} set is about footing {subject.id}, which is not in the design",
            )
        groups[subject.id].append(verdict)
    for footing, verdicts in groups.items():
        if not verdicts:
            raise _refuse(family, footing, f"footing {footing} has no verdict in the {family} set")
    return groups


def _family(verdicts: Sequence[Verdict]) -> Family:
    """The family status by the order of spec 0010 4.4.5 and the governing ratio for display."""
    present = {verdict.status for verdict in verdicts}
    status = next((s for s in PRECEDENCE if s in present), VerdictStatus.PASS)
    ratios = [v.ratio for v in verdicts if v.governing and v.ratio is not None]
    return Family(status=status, ratio=max(ratios) if ratios else None)


@calc(
    id="harness.footing_status",
    version=int(VERSION.value),
    output_kind="harness.footing_status/1",
    title="Footing status: family statuses, closure and decision state",
    method_source="eng-harness spec 0010 §4.4.5",
    verification="draft",
)
def footing_status(inp: StatusInput, meta: InputMeta, trace: TraceBuilder) -> StatusBody:
    """Reduce the six verdict sets of a round to the status row of each footing of the design.

    Raises:
        ContractError: see the module docstring.
    """
    design = sorted(inp.design.footings, key=lambda row: row.id)
    subjects = {subject.id for subject in inp.subjects.subjects}
    for row in design:
        if row.id not in subjects:
            raise _refuse("design", row.id, f"footing {row.id} of the design is not a subject")
    ids = [row.id for row in design]
    sets = {name: getattr(inp, name) for name in FAMILIES}
    groups = {name: _group(name, sets[name], ids) for name in FAMILIES}
    ref = {name: meta.refs[name].result_id for name in ("subjects", "design", *FAMILIES)}
    trace.input("subjects", len(subjects), ref=ref["subjects"])
    trace.input("design_footings", len(design), ref=ref["design"])
    for name in FAMILIES:
        trace.input(f"{name}_verdicts", len(sets[name].verdicts), ref=ref[name])
    rows: list[StatusRow] = []
    for row in design:
        found = {name: _family(groups[name][row.id]) for name in FAMILIES}
        families = Families(
            bearing=found["bearing"],
            one_way_shear=found["one_way_shear"],
            punching=found["punching"],
            flexure=found["flexure"],
            min_steel=found["min_steel"],
            development=found["development"],
        )
        state = FailureState(
            bearing=families.bearing.status,
            one_way_shear=families.one_way_shear.status,
            punching=families.punching.status,
            flexure=families.flexure.status,
            min_steel=families.min_steel.status,
            development=families.development.status,
            plan_at_max=row.plan_at_max,
            depth_at_max=row.depth_at_max,
            spacing_at_min=row.spacing_at_min,
            engineer_sized=row.source == "engineer",
        )
        rows.append(StatusRow(id=row.id, families=families, closure=families.closure(), state=state))
    inputs = [f"{name}_verdicts" for name in FAMILIES]
    trace.step("footings", len(rows), formula="footings of the design", source=_RULE, uses=["design_footings", *inputs])
    for name, closure in (("passed", "passed"), ("failing", "failing"), ("needs_engineer", "needs_engineer")):
        trace.step(
            name,
            len([r for r in rows if r.closure == closure]),
            formula=f"footings whose closure is {closure}",
            source=f"{_RULE} closure",
            uses=["footings"],
        )
    trace.output("footings", "passed", "failing", "needs_engineer")
    return StatusBody(footings=rows)
