"""Unit tests of the change-set model (plan 0007 T1b; spec 0007 section 4.3, AC3).

The values are synthetic; they exercise shape, units and literal types only (the model checks no engineering bound).
"""

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from eng_harness.workflows.model_edit_cycle._change_set import (
    REFUSED_KIND_GAPS,
    ChangeSetDraft,
    ChangeSetSettings,
    LengthInput,
    WallSection,
    refused_gap,
)

BASIS = {"source": "basis", "path": "loads.floor_dead_kpa"}
KINDS = {
    "frame_section",
    "area_section",
    "wall_section",
    "frame_uniform_load",
    "area_uniform_load",
    "load_pattern_add",
    "load_combination_set",
    "load_combination_delete",
    "joint_restraints",
}


def _items() -> list[dict[str, Any]]:
    thickness = {"source": "input", "value": 250, "unit": "mm"}
    return [
        {"id": "a1", "kind": "frame_section", "frames": ["B1", "B2"], "section": "R300x600"},
        {"id": "a2", "kind": "frame_section", "select": {"story": "L1", "section": None}, "section": "R300x600"},
        {"id": "a3", "kind": "area_section", "areas": ["F1"], "section": "S200"},
        {
            "id": "a4",
            "kind": "area_section",
            "select": {"story": None, "section": "S150", "area_kind": "slab"},
            "section": "S200",
        },
        {
            "id": "a5",
            "kind": "wall_section",
            "name": "W250",
            "material": "C30",
            "thickness": thickness,
            "shell_type": "ShellThick",
        },
        {
            "id": "a6",
            "kind": "frame_uniform_load",
            "frames": ["B1"],
            "pattern": "SDL",
            "direction": "gravity",
            "w": {"source": "input", "value": 12.5, "unit": "kN/m"},
        },
        {"id": "a7", "kind": "area_uniform_load", "areas": ["F1"], "pattern": "LL", "direction": "gravity", "q": BASIS},
        {
            "id": "a8",
            "kind": "load_pattern_add",
            "name": "SDL2",
            "type": "dead",
            "self_weight": {"source": "input", "value": 0, "unit": "1"},
        },
        {
            "id": "a9",
            "kind": "load_combination_set",
            "name": "C1",
            "type": "linear_add",
            "items": [
                {
                    "case": {"case": "DL", "case_type": "load_pattern"},
                    "scale": {"source": "input", "value": 1.2, "unit": "1"},
                }
            ],
        },
        {"id": "a10", "kind": "load_combination_delete", "name": "C0"},
        {
            "id": "a11",
            "kind": "joint_restraints",
            "joints": ["J1"],
            "ux": True,
            "uy": True,
            "uz": True,
            "rx": False,
            "ry": False,
            "rz": False,
        },
    ]


def _draft(items: list[dict[str, Any]] | None = None, **extra: Any) -> dict[str, Any]:
    return {"items": _items() if items is None else items, **extra}


def _with(index: int, **change: Any) -> dict[str, Any]:
    items = copy.deepcopy(_items())
    items[index].update(change)
    return _draft(items)


def test_model_parses_and_refuses() -> None:
    parsed = ChangeSetDraft.model_validate(_draft(note="n", benchmark_request="B1-001"))
    assert [i.kind for i in parsed.items][:3] == ["frame_section", "frame_section", "area_section"]
    assert {i.kind for i in parsed.items} == KINDS
    cases: list[tuple[dict[str, Any], str]] = [
        ({**_draft(), "bogus": 1}, "bogus"),
        (_with(0, bogus=1), "bogus"),
        (_with(4, thickness={"source": "input", "value": 250}), "unit"),
        (_with(4, thickness={"source": "input", "value": 250, "unit": "kN"}), "thickness"),
        (_with(5, w={"source": "input", "value": 12.5, "unit": "kPa"}), "w"),
        (_with(7, self_weight={"source": "input", "value": 1, "unit": "mm"}), "self_weight"),
        (_with(4, thickness={"source": "input", "value": float("inf"), "unit": "mm"}), "thickness"),
        (_with(4, thickness={"source": "input", "value": True, "unit": "mm"}), "thickness"),
        (_with(4, thickness={"source": "basis", "path": "NotAPath"}), "path"),
        (_with(4, thickness={"source": "other", "value": 1}), "thickness"),
        (_with(4, shell_type="Plate"), "shell_type"),
        (_with(0, frames=["B1"], select={"story": "L1"}), "frames"),
        (_with(1, select={"story": None, "section": None}), "select"),
        (_with(0, frames=[]), "frames"),
        (_with(5, direction=""), "direction"),
        (_draft([]), "items"),
        (_draft([_items()[0], _items()[0]]), "id"),
    ]
    for payload, field in cases:
        with pytest.raises(ValidationError, match=field):
            ChangeSetDraft.model_validate(payload)


def test_any_unit_of_the_dimension_parses() -> None:
    parsed = ChangeSetDraft.model_validate(_with(4, thickness={"source": "input", "value": 0.25, "unit": "m"}))
    item = parsed.items[4]
    assert isinstance(item, WallSection)
    assert isinstance(item.thickness, LengthInput)
    assert (item.thickness.value, item.thickness.unit) == (0.25, "m")


def test_size_limit_is_a_setting() -> None:
    settings = ChangeSetSettings(max_items=2)
    ChangeSetDraft.model_validate(_draft(_items()[:2]), context={"change_set_settings": settings})
    with pytest.raises(ValidationError, match="items"):
        ChangeSetDraft.model_validate(_draft(_items()[:3]), context={"change_set_settings": settings})
    with pytest.raises(ValidationError):
        ChangeSetSettings.model_validate({})  # no default: a limit is never invented


REFUSED = {
    "slab_section": "H-G1",
    "frame_section_define": "H-G1",
    "area_section_define": "H-G1",
    "material_define": "H-G1",
    "load_pattern_change": "OQ-G8",
    "load_pattern_delete": "OQ-G8",
    "seismic_parameters": "CG-1",
}


@pytest.mark.parametrize(("kind", "gap"), sorted(REFUSED.items()))
def test_refused_kinds_parse_with_their_gap(kind: str, gap: str) -> None:
    parsed = ChangeSetDraft.model_validate(_draft([{"id": "r1", "kind": kind, "anything": {"x": 1}}]))
    assert REFUSED_KIND_GAPS[kind] == gap
    assert refused_gap(parsed.items[0]) == gap


def test_refused_variants_parse_with_their_gap() -> None:
    cases = [
        (_with(5, direction="x"), 5, "H-G2"),
        (_with(6, direction="x"), 6, "H-G2"),
        (_with(7, type="superimposed_dead"), 7, "H-G3"),
        (_with(7, type="roof_live"), 7, "H-G3"),
        (_with(8, type="range"), 8, "H-G3"),
        (_draft([{"id": "p", "kind": "frame_point_load", "frames": ["B1"]}]), 0, "H-G2"),
    ]
    for payload, index, gap in cases:
        assert refused_gap(ChangeSetDraft.model_validate(payload).items[index]) == gap


def test_accepted_items_have_no_gap() -> None:
    assert [refused_gap(i) for i in ChangeSetDraft.model_validate(_draft()).items] == [None] * len(_items())


def test_unknown_kind_is_a_schema_error() -> None:
    with pytest.raises(ValidationError, match="kind"):
        ChangeSetDraft.model_validate(_draft([{"id": "x", "kind": "delete_everything"}]))
