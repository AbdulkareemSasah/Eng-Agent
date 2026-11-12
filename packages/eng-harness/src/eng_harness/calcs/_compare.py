"""Comparison core of the difference report (spec 0003 4.7 rules D2 to D5; the calc itself applies D1, D6 and D7).

Purpose: match the objects of two model state sections by their D2 keys and compare matched objects member by member
(D5), numbers within a tolerance of their quantity kind, exactly as `Fraction`s (D3), everything else exactly (D4).
Units: a tolerance is in the canonical unit of its quantity kind (`kind_for_field`); values are not converted (D6).
Errors: `KeyError` for a keyed list the payload lacks; `TypeError` for a key member that is not a string.
The D2 keys live here, not in `_state.py`: a change there would change the content hash of `harness.model_fingerprint`.
"""

from collections.abc import Iterator, Mapping
from fractions import Fraction
from math import isfinite
from typing import Any, Literal, NamedTuple

from eng_contract.canonical import canonical_json
from eng_contract.units import kind_for_field

from eng_harness.calcs._state import ORDER
from eng_harness.kinds.calcs import Change, PropertyRow, SectionCounts, WithinRow

__all__ = [
    "ROW_KEYS",
    "SectionDiff",
    "as_fraction",
    "compare_property",
    "compare_rows",
    "compare_section",
    "row_key",
    "section_counts",
    "walk_leaves",
    "within_tolerance",
]

ROW_KEYS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("model.stories/1", ("stories",), ("name",)),
    *((kind, path, (key,)) for kind, path, key in ORDER if key is not None),
    ("model.load_set/1", ("combinations", "items"), ("case.case", "case.case_type", "case.step")),
    ("model.load_set/1", ("frame_loads",), ("frame", "pattern", "direction")),
    ("model.load_set/1", ("area_loads",), ("area", "pattern", "direction")),
)
"""The D2 table: kind, path of the list (as in the F2 `ORDER`), key members (a dotted member is nested in the row)."""

Tolerances = Mapping[str, Fraction]
"""Tolerance per quantity kind name (`length`, `angle`, ...), from the design basis `compare.*` fields (spec 4.4)."""


class SectionDiff(NamedTuple):
    """Changes and within-tolerance rows of one section, and one outcome per compared object (for the counts)."""

    changes: list[Change]
    within: list[WithinRow]
    outcomes: list[str]


def row_key(members: tuple[str, ...], row: dict[str, Any]) -> tuple[str, ...]:
    """The D2 key of `row`: its key members in order, exactly as stored; a null or absent member is left out."""
    found: list[str] = []
    for member in members:
        value: Any = row
        for part in member.split("."):
            value = value.get(part)
        if value is None:
            continue
        if not isinstance(value, str):
            raise TypeError(f"key member {member!r} is not a string")
        found.append(value)
    return tuple(found)


def as_fraction(value: Any) -> Fraction | None:
    """The exact value of a finite JSON number; a boolean, a non-finite float or a non-number gives `None`."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return Fraction(value) if isfinite(value) else None


def within_tolerance(before: Fraction, after: Fraction, tolerance: Fraction) -> bool:
    """D3: equal when |after - before| <= tolerance, exactly; a tolerance of zero needs exact equality."""
    return abs(after - before) <= tolerance


def _same(before: Any, after: Any) -> bool:
    """Identical as canonical JSON bytes (so `0` and `0.0` are the same and `True` is not `1`)."""
    return canonical_json(before) == canonical_json(after)


def _utf16(key: str) -> bytes:
    return key.encode("utf-16-be", "surrogatepass")


def walk_leaves(before: Any, after: Any, pointer: str = "") -> Iterator[tuple[str, Any, Any]]:
    """D5 leaves of two values: objects member by member, ordered lists index by index, as JSON pointers.

    A list whose length changed, a nested object whose `type` changed (D4, the tagged `shape` of the 0.1 kinds) and a
    value whose JSON type changed are one leaf at the enclosing pointer. A member missing on one side is `None`.
    """
    if (
        isinstance(before, dict)
        and isinstance(after, dict)
        and (not pointer or before.get("type") == after.get("type"))
    ):
        for key in sorted(before.keys() | after.keys(), key=_utf16):
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from walk_leaves(before.get(key), after.get(key), f"{pointer}/{escaped}")
    elif isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            yield from walk_leaves(left, right, f"{pointer}/{index}")
    else:
        yield pointer, before, after


def compare_property(pointer: str, before: Any, after: Any, tolerances: Tolerances) -> tuple[PropertyRow, bool]:
    """The row of one differing leaf, and whether it is equal within tolerance (D3) rather than changed."""
    leaf = pointer.rpartition("/")[-1].replace("~1", "/").replace("~0", "~")
    quantity = kind_for_field(leaf)
    kind, unit = (quantity.name, quantity.canonical_unit) if quantity else (None, None)
    left, right = as_fraction(before), as_fraction(after)
    tolerance = tolerances.get(kind) if kind else None
    if tolerance is not None and left is not None and right is not None:
        near = within_tolerance(left, right, tolerance)
        row = PropertyRow(
            pointer=pointer,
            before=before,
            after=after,
            unit=unit,
            quantity_kind=kind,
            tolerance=float(tolerance),
            rule="D3",
        )
        return row, near
    rule = "D5" if isinstance(before, list) and isinstance(after, list) else "D4"
    row = PropertyRow(
        pointer=pointer, before=before, after=after, unit=unit, quantity_kind=kind, tolerance=None, rule=rule
    )
    return row, False


def _diff_object(
    before: dict[str, Any], after: dict[str, Any], skip: frozenset[str], tolerances: Tolerances
) -> tuple[list[PropertyRow], list[PropertyRow]]:
    """Changed and within-tolerance rows of two matched objects; members in `skip` (keyed sub-lists) are left out."""
    changed: list[PropertyRow] = []
    near: list[PropertyRow] = []
    kept_before = {k: v for k, v in before.items() if k not in skip}
    kept_after = {k: v for k, v in after.items() if k not in skip}
    for pointer, left, right in walk_leaves(kept_before, kept_after):
        if not _same(left, right):
            row, within = compare_property(pointer, left, right, tolerances)
            (near if within else changed).append(row)
    return changed, near


def _merge(into: SectionDiff, part: SectionDiff) -> None:
    into.changes.extend(part.changes)
    into.within.extend(part.within)
    into.outcomes.extend(part.outcomes)


def _children(kind: str, path: tuple[str, ...]) -> tuple[str, ...]:
    """Names of the keyed lists nested directly under the rows of the list at `path`."""
    return tuple(p[-1] for k, p, _ in ROW_KEYS if k == kind and p[:-1] == path)


def _matched(
    kind: str,
    path: tuple[str, ...],
    key: tuple[str, ...],
    before: dict[str, Any],
    after: dict[str, Any],
    tolerances: Tolerances,
) -> SectionDiff:
    """One object on each side under `key`: its own properties, then its keyed sub-lists under the same key."""
    children = _children(kind, path)
    changed, near = _diff_object(before, after, frozenset(children), tolerances)
    diff = SectionDiff(
        changes=[Change(section=kind, key=list(key), change="changed", before=None, after=None, properties=changed)]
        if changed
        else [],
        within=[WithinRow(section=kind, key=list(key), **row.model_dump()) for row in near],
        outcomes=["changed" if changed else "unchanged"],
    )
    for child in children:
        _merge(diff, compare_rows(kind, (*path, child), before[child], after[child], tolerances, prefix=key))
    return diff


def compare_rows(
    kind: str,
    path: tuple[str, ...],
    before: list[Any],
    after: list[Any],
    tolerances: Tolerances,
    prefix: tuple[str, ...] = (),
) -> SectionDiff:
    """D2: match the rows of the keyed list at `path` of a `kind` section by key, in key order.

    A key on one side only is `added` or `removed` (whole object). A key that occurs more than once on a side is
    `ambiguous` with both object lists, even when both sides are byte-identical (AC28: never unchanged; D7).
    A key once on each side is compared member by member; its nested keyed lists are compared under the parent key
    (`prefix` + key).
    """
    members = next(fields for k, p, fields in ROW_KEYS if k == kind and p == path)
    groups: dict[tuple[str, ...], tuple[list[Any], list[Any]]] = {}
    for side, rows in enumerate((before, after)):
        for row in rows:
            groups.setdefault((*prefix, *row_key(members, row)), ([], []))[side].append(row)
    diff = SectionDiff(changes=[], within=[], outcomes=[])
    for key in sorted(groups):
        left, right = groups[key]
        change: Literal["added", "removed", "ambiguous"]
        old: Any
        new: Any
        if len(left) == len(right) == 1:
            _merge(diff, _matched(kind, path, key, left[0], right[0], tolerances))
            continue
        if len(left) > 1 or len(right) > 1:
            change, old, new = "ambiguous", left, right
        elif right:
            change, old, new = "added", None, right[0]
        else:
            change, old, new = "removed", left[0], None
        diff.changes.append(Change(section=kind, key=list(key), change=change, before=old, after=new, properties=[]))
        diff.outcomes.append(change)
    return diff


def compare_section(kind: str, before: dict[str, Any], after: dict[str, Any], tolerances: Tolerances) -> SectionDiff:
    """Compare two payloads of one section: its own members (key `[]`), then each top-level keyed list (D2 to D5).

    The section's own members count as an object only when one of them changed. Changes and rows are in key order.
    """
    lists = tuple(path for k, path, _ in ROW_KEYS if k == kind and len(path) == 1)
    changed, near = _diff_object(before, after, frozenset(p[0] for p in lists), tolerances)
    diff = SectionDiff(
        changes=[Change(section=kind, key=[], change="changed", before=None, after=None, properties=changed)]
        if changed
        else [],
        within=[WithinRow(section=kind, key=[], **row.model_dump()) for row in near],
        outcomes=["changed"] if changed else [],
    )
    for path in lists:
        _merge(diff, compare_rows(kind, path, before[path[0]], after[path[0]], tolerances))
    diff.changes.sort(key=lambda change: tuple(change.key))
    diff.within.sort(key=lambda row: (tuple(row.key), row.pointer))
    return diff


def section_counts(diff: SectionDiff) -> SectionCounts:
    """The per-section counts of a difference report: outcomes by kind, and the within-tolerance rows."""
    return SectionCounts(
        added=diff.outcomes.count("added"),
        removed=diff.outcomes.count("removed"),
        changed=diff.outcomes.count("changed"),
        ambiguous=diff.outcomes.count("ambiguous"),
        unchanged=diff.outcomes.count("unchanged"),
        within_tolerance=len(diff.within),
    )
