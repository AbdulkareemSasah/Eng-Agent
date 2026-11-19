"""Calc 6, element count and position comparison `harness.placement_compare` v1 (spec 0003 4.11, rules P1 to P6).

Purpose: A1 and A5 for geometry; covers renamed or reversed objects that the difference report cannot show.
Inputs: `a_frames` / `b_frames` (`model.frame_placements/1`) and/or `a_areas` / `b_areas` (`model.area_placements/1`),
same sections on both sides, and `basis` (`compare.length_mm`). `a_*` is `stale_ok` (section 4.13).
Units: millimetres; distances compared as exact squared `Fraction`s (P2); `distance_mm` is `sqrt` of `d²` in float.
Errors: `ContractError` `INVALID_ARGUMENT` for a basis given without a record, a basis field missing, unconfirmed,
wrong unit or not a number >= 0, a placement without a record reference, or mismatched side sections.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any, Literal

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import BasisField, DesignBasis
from eng_contract.kinds.model import Area, AreaPlacements, Frame, FramePlacements
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict, model_validator

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.calcs import Ambiguous, ByIdRow, CountRow, OneSided, Renamed

__all__ = ["BASIS_FIELDS", "PlacementBody", "PlacementInput", "placement_compare"]

LENGTH = "compare.length_mm"
BASIS_FIELDS = (LENGTH,)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""
ZERO = Cited(value=0, unit="mm", source="eng-harness spec 0003 §4.4: compare.length_mm is >= 0")
"""Lower bound of `compare.length_mm` (inclusive)."""
VERSION = Cited(
    value=1, unit="1", source="Calc version 1 of eng-harness spec 0003 §4.11; a method change is a new version"
)
UNASSIGNED = "unassigned"
"""Story name used when `story` is null (spec 0003 §4.11 counts; a real story with this name shares the bucket)."""
FRAME_TYPES: tuple[str, ...] = ("beam", "brace", "column", "other")
AREA_TYPES: tuple[str, ...] = ("deck", "other", "slab", "wall")
_MATCH = frozenset({"same", "reversed"})
ElementName = Literal["frame", "area"]
GeomResult = Literal["same", "reversed", "moved", "reshaped"]


class PlacementInput(CalcInput):
    """Two placement sides and the length tolerance; each side needs frames, areas or both, the same on both sides."""

    a_frames: FramePlacements | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.frame_placements/1"}, engineering_quantity=True, stale_ok=True
    )
    b_frames: FramePlacements | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.frame_placements/1"}, engineering_quantity=True, stale_ok=False
    )
    a_areas: AreaPlacements | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.area_placements/1"}, engineering_quantity=True, stale_ok=True
    )
    b_areas: AreaPlacements | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.area_placements/1"}, engineering_quantity=True, stale_ok=False
    )
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)

    @model_validator(mode="after")
    def _same_sections(self) -> PlacementInput:
        if self.a_frames is None and self.b_frames is None and self.a_areas is None and self.b_areas is None:
            raise ValueError("each side needs frames, areas or both")
        if (self.a_frames is None) != (self.b_frames is None):
            raise ValueError("frames must be present on both sides or on neither")
        if (self.a_areas is None) != (self.b_areas is None):
            raise ValueError("areas must be present on both sides or on neither")
        return self


class PlacementBody(BaseModel):
    """The `harness.placement_comparison/1` payload without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    counts: list[CountRow]
    by_id: list[ByIdRow]
    renamed: list[Renamed]
    ambiguous: list[Ambiguous]
    only_in_a: list[OneSided]
    only_in_b: list[OneSided]
    equal: bool
    complete: bool


def _refuse(path: str, why: str, code: ErrorCode = ErrorCode.INVALID_ARGUMENT, **fields: Any) -> ContractError:
    return ContractError(
        code,
        f"basis field {path} {why}",
        field=f"basis.fields.{path}",
        hint=f"set and confirm {path} in the design basis",
        **fields,
    )


def _length(basis: DesignBasis, basis_id: str, trace: TraceBuilder) -> Fraction:
    """Spec 4.4: `compare.length_mm` present, confirmed, in mm and >= 0."""
    field: BasisField | None = basis.fields.get(LENGTH)
    if field is None:
        raise _refuse(LENGTH, "is missing (no default)")
    if not field.confirmed:
        raise _refuse(LENGTH, "is not confirmed")
    if field.unit != ZERO.unit:
        raise _refuse(LENGTH, f"must be in {ZERO.unit}, not {field.unit}")
    value = as_fraction(field.value)
    if value is None or value < Fraction(ZERO.value):
        raise _refuse(
            LENGTH,
            "must be a number >= 0",
            expected={"min": ZERO.value, "unit": ZERO.unit},
            received=field.value,
        )
    pointer = f"{basis_id}#/fields/{LENGTH}"
    trace.input(LENGTH.replace(".", "_"), float(value), unit=ZERO.unit, ref=pointer)
    return value


def _squared(a: Any, b: Any) -> Fraction:
    """P2: exact squared distance between two `Point3` values in millimetres."""
    dx = Fraction(a.x_mm) - Fraction(b.x_mm)
    dy = Fraction(a.y_mm) - Fraction(b.y_mm)
    dz = Fraction(a.z_mm) - Fraction(b.z_mm)
    return dx * dx + dy * dy + dz * dz


def _within(distance_sq: Fraction, tolerance_sq: Fraction) -> bool:
    return distance_sq <= tolerance_sq


def _display(distance_sq: Fraction) -> float:
    """P2: `distance_mm` is sqrt of d² in float, for display only."""
    return math.sqrt(float(distance_sq))


def _max_sq(first: Fraction, second: Fraction) -> Fraction:
    return first if first >= second else second


def _frame_result(a: Frame, b: Frame, tolerance_sq: Fraction) -> tuple[GeomResult, float]:
    """P3: same, reversed or moved for a common frame id."""
    same_i, same_j = _squared(a.i, b.i), _squared(a.j, b.j)
    if _within(same_i, tolerance_sq) and _within(same_j, tolerance_sq):
        return "same", _display(_max_sq(same_i, same_j))
    rev_i, rev_j = _squared(a.i, b.j), _squared(a.j, b.i)
    if _within(rev_i, tolerance_sq) and _within(rev_j, tolerance_sq):
        return "reversed", _display(_max_sq(rev_i, rev_j))
    return "moved", _display(_max_sq(same_i, same_j))


def _shift_distance(a_points: Sequence[Any], b_points: Sequence[Any], shift: int) -> Fraction:
    """Largest squared point distance when b is read from index `shift` in order."""
    largest = Fraction()
    for index, point in enumerate(a_points):
        candidate = b_points[(index + shift) % len(b_points)]
        distance = _squared(point, candidate)
        if distance > largest:
            largest = distance
    return largest


def _area_result(a: Area, b: Area, tolerance_sq: Fraction) -> tuple[GeomResult, float | None]:
    """P4: same, reversed, reshaped or moved for a common area id."""
    if len(a.points) != len(b.points):
        return "reshaped", None
    for shift in range(len(a.points)):
        distance = _shift_distance(a.points, b.points, shift)
        if _within(distance, tolerance_sq):
            return "same", _display(distance)
    reversed_points = list(reversed(b.points))
    for shift in range(len(a.points)):
        distance = _shift_distance(a.points, reversed_points, shift)
        if _within(distance, tolerance_sq):
            return "reversed", _display(distance)
    moved_sq = max((_squared(p, q) for p, q in zip(a.points, b.points, strict=True)), default=Fraction())
    return "moved", _display(moved_sq)


def _story_name(story: str | None) -> str:
    """Map null story to `unassigned` (a real story named 'unassigned' shares this bucket)."""
    return UNASSIGNED if story is None else story


def _count_rows(
    element: ElementName,
    types: tuple[str, ...],
    a_items: Sequence[Any],
    b_items: Sequence[Any],
) -> list[CountRow]:
    """P1: type rows for every kind of the element class, and story rows for names that appear plus unassigned."""
    rows: list[CountRow] = []
    a_types = {name: len([item for item in a_items if item.kind.value == name]) for name in types}
    b_types = {name: len([item for item in b_items if item.kind.value == name]) for name in types}
    for name in types:
        a_n, b_n = a_types[name], b_types[name]
        rows.append(CountRow(element=element, by="type", name=name, a=a_n, b=b_n, difference=b_n - a_n))
    stories = sorted({_story_name(item.story) for item in (*a_items, *b_items)} | {UNASSIGNED})
    for name in stories:
        a_n = len([item for item in a_items if _story_name(item.story) == name])
        b_n = len([item for item in b_items if _story_name(item.story) == name])
        rows.append(CountRow(element=element, by="story", name=name, a=a_n, b=b_n, difference=b_n - a_n))
    return rows


def _pair_geometry(
    element: ElementName,
    a_only: Mapping[str, Any],
    b_only: Mapping[str, Any],
    tolerance_sq: Fraction,
) -> tuple[list[Renamed], list[Ambiguous], list[OneSided], list[OneSided]]:
    """P5: rename mutual unique geometric partners; list ambiguous candidates; only unmatched ids are one-sided."""

    def partners(left: Any, rights: Mapping[str, Any]) -> list[str]:
        found: list[str] = []
        for other_id, other in rights.items():
            result: GeomResult = (
                _frame_result(left, other, tolerance_sq)[0]
                if element == "frame"
                else _area_result(left, other, tolerance_sq)[0]
            )
            if result in _MATCH:
                found.append(other_id)
        return sorted(found)

    a_to_b = {item_id: partners(item, b_only) for item_id, item in a_only.items()}
    b_to_a = {item_id: partners(item, a_only) for item_id, item in b_only.items()}
    renamed: list[Renamed] = []
    seen_a: set[str] = set()
    seen_b: set[str] = set()
    for a_id, candidates in sorted(a_to_b.items()):
        if len(candidates) != 1:
            continue
        b_id = candidates[0]
        reverse = b_to_a[b_id]
        if len(reverse) == 1 and reverse[0] == a_id:
            renamed.append(Renamed(element=element, a_id=a_id, b_id=b_id))
            seen_a.add(a_id)
            seen_b.add(b_id)
    ambiguous: list[Ambiguous] = []
    for a_id, candidates in sorted(a_to_b.items()):
        if len(candidates) > 1:
            ambiguous.append(Ambiguous(element=element, side="a", id=a_id, candidates=candidates))
            seen_a.add(a_id)
            seen_b.update(candidates)
    for b_id, candidates in sorted(b_to_a.items()):
        if len(candidates) > 1:
            ambiguous.append(Ambiguous(element=element, side="b", id=b_id, candidates=candidates))
            seen_b.add(b_id)
            seen_a.update(candidates)
    only_a = [OneSided(element=element, id=item_id) for item_id in sorted(a_only) if item_id not in seen_a]
    only_b = [OneSided(element=element, id=item_id) for item_id in sorted(b_only) if item_id not in seen_b]
    return renamed, ambiguous, only_a, only_b


def _require_ref(meta: InputMeta, field: str) -> Any:
    ref = meta.refs.get(field)
    if ref is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "a placement must be a record reference", field=field)
    return ref


@calc(
    id="harness.placement_compare",
    version=int(VERSION.value),
    output_kind="harness.placement_comparison/1",
    title="Element count and position comparison of two placement sets",
    method_source="eng-harness spec 0003 §4.11 (P1 to P6); 18 §4 A1 and A5",
    verification="draft",
)
def placement_compare(inp: PlacementInput, meta: InputMeta, trace: TraceBuilder) -> PlacementBody:
    """Read the length tolerance, compare common ids (P3, P4), pair unmatched ones (P5) and assemble counts (P1, P6)."""
    if (basis := meta.refs.get("basis")) is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "the basis must be a record reference", field="basis")
    tolerance = _length(inp.basis, basis.result_id, trace)
    tolerance_sq = tolerance * tolerance
    complete = basis.complete
    counts: list[CountRow] = []
    by_id: list[ByIdRow] = []
    renamed: list[Renamed] = []
    ambiguous: list[Ambiguous] = []
    only_in_a: list[OneSided] = []
    only_in_b: list[OneSided] = []

    if inp.a_frames is not None and inp.b_frames is not None:
        a_ref, b_ref = _require_ref(meta, "a_frames"), _require_ref(meta, "b_frames")
        complete = complete and a_ref.complete and b_ref.complete
        trace.input("a_frames", len(inp.a_frames.frames), ref=a_ref.result_id)
        trace.input("b_frames", len(inp.b_frames.frames), ref=b_ref.result_id)
        frames_a = {frame.id: frame for frame in inp.a_frames.frames}
        frames_b = {frame.id: frame for frame in inp.b_frames.frames}
        counts += _count_rows("frame", FRAME_TYPES, inp.a_frames.frames, inp.b_frames.frames)
        for item_id in sorted(set(frames_a) & set(frames_b)):
            result, distance = _frame_result(frames_a[item_id], frames_b[item_id], tolerance_sq)
            by_id.append(ByIdRow(element="frame", id=item_id, result=result, distance_mm=distance))
        frame_only_a_map = {item_id: frames_a[item_id] for item_id in frames_a if item_id not in frames_b}
        frame_only_b_map = {item_id: frames_b[item_id] for item_id in frames_b if item_id not in frames_a}
        frame_renamed, frame_ambiguous, frame_only_a, frame_only_b = _pair_geometry(
            "frame", frame_only_a_map, frame_only_b_map, tolerance_sq
        )
        renamed += frame_renamed
        ambiguous += frame_ambiguous
        only_in_a += frame_only_a
        only_in_b += frame_only_b

    if inp.a_areas is not None and inp.b_areas is not None:
        a_ref, b_ref = _require_ref(meta, "a_areas"), _require_ref(meta, "b_areas")
        complete = complete and a_ref.complete and b_ref.complete
        trace.input("a_areas", len(inp.a_areas.areas), ref=a_ref.result_id)
        trace.input("b_areas", len(inp.b_areas.areas), ref=b_ref.result_id)
        areas_a = {area.id: area for area in inp.a_areas.areas}
        areas_b = {area.id: area for area in inp.b_areas.areas}
        counts += _count_rows("area", AREA_TYPES, inp.a_areas.areas, inp.b_areas.areas)
        for item_id in sorted(set(areas_a) & set(areas_b)):
            area_result, area_distance = _area_result(areas_a[item_id], areas_b[item_id], tolerance_sq)
            by_id.append(ByIdRow(element="area", id=item_id, result=area_result, distance_mm=area_distance))
        area_only_a_map = {item_id: areas_a[item_id] for item_id in areas_a if item_id not in areas_b}
        area_only_b_map = {item_id: areas_b[item_id] for item_id in areas_b if item_id not in areas_a}
        area_renamed, area_ambiguous, area_only_a, area_only_b = _pair_geometry(
            "area", area_only_a_map, area_only_b_map, tolerance_sq
        )
        renamed += area_renamed
        ambiguous += area_ambiguous
        only_in_a += area_only_a
        only_in_b += area_only_b

    counts = sorted(counts, key=lambda row: (row.element, row.by, row.name))
    by_id = sorted(by_id, key=lambda row: (row.element, row.id))
    renamed = sorted(renamed, key=lambda row: (row.element, row.a_id, row.b_id))
    ambiguous = sorted(ambiguous, key=lambda row: (row.element, row.side, row.id))
    only_in_a = sorted(only_in_a, key=lambda row: (row.element, row.id))
    only_in_b = sorted(only_in_b, key=lambda row: (row.element, row.id))
    equal = (
        all(row.a == row.b for row in counts)
        and all(row.result == "same" for row in by_id)
        and not renamed
        and not ambiguous
        and not only_in_a
        and not only_in_b
    )
    trace.step(
        "equal",
        equal,
        formula="every count difference zero, every by_id same, nothing renamed, ambiguous or one-sided",
        source="§4.11 P6",
        uses=["compare_length_mm"],
    )
    trace.output("equal")
    return PlacementBody(
        counts=counts,
        by_id=by_id,
        renamed=renamed,
        ambiguous=ambiguous,
        only_in_a=only_in_a,
        only_in_b=only_in_b,
        equal=equal,
        complete=complete,
    )
