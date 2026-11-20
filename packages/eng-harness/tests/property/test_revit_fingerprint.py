"""Revit state fingerprint properties (plan 0011 T7; spec 0011 AC10, §4.9).

The fingerprint is over the raw read-set replies (not converted payloads), order-independent by
unique_id / element_id, and excludes file save time and the total element count.
"""

from __future__ import annotations

import copy
from typing import Any

from hypothesis import assume, given, settings
from hypothesis import strategies as st

_coord = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False).map(lambda v: v + 0.0)
_label = st.text("ABCDEFGHJ0123456789", min_size=1, max_size=4)


@st.composite
def _element_row(draw: st.DrawFn) -> dict[str, Any]:
    """One raw element slice of the fingerprint read set (spec 0011 §4.9)."""
    uid = draw(_label) + draw(_label)
    return {
        "unique_id": uid,
        "element_id": draw(st.integers(1, 10_000)),
        "type_id": draw(st.integers(1, 10_000)),
        "type_name": draw(_label),
        "level_id": draw(st.integers(1, 100)),
        "location": {
            "kind": draw(st.sampled_from(["point", "curve"])),
            "i": [draw(_coord) for _ in range(3)],
            "j": [draw(_coord) for _ in range(3)],
        },
        "parameters": {
            "section_b": {"rawValue": draw(_coord)},
            "rotation": {"rawValue": draw(_coord)},
        },
    }


@st.composite
def _level_row(draw: st.DrawFn) -> dict[str, Any]:
    return {
        "element_id": draw(st.integers(1, 10_000)),
        "name": draw(_label),
        "elevation_mm": draw(_coord),
    }


@st.composite
def _grid_row(draw: st.DrawFn) -> dict[str, Any]:
    return {
        "element_id": draw(st.integers(1, 10_000)),
        "name": draw(_label),
        "start": [draw(_coord) for _ in range(3)],
        "end": [draw(_coord) for _ in range(3)],
        "length_mm": draw(_coord),
    }


@st.composite
def revit_read_sets(draw: st.DrawFn) -> dict[str, Any]:
    """Synthetic raw read set for the Revit fingerprint (no project value; no save time or counts)."""
    elements = draw(st.lists(_element_row(), min_size=1, max_size=4, unique_by=lambda row: row["unique_id"]))
    types = [
        {
            "type_id": row["type_id"],
            "type_name": row["type_name"],
            "parameters": {"section_b": {"rawValue": draw(_coord)}, "section_h": {"rawValue": draw(_coord)}},
        }
        for row in elements
    ]
    return {
        "levels": draw(st.lists(_level_row(), min_size=1, max_size=3, unique_by=lambda row: row["element_id"])),
        "grids": draw(st.lists(_grid_row(), min_size=1, max_size=3, unique_by=lambda row: row["element_id"])),
        "elements": elements,
        "types": types,
    }


def _mixed(data: st.DataObject, value: Any) -> Any:
    """Reorder object keys and lists of objects; keep list-of-number order."""
    if isinstance(value, dict):
        return {k: _mixed(data, v) for k, v in data.draw(st.permutations(list(value.items())))}
    if isinstance(value, list):
        items = [_mixed(data, item) for item in value]
        if items and all(isinstance(item, dict) for item in items):
            return list(data.draw(st.permutations(items)))
        return items
    return value


EDITS = (
    "type_name",
    "parameter",
    "location",
    "level_elevation",
    "grid",
    "add_element",
    "drop_element",
)


@settings(derandomize=True, max_examples=80, deadline=None)
@given(revit_read_sets(), st.sampled_from(EDITS), st.data())
def test_order_independent_and_edit_sensitive(read: dict[str, Any], edit: str, data: st.DataObject) -> None:
    """AC10: same fingerprint under any element order; any read-set edit changes it; counts/save time excluded."""
    from eng_harness.adapters.revit._state import fingerprint

    base = fingerprint(read)
    assert len(base) == 64
    assert fingerprint(_mixed(data, read)) == base

    # Excluded fields must not affect the digest (spec 0011 §4.9 / AC10).
    with_noise = copy.deepcopy(read)
    with_noise["save_time"] = "2026-01-01T00:00:00Z"
    with_noise["element_count"] = 999_999
    assert fingerprint(with_noise) == base

    changed = copy.deepcopy(read)
    if edit == "type_name":
        changed["elements"][0]["type_name"] += "x"
    elif edit == "parameter":
        row = changed["elements"][0]["parameters"]["section_b"]
        row["rawValue"] = data.draw(_coord.filter(lambda v: v != row["rawValue"]))
    elif edit == "location":
        point = changed["elements"][0]["location"]["i"]
        idx = data.draw(st.integers(0, 2))
        point[idx] = data.draw(_coord.filter(lambda v: v != point[idx]))
    elif edit == "level_elevation":
        level = changed["levels"][0]
        level["elevation_mm"] = data.draw(_coord.filter(lambda v: v != level["elevation_mm"]))
    elif edit == "grid":
        grid = changed["grids"][0]
        grid["length_mm"] = data.draw(_coord.filter(lambda v: v != grid["length_mm"]))
    elif edit == "add_element":
        extra = data.draw(_element_row())
        assume(extra["unique_id"] not in {row["unique_id"] for row in changed["elements"]})
        changed["elements"].append(extra)
    else:
        assume(len(changed["elements"]) > 1)
        changed["elements"].pop()
    assert fingerprint(changed) != base
