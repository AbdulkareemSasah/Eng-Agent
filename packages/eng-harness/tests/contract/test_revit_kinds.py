"""Contract tests of the Revit harness kinds (plan 0011 T6; spec 0011 AC33, §4.5)."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.kinds.revit import FRAME_ELEMENT_MAP_KIND_NAME, REVIT_KINDS

DATA = Path(__file__).resolve().parents[1] / "data" / "kinds" / "revit"
KINDS = {
    "status": "harness.revit_status/1",
    "levels": "harness.revit_levels/1",
    "grids": "harness.revit_grids/1",
    "structure": "harness.revit_structure/1",
    "write_result": "harness.revit_write_result/1",
}
Mutation = Callable[[dict[str, Any]], None]


def _load(stem: str) -> dict[str, Any]:
    data = json.loads((DATA / f"{stem}.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _set(path: list[str | int], value: Any) -> Mutation:
    def mutate(p: dict[str, Any]) -> None:
        node: Any = p
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return mutate


def _drop(path: list[str | int]) -> Mutation:
    def mutate(p: dict[str, Any]) -> None:
        node: Any = p
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]

    return mutate


def _rename(path: list[str | int], new_name: str) -> Mutation:
    def mutate(p: dict[str, Any]) -> None:
        node: Any = p
        for key in path[:-1]:
            node = node[key]
        old = path[-1]
        assert isinstance(old, str)
        node[new_name] = node.pop(old)

    return mutate


def _levels_unsorted(p: dict[str, Any]) -> None:
    p["levels"].reverse()


def _grids_unsorted(p: dict[str, Any]) -> None:
    p["grids"].reverse()


def _elements_unsorted(p: dict[str, Any]) -> None:
    p["elements"].reverse()


def _types_unsorted(p: dict[str, Any]) -> None:
    p["types"].reverse()


INVALID: list[tuple[str, Mutation, str]] = [
    # unit-bearing field without its suffix (spec 0011 AC33)
    ("levels", _rename(["levels", 0, "elevation_mm"], "elevation"), "elevation_mm"),
    ("grids", _rename(["grids", 0, "length_mm"], "length"), "length_mm"),
    ("structure", _rename(["elements", 0, "rotation_deg"], "rotation"), "rotation_deg"),
    # unsorted lists (spec 0011 AC33 / §4.5)
    ("levels", _levels_unsorted, "sorted"),
    ("grids", _grids_unsorted, "sorted"),
    ("structure", _elements_unsorted, "sorted"),
    ("structure", _types_unsorted, "sorted"),
    # counts that do not match rows (instance_ids length vs declared count is not used;
    # structure types.instance_ids uniqueness / element category)
    ("structure", _set(["elements", 0, "category"], "wall"), "category"),
    ("write_result", _set(["targets", 0, "element_id"], ""), "element_id"),
    ("status", _set(["ping_status"], ""), "ping_status"),
    ("status", _drop(["title"]), "title"),
]


def test_fixtures() -> None:
    """AC33: each Revit kind accepts a valid fixture and refuses unknown fields and the listed invalids."""
    assert set(REVIT_KINDS) == set(KINDS.values())
    assert FRAME_ELEMENT_MAP_KIND_NAME == "harness.frame_element_map/1"
    for stem, kind in KINDS.items():
        model = HARNESS_KINDS[kind]
        assert HARNESS_KINDS[kind] is REVIT_KINDS[kind]
        payload = _load(stem)
        parsed = model.model_validate(payload)
        assert model.model_validate(parsed.model_dump(mode="json", exclude_none=False)) == parsed
        with pytest.raises(ValidationError, match="Extra inputs"):
            model.model_validate({**payload, "unknown_field": 1})
    for stem, mutate, fragment in INVALID:
        payload = copy.deepcopy(_load(stem))
        mutate(payload)
        with pytest.raises(ValidationError, match=fragment):
            HARNESS_KINDS[KINDS[stem]].model_validate(payload)
