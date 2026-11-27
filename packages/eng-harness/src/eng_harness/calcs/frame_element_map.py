"""Calc `harness.frame_element_map` v1 (spec 0011 §4.11 rules M1 to M6; OQ-Q104 structure join).

Purpose: map ETABS frames to Revit elements by geometry (offset, elevation-ordered ends, inclusive
squared-distance tolerance), with optional etabs_link strings as hints only, then take host
`element_id` / `type_id` from `harness.revit_structure/1` by `unique_id`.
Inputs: `frames` / `elements` (`model.frame_placements/1`), `structure` (`harness.revit_structure/1`),
optional `links` (`unique_id` → ETABS frame id string), and `basis` (`compare.length_mm`,
`mapping.offset_x_mm` / `_y_mm` / `_z_mm`). No input is `stale_ok` (spec 0011 §4.11).
Units: millimetres; offsets, translated ends and squared distances stay exact `Fraction`s (M1, M2;
0003 §4.11 P2); display distances are `sqrt` of d² in float. A link whose frame id is not in `frames` is ignored (M4).
Errors: `ContractError` `INVALID_ARGUMENT` for a basis given without a record, a basis field missing,
unconfirmed, wrong unit or a non-numeric value; `OUT_OF_RANGE` for a confirmed numeric
`compare.length_mm` below 0 (spec 0011 §4.11 / 0003 §4.4 inclusive lower bound).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from fractions import Fraction
from typing import Any, Literal

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import BasisField, DesignBasis
from eng_contract.kinds.model import Frame, FramePlacements
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict, StrictInt

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.revit import RevitStructure

__all__ = ["BASIS_FIELDS", "FrameElementMapBody", "FrameElementMapInput", "frame_element_map"]

LENGTH = "compare.length_mm"
OFFSET_X = "mapping.offset_x_mm"
OFFSET_Y = "mapping.offset_y_mm"
OFFSET_Z = "mapping.offset_z_mm"
BASIS_FIELDS = (LENGTH, OFFSET_X, OFFSET_Y, OFFSET_Z)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""
ZERO = Cited(value=0, unit="mm", source="eng-harness spec 0011 §4.11 / 0003 §4.4: compare.length_mm is >= 0")
"""Lower bound of `compare.length_mm` (inclusive)."""
VERSION = Cited(
    value=1,
    unit="1",
    source="Calc version 1 of eng-harness spec 0011 §4.11; a method change is a new version",
)
PairBasis = Literal["geometry", "both"]
AmbiguousSide = Literal["frame", "element"]


class FrameElementMapInput(CalcInput):
    """ETABS frames, Revit frame placements, structure rows for host ids, optional links, and the basis."""

    frames: FramePlacements = eng_param(
        ref_capable=True, ref_kinds={"model.frame_placements/1"}, engineering_quantity=True
    )
    elements: FramePlacements = eng_param(
        ref_capable=True, ref_kinds={"model.frame_placements/1"}, engineering_quantity=True
    )
    structure: RevitStructure = eng_param(
        ref_capable=True, ref_kinds={"harness.revit_structure/1"}, engineering_quantity=True
    )
    links: dict[str, str] | None = eng_param(None, ref_capable=False, engineering_quantity=False)
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)


class PairRow(BaseModel):
    """One matched frame↔element pair after the structure join (spec 0011 §4.11 output)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frame_id: str
    unique_id: str
    element_id: StrictInt
    type_id: StrictInt
    basis: PairBasis
    lower_distance_mm: float
    upper_distance_mm: float


class AmbiguousRow(BaseModel):
    """An id with several geometric candidates on the other side (M3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    side: AmbiguousSide
    id: str
    candidates: list[str]


class UnmatchedFrameRow(BaseModel):
    """A frame with no geometric candidate (M3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frame_id: str


class UnmatchedElementRow(BaseModel):
    """An element with no geometric candidate (M3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    unique_id: str


class ConflictRow(BaseModel):
    """A link/geometry disagreement (M4) or a structure-join failure (spec 0011 §4.11)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frame_id: str
    unique_id: str
    geometric_unique_id: str | None


class FrameElementMapBody(BaseModel):
    """The `harness.frame_element_map/1` payload without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pairs: list[PairRow]
    ambiguous: list[AmbiguousRow]
    unmatched_frames: list[UnmatchedFrameRow]
    unmatched_elements: list[UnmatchedElementRow]
    conflicts: list[ConflictRow]
    complete: bool


def _refuse(path: str, why: str, code: ErrorCode = ErrorCode.INVALID_ARGUMENT, **fields: Any) -> ContractError:
    return ContractError(
        code,
        f"basis field {path} {why}",
        field=f"basis.fields.{path}",
        hint=f"set and confirm {path} in the design basis",
        **fields,
    )


def _require_length(basis: DesignBasis, basis_id: str, trace: TraceBuilder) -> Fraction:
    """Spec 0011 §4.11 / 0003 §4.4: `compare.length_mm` present, confirmed, in mm and >= 0."""
    field: BasisField | None = basis.fields.get(LENGTH)
    if field is None:
        raise _refuse(LENGTH, "is missing (no default)")
    if not field.confirmed:
        raise _refuse(LENGTH, "is not confirmed")
    if field.unit != ZERO.unit:
        raise _refuse(LENGTH, f"must be in {ZERO.unit}, not {field.unit}")
    value = as_fraction(field.value)
    if value is None:
        raise _refuse(LENGTH, "must be a number >= 0")
    if value < Fraction(ZERO.value):
        raise _refuse(
            LENGTH,
            "must be a number >= 0",
            ErrorCode.OUT_OF_RANGE,
            expected={"min": ZERO.value, "unit": ZERO.unit},
            received=field.value,
        )
    pointer = f"{basis_id}#/fields/{LENGTH}"
    trace.input(LENGTH.replace(".", "_"), float(value), unit=ZERO.unit, ref=pointer)
    return value


def _require_offset(basis: DesignBasis, path: str, basis_id: str, trace: TraceBuilder) -> Fraction:
    """Spec 0011 §4.11: each `mapping.offset_*` present, confirmed, in mm (signed; no default)."""
    field: BasisField | None = basis.fields.get(path)
    if field is None:
        raise _refuse(path, "is missing (no default)")
    if not field.confirmed:
        raise _refuse(path, "is not confirmed")
    if field.unit != ZERO.unit:
        raise _refuse(path, f"must be in {ZERO.unit}, not {field.unit}")
    value = as_fraction(field.value)
    if value is None:
        raise _refuse(path, "must be a number")
    pointer = f"{basis_id}#/fields/{path}"
    trace.input(path.replace(".", "_"), float(value), unit=ZERO.unit, ref=pointer)
    return value


Point = tuple[Fraction, Fraction, Fraction]
"""An exact (x, y, z) point in millimetres."""


def _squared(a: Point, b: Point) -> Fraction:
    """Exact squared distance between two points in millimetres (M2; 0003 §4.11 P2)."""
    return sum(((p - q) * (p - q) for p, q in zip(a, b, strict=True)), Fraction())


def _display(distance_sq: Fraction) -> float:
    """Display distance: sqrt of d² in float (spec 0011 §4.11)."""
    return math.sqrt(float(distance_sq))


def _elevation_key(point: Point) -> Point:
    x, y, z = point
    return z, x, y


def _ordered_ends(frame: Frame, offset: Point) -> tuple[Point, Point]:
    """M1: translate both ends exactly by `offset`, then order by elevation (then x, then y) into (lower, upper)."""
    ox, oy, oz = offset
    ends = [(Fraction(end.x_mm) + ox, Fraction(end.y_mm) + oy, Fraction(end.z_mm) + oz) for end in (frame.i, frame.j)]
    lower, upper = sorted(ends, key=_elevation_key)
    return lower, upper


def _within(distance_sq: Fraction, tolerance_sq: Fraction) -> bool:
    return distance_sq <= tolerance_sq


def _candidates(
    left_ends: Mapping[str, tuple[Point, Point]],
    right_ends: Mapping[str, tuple[Point, Point]],
    tolerance_sq: Fraction,
) -> dict[str, list[str]]:
    """M2: ids on the right whose lower and upper ends are each within the tolerance of the left id."""
    found: dict[str, list[str]] = {}
    for left_id, (left_lower, left_upper) in left_ends.items():
        matches: list[str] = []
        for right_id, (right_lower, right_upper) in right_ends.items():
            lower_ok = _within(_squared(left_lower, right_lower), tolerance_sq)
            upper_ok = _within(_squared(left_upper, right_upper), tolerance_sq)
            if lower_ok and upper_ok:
                matches.append(right_id)
        found[left_id] = sorted(matches)
    return found


def _require_ref(meta: InputMeta, field: str) -> Any:
    ref = meta.refs.get(field)
    if ref is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "a placement must be a record reference", field=field)
    return ref


@calc(
    id="harness.frame_element_map",
    version=int(VERSION.value),
    output_kind="harness.frame_element_map/1",
    title="Map ETABS frames to Revit elements by geometry and structure ids",
    method_source="eng-harness spec 0011 §4.11 (M1 to M6); OQ-Q104 structure join",
    verification="draft",
)
def frame_element_map(inp: FrameElementMapInput, meta: InputMeta, trace: TraceBuilder) -> FrameElementMapBody:
    """Apply M1 to M6, then join matched pairs to `structure` for host element and type ids."""
    if (basis_ref := meta.refs.get("basis")) is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "the basis must be a record reference", field="basis")
    frames_ref = _require_ref(meta, "frames")
    elements_ref = _require_ref(meta, "elements")
    structure_ref = _require_ref(meta, "structure")
    tolerance = _require_length(inp.basis, basis_ref.result_id, trace)
    ox = _require_offset(inp.basis, OFFSET_X, basis_ref.result_id, trace)
    oy = _require_offset(inp.basis, OFFSET_Y, basis_ref.result_id, trace)
    oz = _require_offset(inp.basis, OFFSET_Z, basis_ref.result_id, trace)
    tolerance_sq = tolerance * tolerance
    complete = basis_ref.complete and frames_ref.complete and elements_ref.complete and structure_ref.complete
    trace.input("frames", len(inp.frames.frames), ref=frames_ref.result_id)
    trace.input("elements", len(inp.elements.frames), ref=elements_ref.result_id)
    trace.input("structure", len(inp.structure.elements), ref=structure_ref.result_id)

    no_offset: Point = (Fraction(), Fraction(), Fraction())
    frame_ends = {frame.id: _ordered_ends(frame, (ox, oy, oz)) for frame in inp.frames.frames}
    element_ends = {frame.id: _ordered_ends(frame, no_offset) for frame in inp.elements.frames}
    frame_to_elements = _candidates(frame_ends, element_ends, tolerance_sq)
    element_to_frames = _candidates(element_ends, frame_ends, tolerance_sq)

    matched: dict[str, str] = {}
    matched_distances: dict[str, tuple[Fraction, Fraction]] = {}
    ambiguous: list[AmbiguousRow] = []
    seen_frames: set[str] = set()
    seen_elements: set[str] = set()

    for frame_id, candidates in sorted(frame_to_elements.items()):
        if len(candidates) != 1:
            continue
        unique_id = candidates[0]
        reverse = element_to_frames[unique_id]
        if len(reverse) == 1 and reverse[0] == frame_id:
            lower_sq = _squared(frame_ends[frame_id][0], element_ends[unique_id][0])
            upper_sq = _squared(frame_ends[frame_id][1], element_ends[unique_id][1])
            matched[frame_id] = unique_id
            matched_distances[frame_id] = (lower_sq, upper_sq)
            seen_frames.add(frame_id)
            seen_elements.add(unique_id)

    for frame_id, candidates in sorted(frame_to_elements.items()):
        if len(candidates) > 1:
            ambiguous.append(AmbiguousRow(side="frame", id=frame_id, candidates=candidates))
            seen_frames.add(frame_id)
            seen_elements.update(candidates)
    for unique_id, candidates in sorted(element_to_frames.items()):
        if len(candidates) > 1:
            ambiguous.append(AmbiguousRow(side="element", id=unique_id, candidates=candidates))
            seen_elements.add(unique_id)
            seen_frames.update(candidates)

    unmatched_frames = [
        UnmatchedFrameRow(frame_id=frame_id) for frame_id in sorted(frame_ends) if frame_id not in seen_frames
    ]
    unmatched_elements = [
        UnmatchedElementRow(unique_id=unique_id) for unique_id in sorted(element_ends) if unique_id not in seen_elements
    ]

    links: Mapping[str, str] = inp.links or {}
    conflicts: list[ConflictRow] = []
    conflicted_frames: set[str] = set()
    for unique_id, frame_id in sorted(links.items()):
        if frame_id not in frame_ends:
            continue  # M4: only a link naming a frame of `frames` is checked against geometry
        geometric = matched.get(frame_id)
        if geometric != unique_id:
            conflicts.append(ConflictRow(frame_id=frame_id, unique_id=unique_id, geometric_unique_id=geometric))
            if frame_id in matched:
                conflicted_frames.add(frame_id)
    for frame_id in conflicted_frames:
        del matched[frame_id]
        del matched_distances[frame_id]

    by_unique = {row.unique_id: row for row in inp.structure.elements}
    pairs: list[PairRow] = []
    for frame_id, unique_id in sorted(matched.items()):
        row = by_unique.get(unique_id)
        if row is None:
            conflicts.append(ConflictRow(frame_id=frame_id, unique_id=unique_id, geometric_unique_id=unique_id))
            continue
        link_frame = links.get(unique_id)
        pair_basis: PairBasis = "both" if link_frame == frame_id else "geometry"
        lower_sq, upper_sq = matched_distances[frame_id]
        pairs.append(
            PairRow(
                frame_id=frame_id,
                unique_id=unique_id,
                element_id=row.element_id,
                type_id=row.type_id,
                basis=pair_basis,
                lower_distance_mm=_display(lower_sq),
                upper_distance_mm=_display(upper_sq),
            )
        )

    ambiguous = sorted(ambiguous, key=lambda row: (row.side, row.id))
    conflicts = sorted(conflicts, key=lambda row: (row.frame_id, row.unique_id))
    pairs = sorted(pairs, key=lambda row: row.frame_id)
    trace.step(
        "pairs",
        len(pairs),
        formula="M1 to M6 geometric pairing then structure join on unique_id",
        source="§4.11 M1-M6",
        uses=["compare_length_mm", "mapping_offset_x_mm", "mapping_offset_y_mm", "mapping_offset_z_mm"],
    )
    trace.output("pairs")
    return FrameElementMapBody(
        pairs=pairs,
        ambiguous=ambiguous,
        unmatched_frames=unmatched_frames,
        unmatched_elements=unmatched_elements,
        conflicts=conflicts,
        complete=complete,
    )
