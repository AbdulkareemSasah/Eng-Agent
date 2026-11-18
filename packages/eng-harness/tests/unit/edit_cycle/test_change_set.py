"""Unit tests of the change-set model (plan 0007 T1b; spec 0007 section 4.3, AC3).

The values are synthetic; they exercise shape, units and literal types only (the model checks no engineering bound).
"""

import copy
from typing import Any

import pytest
from eng_contract.envelope import Provenance
from eng_contract.params import InputPolicy, validate_input
from eng_contract.store import ResultStore
from golden.edit_cycle import input_meta, load_cases, run_check
from pydantic import JsonValue, ValidationError

from eng_harness.adapters.csi._edits import AddLoadPatternArgs, DefineWallSectionArgs, SetFrameLoadDistributedArgs
from eng_harness.workflows.model_edit_cycle._change_set import (
    REFUSED_KIND_GAPS,
    AreaLoadInput,
    ChangeSetDraft,
    ChangeSetSettings,
    LengthInput,
    LineLoadInput,
    RatioInput,
    WallSection,
    refused_gap,
)

BASIS = {"source": "basis", "path": "loads.floor_dead_kPa"}
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


REFUSED_ITEMS = [
    *({"id": "r1", "kind": kind, "anything": {"x": 1}} for kind in sorted(REFUSED)),
    {"id": "r1", "kind": "frame_point_load", "frames": ["B1"]},
    {**_items()[5], "id": "r1", "direction": "global_x"},
    {**_items()[6], "id": "r1", "direction": "local_3"},
    {**_items()[7], "id": "r1", "type": "superimposed_dead"},
    {**_items()[7], "id": "r1", "type": "roof_live"},
    {**_items()[8], "id": "r1", "type": "range"},
]
REFUSED_GAPS = [*(REFUSED[kind] for kind in sorted(REFUSED)), "H-G2", "H-G2", "H-G2", "H-G3", "H-G3", "H-G3"]


@pytest.mark.parametrize(("item", "gap"), list(zip(REFUSED_ITEMS, REFUSED_GAPS, strict=True)))
def test_refused_kinds_name_their_gap(item: dict[str, Any], gap: str) -> None:
    """AC6: a refused kind or variant is the error issue NOT_IMPLEMENTED with its gap id; the check fails."""
    case = load_cases("check")["check-resolve-select"]
    accepted = {"id": "ok", "kind": "frame_section", "frames": ["B1"], "section": "C400"}
    body = run_check(case, items=[item, accepted])
    assert body["status"] == "FAIL"
    assert body["issues"] == [
        {
            "item_id": "r1",
            "severity": "error",
            "code": "NOT_IMPLEMENTED",
            "detail": f"{item['kind']} is refused in v1 (spec 0007 4.3.2)",
            "gap": gap,
        }
    ]
    assert [resolved["item_id"] for resolved in body["resolved"]] == ["ok"]


def test_value_refs_are_write_arguments(store: ResultStore) -> None:
    """AC40: each resolved ref of the check is a valid engineering argument of the CSI tool port (`require_refs`).

    By hand from the contract's unit table: 1 m = 1000 mm, so 0.2 m is 200 mm; a basis value and a ratio are stored
    as they are (12 kN/m, 0.5). The answer is stored as the engine stores it (`basis.engineer_input/1`, `fields`).
    """
    case = load_cases("check")["check-resolve-added-earlier"]
    basis = copy.deepcopy(case.input["basis"])
    basis["fields"]["loads.line_kN_m"] = {**basis["fields"]["loads.sdl_kPa"], "value": 12.0, "unit": "kN/m"}
    items = [
        {
            "id": "w1",
            "kind": "wall_section",
            "name": "W200",
            "material": "C30",
            "thickness": {"source": "input", "value": 0.2, "unit": "m"},
            "shell_type": "ShellThick",
        },
        {
            "id": "l1",
            "kind": "frame_uniform_load",
            "frames": ["B1"],
            "pattern": "DEAD",
            "direction": "gravity",
            "w": {"source": "basis", "path": "loads.line_kN_m"},
        },
        {
            "id": "p1",
            "kind": "load_pattern_add",
            "name": "SDL",
            "type": "dead",
            "self_weight": {"source": "input", "value": 0.5, "unit": "1"},
        },
    ]
    stored = ChangeSetDraft.model_validate({"items": items}).model_dump(mode="json")
    provenance = Provenance(
        tool="harness", tool_version="1", host=None, inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
    )
    entered = {"unit": None, "entered_by": "test", "entered_at": provenance.started_at}
    held: dict[str, JsonValue] = {"change_set": {"value": stored, **entered}}
    answer = store.put("basis.engineer_input/1", {"step": "s", "fields": held}, provenance).result_id
    basis_id = store.put("basis.design_basis/1", basis, provenance).result_id
    meta = input_meta({**case.refs, "change_set": answer, "basis": basis_id})
    body = run_check(case, items=stored["items"], meta=meta, basis=basis)
    assert body["status"] == "PASS"
    refs = [value["ref"] for item in body["resolved"] for value in item["values"]]

    def argument(model: Any, **fields: Any) -> Any:
        raw = {"model": "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", **fields}
        policy = InputPolicy(require_refs=True)
        return validate_input(model, raw, source=store, current_revision=lambda _: None, policy=policy).model

    wall = argument(DefineWallSectionArgs, name="W200", material="C30", thickness_mm={"$ref": refs[0]})
    load = argument(SetFrameLoadDistributedArgs, frame="B1", pattern="DEAD", w_kN_m={"$ref": refs[1]})
    pattern = argument(AddLoadPatternArgs, name="SDL", type="dead", self_weight_ratio={"$ref": refs[2]})
    assert (wall.thickness_mm, load.w_kN_m, pattern.self_weight_ratio) == (200.0, 12.0, 0.5)
    assert refs == [
        f"{answer}#/fields/change_set/value/items/0/thickness/value_mm",
        f"{basis_id}#/fields/loads.line_kN_m/value",
        f"{answer}#/fields/change_set/value/items/2/self_weight/value_ratio",
    ]


CANONICAL: list[tuple[type[Any], dict[str, Any], str, float]] = [
    (LengthInput, {"value": 0.2, "unit": "m"}, "value_mm", 200.0),  # 1 m = 1000 mm
    (LengthInput, {"value": 250.0, "unit": "mm"}, "value_mm", 250.0),
    (LineLoadInput, {"value": 12000.0, "unit": "N/m"}, "value_kN_m", 12.0),  # 1 N/m = 0.001 kN/m
    (AreaLoadInput, {"value": 1500.0, "unit": "Pa"}, "value_kPa", 1.5),  # 1 Pa = 0.001 kPa
    (RatioInput, {"value": 0.5, "unit": "1"}, "value_ratio", 0.5),
]


@pytest.mark.parametrize(("model", "literal", "name", "canonical"), CANONICAL)
def test_input_value_holds_its_canonical_number(
    model: type[Any], literal: dict[str, Any], name: str, canonical: float
) -> None:
    """AC40: `value_<suffix>` is filled from `value` and `unit`, kept when given right, and refused when it differs."""
    raw = {"source": "input", **literal}
    filled = model.model_validate(raw)
    assert getattr(filled, name) == canonical
    assert model.model_validate(filled.model_dump(mode="json")) == filled  # the stored answer validates on replay
    assert model.model_validate({**raw, name: None}) == filled  # an absent number and a null are the same
    for wrong in (canonical + 1.0, canonical * 1.0000001):
        with pytest.raises(ValidationError, match=f"{name} {wrong!r} is not"):
            model.model_validate({**raw, name: wrong})


def test_canonical_field_is_declared_on_the_four_models_only() -> None:
    declared = {
        m: sorted(name for name in m.model_fields if name.startswith("value_"))
        for m in (LengthInput, LineLoadInput, AreaLoadInput, RatioInput)
    }
    assert list(declared.values()) == [["value_mm"], ["value_kN_m"], ["value_kPa"], ["value_ratio"]]
    from eng_harness.workflows.column_design._requests import _Area  # the frozen column model is unchanged

    assert not [name for name in _Area.model_fields if name.startswith("value_")]


def test_canonical_number_of_a_bad_literal_is_not_invented() -> None:
    """A bad unit, a non-finite or boolean value fail on their own field; no number is filled for them."""
    for bad in ({"value": 1.0, "unit": "kN"}, {"value": float("inf"), "unit": "mm"}, {"value": True, "unit": "mm"}):
        with pytest.raises(ValidationError) as caught:
            LengthInput.model_validate({"source": "input", **bad})
        assert "value_mm" not in str(caught.value)
