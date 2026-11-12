"""Section keys and canonical order of a model state (spec 0003 4.6 rule F2 and its table).

Purpose: put the lists of a neutral model payload in one order, so the same state read in any list order gives the
same bytes. Named lists are sorted by their key as UTF-16 code-unit sequences (as RFC 8785 sorts keys); lists of
unnamed rows by each row's canonical JSON bytes, so duplicates are kept. Stories, area `points` and `joints` keep
their order. Units: none; values are not changed. Errors: none of its own; `canonical_json` raises
`CanonicalJsonError` for a value outside the JSON data model. `ROW_KEYS` and `row_key` add the object keys of the
difference report (spec 4.7 rule D2); `row_key` raises `TypeError` for a key member that is not a string.
"""

from typing import Any

from eng_contract.canonical import canonical_json

__all__ = ["ORDER", "ROW_KEYS", "SECTIONS", "canonical_state", "item_count", "row_key"]

SECTIONS: tuple[tuple[str, str], ...] = (
    ("stories", "model.stories/1"),
    ("grids", "model.grid_system/1"),
    ("frames", "model.frame_placements/1"),
    ("areas", "model.area_placements/1"),
    ("sections", "model.sections/1"),
    ("materials", "model.materials/1"),
    ("loads", "model.load_set/1"),
    ("restraints", "model.joint_restraints/1"),
)
"""Input field name and neutral kind of each section (spec 4.6 input)."""

ORDER: tuple[tuple[str, tuple[str, ...], str | None], ...] = (
    ("model.grid_system/1", ("systems",), "name"),
    ("model.grid_system/1", ("systems", "lines"), "id"),
    ("model.frame_placements/1", ("frames",), "id"),
    ("model.area_placements/1", ("areas",), "id"),
    ("model.sections/1", ("frame_sections",), "name"),
    ("model.sections/1", ("area_sections",), "name"),
    ("model.materials/1", ("materials",), "name"),
    ("model.load_set/1", ("patterns",), "name"),
    ("model.load_set/1", ("combinations",), "name"),
    ("model.load_set/1", ("combinations", "items"), None),
    ("model.load_set/1", ("frame_loads",), None),
    ("model.load_set/1", ("area_loads",), None),
    ("model.joint_restraints/1", ("joints",), "joint"),
)
"""The F2 table: kind, path of the list (a nested list under each row of the one before), key (None: row bytes)."""

ROW_KEYS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("model.stories/1", ("stories",), ("name",)),
    *((kind, path, (key,)) for kind, path, key in ORDER if key is not None),
    ("model.load_set/1", ("combinations", "items"), ("case.case", "case.case_type", "case.step")),
    ("model.load_set/1", ("frame_loads",), ("frame", "pattern", "direction")),
    ("model.load_set/1", ("area_loads",), ("area", "pattern", "direction")),
)
"""The D2 table: kind, path of the list (as in ORDER), key members (a dotted member is nested in the row)."""


def _sorted(rows: list[Any], key: str | None) -> list[Any]:
    if key is None:
        return sorted(rows, key=canonical_json)
    return sorted(rows, key=lambda row: row[key].encode("utf-16-be", "surrogatepass"))


def _apply(node: dict[str, Any], path: tuple[str, ...], key: str | None) -> dict[str, Any]:
    head, rest = path[0], path[1:]
    rows = node[head]
    return {**node, head: [_apply(row, rest, key) for row in rows] if rest else _sorted(rows, key)}


def canonical_state(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a normalized `kind` payload with its lists in the F2 order; the input is not changed."""
    state = payload
    for name, path, key in ORDER:
        if name == kind:
            state = _apply(state, path, key)
    return state


def item_count(payload: dict[str, Any]) -> int:
    """The number of members of the payload's top-level lists (the `items` of a fingerprint section)."""
    return sum(len(value) for value in payload.values() if isinstance(value, list))


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
