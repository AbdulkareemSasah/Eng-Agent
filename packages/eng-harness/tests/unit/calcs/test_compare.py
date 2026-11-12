"""Comparison core of the difference report (plan 0003 T8; spec 0003 4.7 rules D2 to D5) on synthetic rows.

Every tolerance below is synthetic (spec 4.7 verification cases: "the synthetic tolerance"); none is a project value.
Expected values are derived by hand in the comments from D2 to D5, never computed by the code under test.
"""

import math
from fractions import Fraction
from typing import Any

import pytest

from eng_harness.calcs._compare import (
    ROW_KEYS,
    SectionDiff,
    as_fraction,
    compare_property,
    compare_rows,
    compare_section,
    row_key,
    section_counts,
    walk_leaves,
    within_tolerance,
)
from eng_harness.kinds.calcs import Change, PropertyRow, SectionCounts, WithinRow

FRAMES = "model.frame_placements/1"
LOADS = "model.load_set/1"
GRIDS = "model.grid_system/1"
STORIES = "model.stories/1"
SECTIONS = "model.sections/1"
# Synthetic tolerances per quantity kind (the calc takes them from the basis `compare.*` fields, spec 4.4).
TOL = {"length": Fraction(1, 2), "angle": Fraction(0), "line_load": Fraction(1, 4), "dimensionless": Fraction(0)}


def _point(x: float, y: float, z: float) -> dict[str, Any]:
    return {"x_mm": x, "y_mm": y, "z_mm": z}


def _frame(fid: str, section: str = "S1", x: float = 0.0, rotation: float = 0.0) -> dict[str, Any]:
    return {
        "id": fid,
        "kind": "column",
        "section": section,
        "i": _point(x, 0.0, 0.0),
        "j": _point(x, 0.0, 3000.0),
        "rotation_deg": rotation,
    }


def _row(
    pointer: str, before: Any, after: Any, unit: str | None, kind: str | None, tol: float | None, rule: str
) -> PropertyRow:
    return PropertyRow(
        pointer=pointer, before=before, after=after, unit=unit, quantity_kind=kind, tolerance=tol, rule=rule
    )


# --- D3: exact tolerance comparison ------------------------------------------------------------------------------


def test_tolerance_boundary_exact() -> None:
    # 1000.5 - 1000.0 = 0.5 exactly (both dyadic), equal to the tolerance 1/2: within (AC25, `<=`).
    assert within_tolerance(Fraction(1000.0), Fraction(1000.5), Fraction(1, 2))
    # The next float above 1000.5 differs by 0.5 + 2**-43 > 1/2: changed.
    above = math.nextafter(1000.5, math.inf)
    assert not within_tolerance(Fraction(1000.0), Fraction(above), Fraction(1, 2))
    # Symmetric in its sides: |before - after| is used, not a signed difference.
    assert within_tolerance(Fraction(1000.5), Fraction(1000.0), Fraction(1, 2))
    assert not within_tolerance(Fraction(above), Fraction(1000.0), Fraction(1, 2))
    # A tolerance of zero: only exact equality is equal; the smallest step is a change.
    assert within_tolerance(Fraction(3000.0), Fraction(3000.0), Fraction(0))
    assert not within_tolerance(Fraction(3000.0), Fraction(math.nextafter(3000.0, 0.0)), Fraction(0))
    # Exact, not float: 1.0 - (-1e-20) rounds to 1.0 in floats, but exactly it is 1 + 1e-20 > 1, so changed.
    assert not within_tolerance(Fraction(-1e-20), Fraction(1.0), Fraction(1))
    # The same boundary through a property row (D3): within at the tolerance, changed one float above it.
    near = compare_property("/i/x_mm", 1000.0, 1000.5, TOL)
    assert near == (_row("/i/x_mm", 1000.0, 1000.5, "mm", "length", 0.5, "D3"), True)
    far = compare_property("/i/x_mm", 1000.0, above, TOL)
    assert far == (_row("/i/x_mm", 1000.0, above, "mm", "length", 0.5, "D3"), False)
    # rotation_deg with a zero tolerance and a full turn: changed, no wrapping (D6, AC29).
    turn = compare_property("/rotation_deg", 0.0, 360.0, TOL)
    assert turn == (_row("/rotation_deg", 0.0, 360.0, "deg", "angle", 0.0, "D3"), False)


def test_as_fraction_takes_numbers_only() -> None:
    assert as_fraction(3) == Fraction(3)
    assert as_fraction(0.1) == Fraction(3602879701896397, 36028797018963968)  # the binary value of 0.1
    assert as_fraction(True) is None  # a boolean is not a number (D4)
    assert as_fraction(None) is None
    assert as_fraction("1") is None
    assert as_fraction(math.inf) is None
    assert as_fraction(math.nan) is None


def test_property_rules_outside_d3() -> None:
    # A string compares exactly (D4); no quantity kind, no unit, no tolerance.
    assert compare_property("/section", "S1", "S2", TOL) == (
        _row("/section", "S1", "S2", None, None, None, "D4"),
        False,
    )
    # A number to null is a D4 change of that pointer, keeping the field's kind and unit.
    assert compare_property("/i/x_mm", 1.0, None, TOL) == (
        _row("/i/x_mm", 1.0, None, "mm", "length", None, "D4"),
        False,
    )
    # A known kind without a tolerance in the mapping compares exactly (D4); a stress kind is not in TOL.
    assert compare_property("/fc_MPa", 30.0, 30.25, TOL) == (
        _row("/fc_MPa", 30.0, 30.25, "MPa", "stress", None, "D4"),
        False,
    )
    # A numeric field without a known suffix compares exactly (D4).
    assert compare_property("/count", 1, 2, TOL) == (_row("/count", 1, 2, None, None, None, "D4"), False)
    # An ordered list whose length changed is one property (D5).
    assert compare_property("/joints", ["J1"], ["J1", "J2"], TOL) == (
        _row("/joints", ["J1"], ["J1", "J2"], None, None, None, "D5"),
        False,
    )
    # An escaped pointer segment still names its field for the quantity kind.
    assert compare_property("/a~1b_mm", 1.0, 1.25, TOL)[0].quantity_kind == "length"


# --- D4 and D5: the leaf walker ----------------------------------------------------------------------------------


def test_walk_leaves_member_by_member() -> None:
    before = {"b": 1, "a": {"y": [1, 2], "x": "p"}, "c/d": True}
    after = {"b": 1, "a": {"y": [1, 3], "x": "p"}, "c/d": False}
    # Keys in UTF-16 order, ordered lists index by index, "/" escaped as "~1" (RFC 6901).
    assert list(walk_leaves(before, after)) == [
        ("/a/x", "p", "p"),
        ("/a/y/0", 1, 1),
        ("/a/y/1", 2, 3),
        ("/b", 1, 1),
        ("/c~1d", True, False),
    ]
    # A list length change is one leaf (D5); `~` is escaped as "~0".
    assert list(walk_leaves({"p~": [1]}, {"p~": [1, 2]})) == [("/p~0", [1], [1, 2])]
    # A member missing on one side is null on that side.
    assert list(walk_leaves({"a": 1}, {})) == [("/a", 1, None)]
    # Keys sort as UTF-16 code units: U+FF5E (one unit 0xFF5E) after U+1F600 (surrogates 0xD83D 0xDE00).
    assert [p for p, _, _ in walk_leaves({chr(0xFF5E): 1, chr(0x1F600): 1}, {})] == [
        "/" + chr(0x1F600),
        "/" + chr(0xFF5E),
    ]


def test_walk_leaves_type_change_is_the_enclosing_pointer() -> None:
    rect = {"name": "S1", "shape": {"type": "rectangular", "b_mm": 300.0, "h_mm": 600.0}}
    circ = {"name": "S1", "shape": {"type": "circular", "D_mm": 500.0}}
    leaves = list(walk_leaves(rect, circ))
    assert leaves == [("/name", "S1", "S1"), ("/shape", rect["shape"], circ["shape"])]
    # The same tagged type is walked member by member.
    wider = {"name": "S1", "shape": {"type": "rectangular", "b_mm": 350.0, "h_mm": 600.0}}
    assert ("/shape/b_mm", 300.0, 350.0) in list(walk_leaves(rect, wider))
    # The root object's own `type` (a material, a pattern) is an ordinary member, never the whole object.
    assert list(walk_leaves({"type": "concrete"}, {"type": "steel"})) == [("/type", "concrete", "steel")]
    # An object against a non-object is one leaf.
    assert list(walk_leaves({"a": {"b": 1}}, {"a": 2})) == [("/a", {"b": 1}, 2)]


# --- D2: keys ----------------------------------------------------------------------------------------------------


def test_unnamed_row_keys() -> None:
    keys = {(kind, path): fields for kind, path, fields in ROW_KEYS}
    # D2 unnamed rows and stories; the named lists keep their §4.6 keys.
    assert keys[LOADS, ("frame_loads",)] == ("frame", "pattern", "direction")
    assert keys[LOADS, ("area_loads",)] == ("area", "pattern", "direction")
    assert keys[LOADS, ("combinations", "items")] == ("case.case", "case.case_type", "case.step")
    assert keys[STORIES, ("stories",)] == ("name",)
    assert keys[FRAMES, ("frames",)] == ("id",)
    assert keys[GRIDS, ("systems", "lines")] == ("id",)
    assert keys[LOADS, ("combinations",)] == ("name",)
    assert keys["model.joint_restraints/1", ("joints",)] == ("joint",)
    assert len(ROW_KEYS) == len(keys) == 14
    load = {"frame": "F1", "pattern": "DL", "direction": "gravity", "w_kN_m": 5.0}
    assert row_key(keys[LOADS, ("frame_loads",)], load) == ("F1", "DL", "gravity")
    item = {"case": {"case": "DL", "case_type": "load_pattern", "step": "Max"}, "scale_ratio": 1.2}
    assert row_key(keys[LOADS, ("combinations", "items")], item) == ("DL", "load_pattern", "Max")
    # A null member (a case without a step) is left out of the key, so it never equals any step string.
    item_no_step = {"case": {"case": "DL", "case_type": "load_pattern", "step": None}, "scale_ratio": 1.2}
    assert row_key(keys[LOADS, ("combinations", "items")], item_no_step) == ("DL", "load_pattern")
    # Keys are exact: no case folding or trimming (Q5).
    assert row_key(("id",), {"id": " f1"}) == (" f1",)
    with pytest.raises(TypeError, match="key member 'id' is not a string"):
        row_key(("id",), {"id": 3})


# --- D2 to D5: keyed rows ----------------------------------------------------------------------------------------


def test_keyed_rows_change_kinds() -> None:
    before = [_frame("F1"), _frame("F2"), _frame("F3"), _frame("F4", x=1000.0), _frame("F6"), _frame("F6", "S2")]
    after = [
        _frame("F1"),  # unchanged
        _frame("F2", "S9"),  # changed: one D4 row at /section
        _frame("F4", x=1000.5),  # equal within the 0.5 mm tolerance on /i/x_mm and /j/x_mm
        _frame("F5"),  # added
        _frame("F6"),  # F6 twice before, once after: ambiguous, both lists shown
    ]  # F3 removed
    diff = compare_rows(FRAMES, ("frames",), before, after, TOL)
    assert diff.changes == [
        Change(
            section=FRAMES,
            key=["F2"],
            change="changed",
            before=None,
            after=None,
            properties=[_row("/section", "S1", "S9", None, None, None, "D4")],
        ),
        Change(section=FRAMES, key=["F3"], change="removed", before=_frame("F3"), after=None, properties=[]),
        Change(section=FRAMES, key=["F5"], change="added", before=None, after=_frame("F5"), properties=[]),
        Change(
            section=FRAMES,
            key=["F6"],
            change="ambiguous",
            before=[_frame("F6"), _frame("F6", "S2")],
            after=[_frame("F6")],
            properties=[],
        ),
    ]
    assert diff.within == [
        WithinRow(
            section=FRAMES, key=["F4"], **_row("/i/x_mm", 1000.0, 1000.5, "mm", "length", 0.5, "D3").model_dump()
        ),
        WithinRow(
            section=FRAMES, key=["F4"], **_row("/j/x_mm", 1000.0, 1000.5, "mm", "length", 0.5, "D3").model_dump()
        ),
    ]
    # Counts by hand: added F5, removed F3, changed F2, ambiguous F6, unchanged F1 and F4, two within rows.
    assert section_counts(diff) == SectionCounts(
        added=1, removed=1, changed=1, ambiguous=1, unchanged=2, within_tolerance=2
    )


def test_ambiguous_identical_and_sides_shown() -> None:
    # A duplicated key is ambiguous even with byte-identical rows on both sides: never unchanged (AC28, D7).
    rows: list[Any] = [_frame("F1"), _frame("F1", "S2")]
    same = compare_rows(FRAMES, ("frames",), rows, list(reversed(rows)), TOL)
    assert same == SectionDiff(
        changes=[
            Change(
                section=FRAMES, key=["F1"], change="ambiguous", before=rows, after=list(reversed(rows)), properties=[]
            )
        ],
        within=[],
        outcomes=["ambiguous"],
    )
    # A duplicate on one side and nothing on the other: both lists shown, the empty one as [].
    gone = compare_rows(FRAMES, ("frames",), rows, [], TOL)
    assert gone.changes == [
        Change(section=FRAMES, key=["F1"], change="ambiguous", before=rows, after=[], properties=[])
    ]
    # Identical values written differently (int and float, as RFC 8785 writes them) are not a change.
    assert compare_rows(FRAMES, ("frames",), [_frame("F1", x=0)], [_frame("F1", x=0.0)], TOL).changes == []


def test_nested_keyed_lists_carry_the_parent_key() -> None:
    def system(lines: list[dict[str, Any]], rotation: float = 0.0) -> dict[str, Any]:
        return {"name": "G1", "origin_x_mm": 0.0, "origin_y_mm": 0.0, "rotation_deg": rotation, "lines": lines}

    a = {"id": "A", "axis": "x", "coordinate_mm": 0.0, "visible": True}
    b = {"id": "B", "axis": "x", "coordinate_mm": 6000.0, "visible": True}
    b_moved = {**b, "coordinate_mm": 6001.0}
    diff = compare_rows(GRIDS, ("systems",), [system([b, a])], [system([a, b_moved], 90.0)], TOL)
    # Lines are matched by id under their system (not index by index), and the line list is not a system property.
    assert diff.changes == [
        Change(
            section=GRIDS,
            key=["G1"],
            change="changed",
            before=None,
            after=None,
            properties=[_row("/rotation_deg", 0.0, 90.0, "deg", "angle", 0.0, "D3")],
        ),
        Change(
            section=GRIDS,
            key=["G1", "B"],
            change="changed",
            before=None,
            after=None,
            properties=[_row("/coordinate_mm", 6000.0, 6001.0, "mm", "length", 0.5, "D3")],
        ),
    ]
    # System G1 changed; line A unchanged, line B changed.
    assert diff.outcomes == ["changed", "unchanged", "changed"]
    # An added parent carries its children inside the whole object; they get no rows of their own.
    added = compare_rows(GRIDS, ("systems",), [], [system([a])], TOL)
    assert added.outcomes == ["added"]
    assert [c.key for c in added.changes] == [["G1"]]


def test_compare_section_whole_payload() -> None:
    before = {
        "patterns": [{"name": "DL", "type": "dead", "self_weight_ratio": 1.0}],
        "combinations": [
            {
                "name": "C1",
                "type": "linear_add",
                "items": [{"case": {"case": "DL", "case_type": "load_pattern"}, "scale_ratio": 1.4}],
            }
        ],
        "frame_loads": [{"frame": "F1", "pattern": "DL", "direction": "gravity", "w_kN_m": 5.0}],
        "area_loads": [],
    }
    after = {
        "patterns": [{"name": "DL", "type": "dead", "self_weight_ratio": 1.0}],
        "combinations": [
            {
                "name": "C1",
                "type": "linear_add",
                "items": [{"case": {"case": "DL", "case_type": "load_pattern"}, "scale_ratio": 1.2}],
            }
        ],
        "frame_loads": [{"frame": "F1", "pattern": "DL", "direction": "gravity", "w_kN_m": 5.25}],
        "area_loads": [],
    }
    diff = compare_section(LOADS, before, after, TOL)
    item_change = Change(
        section=LOADS,
        key=["C1", "DL", "load_pattern"],
        change="changed",
        before=None,
        after=None,
        properties=[_row("/scale_ratio", 1.4, 1.2, "1", "dimensionless", 0.0, "D3")],
    )
    assert diff.changes == [item_change]
    # 5.25 - 5.0 = 0.25 = the line-load tolerance: within.
    assert diff.within == [
        WithinRow(
            section=LOADS,
            key=["F1", "DL", "gravity"],
            **_row("/w_kN_m", 5.0, 5.25, "kN/m", "line_load", 0.25, "D3").model_dump(),
        )
    ]
    # patterns DL, combinations C1, items (C1, DL), frame loads F1: one changed, three unchanged.
    assert section_counts(diff) == SectionCounts(
        added=0, removed=0, changed=1, ambiguous=0, unchanged=3, within_tolerance=1
    )


def test_compare_section_own_members() -> None:
    story = {"name": "L1", "elevation_mm": 3000.0, "height_mm": 3000.0, "master_story": True, "similar_to": None}
    before = {"base_elevation_mm": 0.0, "stories": [story]}
    after = {"base_elevation_mm": 2.0, "stories": [story]}
    diff = compare_section(STORIES, before, after, TOL)
    # A member of the section itself (not in a keyed list) is a property of the section, key [].
    assert diff.changes == [
        Change(
            section=STORIES,
            key=[],
            change="changed",
            before=None,
            after=None,
            properties=[_row("/base_elevation_mm", 0.0, 2.0, "mm", "length", 0.5, "D3")],
        )
    ]
    assert diff.outcomes == ["changed", "unchanged"]
    # Unchanged section members add no outcome; the stories list is compared by name.
    assert compare_section(STORIES, before, before, TOL) == SectionDiff(changes=[], within=[], outcomes=["unchanged"])
    # Within-tolerance section members are listed with key [].
    near = compare_section(STORIES, before, {**before, "base_elevation_mm": 0.5}, TOL)
    assert (near.changes, [w.key for w in near.within], near.outcomes) == ([], [[]], ["unchanged"])


def test_compare_section_sorts_changes_by_key() -> None:
    before = {
        "frame_sections": [],
        "area_sections": [{"name": "W1", "material": "C30", "kind": "wall", "thickness_mm": 200.0}],
    }
    after = {
        "frame_sections": [{"name": "A1", "material": "C30", "shape": {"type": "circular", "D_mm": 500.0}}],
        "area_sections": [],
    }
    diff = compare_section(SECTIONS, before, after, TOL)
    # Sorted by key across the section's lists: ["A1"] before ["W1"].
    assert [(c.key, c.change) for c in diff.changes] == [(["A1"], "added"), (["W1"], "removed")]
