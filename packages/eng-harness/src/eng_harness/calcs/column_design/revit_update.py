"""Calc `harness.revit_column_update` v1: plan of Revit column type changes by reference (spec 0013 4.4.5, U1 to U10).

Purpose: for each `harness.frame_element_map/1` pair, take the target roles from the frame's ETABS section as
references to `model.sections/1` fields (`rectangular` sets `section_b` and `section_h`, `circular` sets `section_D`;
`other` is `not_updatable` `SHAPE_NOT_SUPPORTED`); block pairs whose family lacks a `reference` status for every
required role (`SECTION_ROLES_UNMAPPED`); keep the element's current type when every role is within
`compare.length_mm` (`no_change`); otherwise reuse the one same-family type within tolerance, report several as
`TYPE_AMBIGUOUS`, or plan one new type per (family, ETABS section name) named after the section (`NAME_CONFLICT`
when that name is taken). A pair that proceeds to a write with a non-square rectangular target carries an
`orientation` row with the ETABS and Revit `rotation_deg` references (never compared, never written). Every
assignment carries its origin (`changed_in_design` when its frame is in `changed`, else `preexisting`); `expected`
holds one element row per assignment and one type row per new type. Ids are `str(int)`; U1 and U5 pointers use the
actual input row indices. The calc holds no engineering constant.
Units: lengths in mm. Errors: `ContractError` `INVALID_ARGUMENT` for a basis field that is missing, unconfirmed, not
a number or negative, for a non-reference `map`, `frames`, `sections`, `revit`, `revit_placements`, `changed` or
`basis`, and for a map pair whose frame, section, element, current type or Revit placement row the inputs lack.
"""

from fractions import Fraction
from typing import Any, Literal, NamedTuple

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import Circular, FramePlacements, Rectangular, Sections
from eng_contract.params import eng_param
from eng_contract.quantity import Quantity
from eng_contract.refs import RefString
from eng_contract.units import unit
from pydantic import BaseModel, ConfigDict, StrictBool

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs.column_design.column_select import read_tolerance
from eng_harness.kinds.calcs import FrameElementMap
from eng_harness.kinds.edit_cycle import Label
from eng_harness.kinds.revit import ParameterValue, RevitStructure, TypeRow

__all__ = ["BASIS_FIELDS", "RevitUpdateBody", "RevitUpdateInput", "revit_column_update"]

_LENGTH = "compare.length_mm"
BASIS_FIELDS = (_LENGTH,)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""
_ROLE_B = "section_b"
_ROLE_H = "section_h"
_ROLE_D = "section_D"
_MM = "mm"
_REFS = ("map", "frames", "sections", "revit", "revit_placements", "changed", "basis")
_RULE = "spec 0013 4.4.5"
_RoleStatus = Literal["reference", "candidate", "unmapped"]
_Origin = Literal["preexisting", "changed_in_design"]
_BlockedCode = Literal["SHAPE_NOT_SUPPORTED", "SECTION_ROLES_UNMAPPED", "TYPE_AMBIGUOUS", "NAME_CONFLICT"]


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class _ChangedRow(_M):
    """One row of the design record's `changed` list (spec 0013 AC22), resolved through `#/changed`."""

    frame_id: Label
    from_section: Label
    to_section: Label


def _ref(kind: str) -> Any:
    return eng_param(ref_capable=True, ref_kinds={kind}, engineering_quantity=True)


class RevitUpdateInput(CalcInput):
    """Map pairs, ETABS frames and sections, Revit reads, role statuses, changed frames and basis."""

    map: FrameElementMap = _ref("harness.frame_element_map/1")
    frames: FramePlacements = _ref("model.frame_placements/1")
    sections: Sections = _ref("model.sections/1")
    revit: RevitStructure = _ref("harness.revit_structure/1")
    role_statuses: dict[Label, dict[Label, _RoleStatus]]
    """RV section 4.8 validation results keyed by family and role (spec 0013 Q15); inline, not a reference."""
    revit_placements: FramePlacements = _ref("model.frame_placements/1")
    changed: list[_ChangedRow] = _ref("harness.column_design_record/1")
    basis: DesignBasis = _ref("basis.design_basis/1")


class _NewType(_M):
    family: str
    section: str
    name: str
    from_unique_id: str
    origins: list[_Origin]
    roles: dict[str, RefString]


class _Same(_M):
    unique_id: str
    type_id: str


class _Assign(_M):
    unique_id: str
    element_id: str
    from_type_id: str
    type_id: str | None = None
    new_type_name: str | None = None
    origin: _Origin


class _Blocked(_M):
    frame_id: str
    code: _BlockedCode


class _Orient(_M):
    frame_id: str
    rotations: tuple[RefString, RefString]


class _ExpectEl(_M):
    unique_id: str
    type_id: str | None = None
    family: str | None = None
    type_name: str | None = None


class _ExpectType(_M):
    family: str
    name: str
    roles: dict[str, RefString]


class _Expected(_M):
    elements: list[_ExpectEl]
    types: list[_ExpectType]


class RevitUpdateBody(_M):
    """The payload of `harness.revit_column_update/1` without `calc`, `draft` and `trace`."""

    new_types: list[_NewType]
    assignments: list[_Assign]
    no_change: list[_Same]
    not_updatable: list[_Blocked]
    orientation: list[_Orient]
    expected: _Expected
    complete: StrictBool


class _Pending(NamedTuple):
    """One pair past U3: identities, U1 target values in mm and their section references."""

    frame_id: str
    unique_id: str
    element_id: int
    from_type_id: int
    family: str
    section: str
    targets: dict[str, Fraction]
    refs: dict[str, str]


def _require_refs(meta: InputMeta) -> dict[str, str]:
    """The `result_id` of every referenced input; `role_statuses` is inline and needs none."""
    refs: dict[str, str] = {}
    for name in _REFS:
        entry = meta.refs.get(name)
        if entry is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{name} must be a record reference", field=name)
        refs[name] = entry.result_id
    return refs


def _role_mm(value: ParameterValue | None) -> Fraction | None:
    """The type parameter value in mm as an exact Fraction, or None when it is not a length quantity."""
    if not isinstance(value, Quantity):
        return None
    if unit(value.unit).dimension != unit(_MM).dimension:
        return None
    return Fraction(value.value) * unit(value.unit).factor / unit(_MM).factor


def _within(actual: Fraction, target: Fraction, tolerance: Fraction) -> bool:
    """U3/U4: |actual - target| <= tolerance as exact Fractions of the stored values."""
    return abs(actual - target) <= tolerance


def _within_all(roles: dict[str, Fraction], params: dict[str, ParameterValue], tolerance: Fraction) -> bool:
    """U3/U4: every required role reads a length within the tolerance of its target."""
    for role, target in roles.items():
        actual = _role_mm(params.get(role))
        if actual is None or not _within(actual, target, tolerance):
            return False
    return True


def _origin_of(frame_id: str, changed: set[str]) -> _Origin:
    """U6: `changed_in_design` when the frame is in `changed`, otherwise `preexisting`."""
    return "changed_in_design" if frame_id in changed else "preexisting"


@calc(
    id="harness.revit_column_update",
    version=1,
    output_kind="harness.revit_column_update/1",
    title="Revit column update plan: type reuse, new types and read-back expectations by reference",
    method_source="eng-harness spec 0013 §4.4.5 (U1 to U10)",
    verification="draft",
)
def revit_column_update(inp: RevitUpdateInput, meta: InputMeta, trace: TraceBuilder) -> RevitUpdateBody:
    """Plan per-pair type reuse or new types with origins, orientation rows and read-back expectations (U1 to U10).

    Raises:
        ContractError: see the module docstring.
    """
    refs = _require_refs(meta)
    tolerance = read_tolerance(inp.basis)
    trace.input("pairs", len(inp.map.pairs), ref=refs["map"])
    trace.input("frames", len(inp.frames.frames), ref=refs["frames"])
    trace.input("frame_sections", len(inp.sections.frame_sections), ref=refs["sections"])
    trace.input("elements", len(inp.revit.elements), ref=refs["revit"])
    trace.input("types", len(inp.revit.types), ref=refs["revit"])
    trace.input("role_statuses", len(inp.role_statuses))
    trace.input("revit_placements", len(inp.revit_placements.frames), ref=refs["revit_placements"])
    trace.input("changed", len(inp.changed), ref=refs["changed"])
    trace.input("compare_length_mm", float(tolerance), unit=_MM, ref=f"{refs['basis']}#/fields/{_LENGTH}")
    frames = {row.id: row for row in inp.frames.frames}
    frame_index = {row.id: pos for pos, row in enumerate(inp.frames.frames)}
    sections = {row.name: row for row in inp.sections.frame_sections}
    section_index = {row.name: pos for pos, row in enumerate(inp.sections.frame_sections)}
    elements = {row.unique_id: row for row in inp.revit.elements}
    types = {row.type_id: row for row in inp.revit.types}
    revit_index = {row.id: pos for pos, row in enumerate(inp.revit_placements.frames)}
    changed = {row.frame_id for row in inp.changed}
    no_change: list[_Same] = []
    not_updatable: list[_Blocked] = []
    pending: list[_Pending] = []
    for pair in inp.map.pairs:
        frame = frames.get(pair.frame_id)
        if frame is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"frame {pair.frame_id} of the map is not in the frames",
                field="frames",
            )
        section = sections.get(frame.section)
        pos = section_index.get(frame.section)
        if section is None or pos is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"section {frame.section} of column {pair.frame_id} is not in the sections",
                field="sections",
                received=frame.section,
            )
        element = elements.get(pair.unique_id)
        if element is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"element {pair.unique_id} of the map is not in the revit structure",
                field="revit",
            )
        current = types.get(element.type_id)
        if current is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"type {element.type_id} of element {pair.unique_id} is not in the revit structure",
                field="revit",
            )
        shape = section.shape
        if isinstance(shape, Rectangular):
            wanted = {_ROLE_B: Fraction(shape.b_mm), _ROLE_H: Fraction(shape.h_mm)}
            fields = {_ROLE_B: "b_mm", _ROLE_H: "h_mm"}
        elif isinstance(shape, Circular):
            wanted = {_ROLE_D: Fraction(shape.D_mm)}
            fields = {_ROLE_D: "D_mm"}
        else:
            not_updatable.append(_Blocked(frame_id=pair.frame_id, code="SHAPE_NOT_SUPPORTED"))
            continue
        statuses = inp.role_statuses.get(element.family, {})
        if any(statuses.get(role) != "reference" for role in wanted):
            not_updatable.append(_Blocked(frame_id=pair.frame_id, code="SECTION_ROLES_UNMAPPED"))
            continue
        if _within_all(wanted, current.parameters, tolerance):
            no_change.append(_Same(unique_id=pair.unique_id, type_id=str(element.type_id)))
            continue
        pending.append(
            _Pending(
                frame_id=pair.frame_id,
                unique_id=pair.unique_id,
                element_id=element.element_id,
                from_type_id=element.type_id,
                family=element.family,
                section=frame.section,
                targets=wanted,
                refs={
                    role: f"{refs['sections']}#/frame_sections/{pos}/shape/{field}" for role, field in fields.items()
                },
            )
        )
    family_types: dict[str, list[TypeRow]] = {}
    for row in inp.revit.types:
        family_types.setdefault(row.family, []).append(row)
    groups: dict[tuple[str, str], list[_Pending]] = {}
    for item in pending:
        groups.setdefault((item.family, item.section), []).append(item)
    new_types: list[_NewType] = []
    assignments: list[_Assign] = []
    expected_elements: list[_ExpectEl] = []
    written: list[_Pending] = []
    for key in sorted(groups):
        members = sorted(groups[key], key=lambda item: item.unique_id)
        first = members[0]
        same_family = family_types.get(first.family, [])
        candidates = sorted(row.type_id for row in same_family if _within_all(first.targets, row.parameters, tolerance))
        if len(candidates) == 1:
            target = str(candidates[0])
            for item in members:
                origin = _origin_of(item.frame_id, changed)
                assignments.append(
                    _Assign(
                        unique_id=item.unique_id,
                        element_id=str(item.element_id),
                        from_type_id=str(item.from_type_id),
                        type_id=target,
                        origin=origin,
                    )
                )
                expected_elements.append(_ExpectEl(unique_id=item.unique_id, type_id=target))
                written.append(item)
        elif candidates:
            for item in members:
                not_updatable.append(_Blocked(frame_id=item.frame_id, code="TYPE_AMBIGUOUS"))
        else:
            names = {row.name for row in same_family}
            if first.section in names:
                for item in members:
                    not_updatable.append(_Blocked(frame_id=item.frame_id, code="NAME_CONFLICT"))
                continue
            origins: list[_Origin] = [_origin_of(item.frame_id, changed) for item in members]
            new_types.append(
                _NewType(
                    family=first.family,
                    section=first.section,
                    name=first.section,
                    from_unique_id=first.unique_id,
                    origins=origins,
                    roles=first.refs,
                )
            )
            for item in members:
                assignments.append(
                    _Assign(
                        unique_id=item.unique_id,
                        element_id=str(item.element_id),
                        from_type_id=str(item.from_type_id),
                        new_type_name=first.section,
                        origin=_origin_of(item.frame_id, changed),
                    )
                )
                expected_elements.append(
                    _ExpectEl(unique_id=item.unique_id, family=item.family, type_name=first.section)
                )
                written.append(item)
    orientation: list[_Orient] = []
    for item in written:
        if _ROLE_D in item.targets or item.targets[_ROLE_B] == item.targets[_ROLE_H]:
            continue
        pos = revit_index.get(item.unique_id)
        if pos is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"element {item.unique_id} of the map is not in the revit placements",
                field="revit_placements",
            )
        orientation.append(
            _Orient(
                frame_id=item.frame_id,
                rotations=(
                    f"{refs['frames']}#/frames/{frame_index[item.frame_id]}/rotation_deg",
                    f"{refs['revit_placements']}#/frames/{pos}/rotation_deg",
                ),
            )
        )
    assignments.sort(key=lambda row: row.unique_id)
    no_change.sort(key=lambda row: row.unique_id)
    not_updatable.sort(key=lambda row: row.frame_id)
    orientation.sort(key=lambda row: row.frame_id)
    expected_elements.sort(key=lambda row: row.unique_id)
    expected_types = [_ExpectType(family=row.family, name=row.name, roles=row.roles) for row in new_types]
    complete = all(entry.complete for entry in meta.refs.values())
    trace.step(
        "targets",
        len(pending) + len(no_change),
        formula="map pairs with a rectangular or circular ETABS section and reference roles",
        source=f"{_RULE} U1, U2",
        uses=["pairs", "frames", "frame_sections", "role_statuses"],
    )
    trace.step(
        "no_change",
        len(no_change),
        formula="current type within compare.length_mm on every role",
        source=f"{_RULE} U3",
        uses=["targets", "elements", "types", "compare_length_mm"],
    )
    trace.step(
        "not_updatable",
        len(not_updatable),
        formula="pairs blocked: other shape, unmapped roles, ambiguous or conflicting types",
        source=f"{_RULE} U1, U2, U4",
        uses=["pairs", "targets", "types", "compare_length_mm"],
    )
    trace.step(
        "new_types",
        len(new_types),
        formula="one new type per (family, ETABS section) with no type within tolerance",
        source=f"{_RULE} U4",
        uses=["targets", "types", "compare_length_mm"],
    )
    trace.step(
        "assignments",
        len(assignments),
        formula="reuse and new-type assignments with changed_in_design or preexisting origins",
        source=f"{_RULE} U4, U6",
        uses=["targets", "no_change", "not_updatable", "changed"],
    )
    trace.step(
        "orientation",
        len(orientation),
        formula="non-square rectangular write pairs with ETABS and Revit rotation references",
        source=f"{_RULE} U5",
        uses=["assignments", "frames", "revit_placements"],
    )
    trace.step(
        "expected_elements",
        len(expected_elements),
        formula="one element expectation per assignment",
        source=f"{_RULE} U7",
        uses=["assignments"],
    )
    trace.step(
        "expected_types",
        len(expected_types),
        formula="one type expectation per new type",
        source=f"{_RULE} U7",
        uses=["new_types"],
    )
    trace.step(
        "complete",
        complete,
        formula="all referenced input records complete",
        source=f"{_RULE} U8",
    )
    trace.output(
        "new_types",
        "assignments",
        "no_change",
        "not_updatable",
        "orientation",
        "expected_elements",
        "expected_types",
        "complete",
    )
    return RevitUpdateBody(
        new_types=new_types,
        assignments=assignments,
        no_change=no_change,
        not_updatable=not_updatable,
        orientation=orientation,
        expected=_Expected(elements=expected_elements, types=expected_types),
        complete=complete,
    )
