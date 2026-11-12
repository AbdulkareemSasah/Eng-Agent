"""Calc 2, difference report `harness.model_diff` v1 (spec 0003 4.7, rules D1 to D7).

Purpose: show every change between two model state reads (before and after), per section and key, with each changed
property's pointer, values, unit and the tolerance applied. The comparison core of `_compare.py` applies D2 to D5;
this module applies D1 (a section is compared only when both sides hold it: the input fields fix each section's kind
version and records are always `canonical/1`), D6 (nothing is normalized) and D7.
Inputs: `before_<section>` and `after_<section>` (the two read sets, flat because the CalcPort resolves top-level
references only; `before_*` is `stale_ok`, spec 4.13) and `basis`.
Units: tolerances are the `compare.*` basis fields of spec 4.4, one per quantity kind, in its canonical unit.
Errors: `ContractError` `INVALID_ARGUMENT` (with `field`) for a basis field that is missing, unconfirmed, in another
unit, not a number or negative (no default), a basis or section given without a record, a record without a host
model, or one side mixing models or revisions; a `ValidationError` when a side has no section.
"""

from fractions import Fraction
from typing import Any, Self

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import (
    AreaPlacements,
    FramePlacements,
    GridSystem,
    JointRestraints,
    LoadSet,
    Materials,
    Sections,
    Stories,
)
from eng_contract.params import eng_param
from pydantic import model_validator

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import Tolerances, as_fraction, compare_section, section_counts
from eng_harness.calcs._state import SECTIONS
from eng_harness.kinds.calcs import Change, DiffBody, SectionCounts, Side, Tolerance, WithinRow

__all__ = ["BASIS_FIELDS", "TOLERANCE_FIELDS", "DiffInput", "model_diff", "read_tolerances"]

TOLERANCE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("compare.length", "length", "mm"),
    ("compare.angle", "angle", "deg"),
    ("compare.stress", "stress", "MPa"),
    ("compare.unit_weight", "unit_weight", "kN/m3"),
    ("compare.line_load", "line_load", "kN/m"),
    ("compare.area_load", "area_load", "kPa"),
    ("compare.ratio", "dimensionless", "1"),
)
"""The spec 4.4 table rows this calc reads: basis path, quantity kind (`kind_for_field` name) and unit."""
BASIS_FIELDS = tuple(path for path, _, _ in TOLERANCE_FIELDS)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""


def _section(kind: str, *, stale_ok: bool) -> Any:
    return eng_param(None, ref_capable=True, ref_kinds={kind}, engineering_quantity=True, stale_ok=stale_ok)


class DiffInput(CalcInput):
    """The before and after read sets (one optional reference per neutral model kind each) and the design basis."""

    before_stories: Stories | None = _section("model.stories/1", stale_ok=True)
    before_grids: GridSystem | None = _section("model.grid_system/1", stale_ok=True)
    before_frames: FramePlacements | None = _section("model.frame_placements/1", stale_ok=True)
    before_areas: AreaPlacements | None = _section("model.area_placements/1", stale_ok=True)
    before_sections: Sections | None = _section("model.sections/1", stale_ok=True)
    before_materials: Materials | None = _section("model.materials/1", stale_ok=True)
    before_loads: LoadSet | None = _section("model.load_set/1", stale_ok=True)
    before_restraints: JointRestraints | None = _section("model.joint_restraints/1", stale_ok=True)
    after_stories: Stories | None = _section("model.stories/1", stale_ok=False)
    after_grids: GridSystem | None = _section("model.grid_system/1", stale_ok=False)
    after_frames: FramePlacements | None = _section("model.frame_placements/1", stale_ok=False)
    after_areas: AreaPlacements | None = _section("model.area_placements/1", stale_ok=False)
    after_sections: Sections | None = _section("model.sections/1", stale_ok=False)
    after_materials: Materials | None = _section("model.materials/1", stale_ok=False)
    after_loads: LoadSet | None = _section("model.load_set/1", stale_ok=False)
    after_restraints: JointRestraints | None = _section("model.joint_restraints/1", stale_ok=False)
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)

    @model_validator(mode="after")
    def _both_sides(self) -> Self:
        for side in ("before", "after"):
            if all(getattr(self, f"{side}_{name}") is None for name, _ in SECTIONS):
                raise ValueError("each side needs at least one section")
        return self


def _refuse(path: str, why: str) -> ContractError:
    return ContractError(
        ErrorCode.INVALID_ARGUMENT,
        f"basis field {path} {why}",
        field=f"basis.fields.{path}",
        hint=f"set and confirm {path} in the design basis",
    )


def read_tolerances(basis: DesignBasis, basis_id: str, trace: TraceBuilder) -> tuple[Tolerances, dict[str, Tolerance]]:
    """Spec 4.4: each `compare.*` field present, confirmed, in its unit and >= 0; exact values and display rows."""
    exact: dict[str, Fraction] = {}
    shown: dict[str, Tolerance] = {}
    for path, kind, unit in TOLERANCE_FIELDS:
        field = basis.fields.get(path)
        if field is None:
            raise _refuse(path, "is missing (no default)")
        if not field.confirmed:
            raise _refuse(path, "is not confirmed")
        if field.unit != unit:
            raise _refuse(path, f"must be in {unit}, not {field.unit}")
        value = as_fraction(field.value)
        if value is None or abs(value) != value:  # not a finite number, or negative (4.4 bounds: >= 0)
            raise _refuse(path, "must be a number >= 0")
        pointer = f"{basis_id}#/fields/{path}"
        exact[kind] = value
        shown[kind] = Tolerance(value=float(value), unit=unit, ref=pointer)
        trace.input(path.replace(".", "_"), float(value), unit=unit, ref=pointer)
    return exact, shown


def _side(inp: DiffInput, meta: InputMeta, side: str) -> tuple[Side, bool, dict[str, dict[str, Any]]]:
    """One side's model and revision (one of each), whether its records are complete, and its payloads by kind."""
    identity: tuple[str, int] | None = None
    complete = True
    payloads: dict[str, dict[str, Any]] = {}
    for name, kind in SECTIONS:
        field = f"{side}_{name}"
        if (payload := getattr(inp, field)) is None:
            continue
        if (ref := meta.refs.get(field)) is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "a section must be a record reference", field=field)
        if ref.model_id is None or ref.model_revision is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "the record names no host model", field=field)
        identity = identity or (ref.model_id, ref.model_revision)
        if (ref.model_id, ref.model_revision) != identity:
            message = "the records of one side belong to different models or revisions"
            raise ContractError(ErrorCode.INVALID_ARGUMENT, message, field=field)
        complete = complete and ref.complete
        payloads[kind] = payload.model_dump(mode="json", by_alias=True, exclude_none=False)
    if identity is None:  # the input model requires a section on each side; kept for the type checker
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "each side needs at least one section", field=side)
    covered = sorted(payloads)
    return Side(model_id=identity[0], model_revision=identity[1], covered=covered), complete, payloads


def _tally(counts: SectionCounts) -> str:
    return ", ".join(f"{name.replace('_', ' ')} {value}" for name, value in counts.model_dump().items())


@calc(
    id="harness.model_diff",
    version=1,
    output_kind="harness.model_diff/1",
    title="Difference report between two model states",
    method_source="eng-harness spec 0003 §4.7 (D1 to D7); 18 §4 step 4",
    verification="draft",
)
def model_diff(inp: DiffInput, meta: InputMeta, trace: TraceBuilder) -> DiffBody:
    """Read the tolerances, compare each section both sides hold (D1 to D6) and build the report (D7)."""
    if (basis := meta.refs.get("basis")) is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "the basis must be a record reference", field="basis")
    exact, shown = read_tolerances(inp.basis, basis.result_id, trace)
    tolerance_names = [path.replace(".", "_") for path in BASIS_FIELDS]
    before, before_complete, old = _side(inp, meta, "before")
    after, after_complete, new = _side(inp, meta, "after")
    changes: list[Change] = []
    within: list[WithinRow] = []
    counts: dict[str, SectionCounts] = {}
    not_compared: list[str] = []
    steps: list[str] = []
    for name, kind in sorted(SECTIONS, key=lambda section: section[1]):
        if kind not in old or kind not in new:  # D1
            if kind in old or kind in new:
                not_compared.append(kind)
            continue
        diff = compare_section(kind, old[kind], new[kind], exact)
        changes += diff.changes
        within += diff.within
        counts[kind] = section_counts(diff)
        steps.append(f"{name}_counts")
        trace.step(
            steps[-1],
            _tally(counts[kind]),
            formula=f"objects of {kind} matched by key (D2), compared by D3 to D5",
            source="§4.7 D1 to D5",
            uses=tolerance_names,
        )
    ambiguous = any(change.change == "ambiguous" for change in changes)
    complete = before_complete and after_complete and not not_compared and not ambiguous
    identical = complete and not changes  # D7
    trace.step(
        "identical",
        identical,
        formula="no changes or ambiguous keys, nothing not compared, both sides complete",
        source="§4.7 D7",
        uses=steps,
    )
    trace.output("identical")
    return DiffBody(
        before=before,
        after=after,
        tolerances=shown,
        changes=changes,
        within_tolerance=within,
        not_compared=not_compared,
        counts=counts,
        identical=identical,
        complete=complete,
    )
