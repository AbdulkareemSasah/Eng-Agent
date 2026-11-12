"""Section keys and canonical order of a model state (spec 0003 4.6 rule F2 and its table).

Purpose: put the lists of a neutral model payload in one order, so the same state read in any list order gives the
same bytes. Named lists are sorted by their key as UTF-16 code-unit sequences (as RFC 8785 sorts keys); lists of
unnamed rows by each row's canonical JSON bytes, so duplicates are kept. Stories, area `points` and `joints` keep
their order. Units: none; values are not changed. Errors: none of its own; `canonical_json` raises
`CanonicalJsonError` for a value outside the JSON data model.
"""

from typing import Any

from eng_contract.canonical import canonical_json

__all__ = ["ORDER", "SECTIONS", "canonical_state", "item_count", "list_at", "row_key"]

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


def list_at(payload: dict[str, Any], path: tuple[str, ...]) -> list[Any]:
    """The list at `path` under `payload` (F2 paths); raises `KeyError` when a segment is missing."""
    if not path:
        raise KeyError("empty path")
    head, *rest = path
    node = payload[head]
    if not rest:
        if not isinstance(node, list):
            raise TypeError(f"path {path!r} is not a list")
        return node
    if isinstance(node, list):
        rows: list[Any] = []
        for row in node:
            if isinstance(row, dict):
                rows.extend(list_at(row, tuple(rest)))
        return rows
    if isinstance(node, dict):
        return list_at(node, tuple(rest))
    raise TypeError(f"path {path!r} cannot be followed")


def row_key(list_name: str, key: str | None, row: dict[str, Any]) -> tuple[str, ...]:
    """D2 object key within a named list (`key`) or an unnamed list (`list_name`)."""
    if key is not None:
        return (row[key],)
    if list_name == "items":
        case = row["case"]
        step = case["step"] if case.get("step") is not None else ""
        return (case["case"], case["case_type"], step)
    if list_name == "frame_loads":
        return (row["frame"], row["pattern"], row["direction"])
    if list_name == "area_loads":
        return (row["area"], row["pattern"], row["direction"])
    raise ValueError(f"unnamed list {list_name!r} has no row key rule")
