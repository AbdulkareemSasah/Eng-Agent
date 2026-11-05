"""Change-set model (plan 0007 T1; spec 0007 section 4.3, AC3)."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from eng_harness.workflows.model_edit_cycle import ChangeSetDraft, ChangeSetRequest

DATA = Path(__file__).resolve().parents[2] / "data" / "kinds" / "edit_cycle"
V1_KINDS = {
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


def _load(stem: str) -> dict[str, Any]:
    data = json.loads((DATA / f"{stem}.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _item(payload: dict[str, Any], kind: str) -> dict[str, Any]:
    return next(i for i in payload["items"] if i["kind"] == kind)


def _no_unit(p: dict[str, Any]) -> None:
    del _item(p, "wall_section")["thickness"]["unit"]


def _wrong_dimension(p: dict[str, Any]) -> None:
    _item(p, "wall_section")["thickness"]["unit"] = "kPa"


def _wrong_dimension_load(p: dict[str, Any]) -> None:
    _item(p, "frame_uniform_load")["w"]["unit"] = "mm"


def _unknown_unit(p: dict[str, Any]) -> None:
    _item(p, "area_uniform_load")["q"] = {"source": "input", "value": 1, "unit": "furlong"}


def _unknown_field(p: dict[str, Any]) -> None:
    _item(p, "frame_section")["colour"] = "red"


def _unknown_top_field(p: dict[str, Any]) -> None:
    p["extra"] = 1


def _duplicate_id(p: dict[str, Any]) -> None:
    p["items"][1]["id"] = p["items"][0]["id"]


def _empty(p: dict[str, Any]) -> None:
    p["items"] = []


def _both_targets(p: dict[str, Any]) -> None:
    _item(p, "frame_uniform_load")["frames"] = ["F1"]


def _no_target(p: dict[str, Any]) -> None:
    del _item(p, "frame_section")["frames"]


def _empty_select(p: dict[str, Any]) -> None:
    _item(p, "frame_uniform_load")["select"] = {"story": None, "section": None}


def _unknown_kind(p: dict[str, Any]) -> None:
    _item(p, "frame_section")["kind"] = "beam_magic"


def _bool_value(p: dict[str, Any]) -> None:
    _item(p, "wall_section")["thickness"]["value"] = True


def _nan_value(p: dict[str, Any]) -> None:
    _item(p, "wall_section")["thickness"]["value"] = float("nan")


def _bad_shell(p: dict[str, Any]) -> None:
    _item(p, "wall_section")["shell_type"] = "ShellMagic"


def _bad_path(p: dict[str, Any]) -> None:
    _item(p, "area_uniform_load")["q"]["path"] = "not a path"


def _number_as_restraint(p: dict[str, Any]) -> None:
    _item(p, "joint_restraints")["ux"] = 1


INVALID: list[tuple[Callable[[dict[str, Any]], None], str]] = [
    (_no_unit, "thickness"),
    (_wrong_dimension, "thickness"),
    (_wrong_dimension_load, "w"),
    (_unknown_unit, "q"),
    (_unknown_field, "colour"),
    (_unknown_top_field, "extra"),
    (_duplicate_id, "id"),
    (_empty, "items"),
    (_both_targets, "frames"),
    (_no_target, "frames"),
    (_empty_select, "select"),
    (_unknown_kind, "kind"),
    (_bool_value, "thickness"),
    (_nan_value, "thickness"),
    (_bad_shell, "shell_type"),
    (_bad_path, "path"),
    (_number_as_restraint, "ux"),
]


def test_model_parses_and_refuses() -> None:
    """AC3: one item of each v1 kind parses; each invalid answer is refused naming its field."""
    payload = _load("change_set_all_kinds")
    draft = ChangeSetDraft.model_validate(payload)
    assert {i.kind for i in draft.items} == V1_KINDS
    assert draft.benchmark_request == "B1-r1"
    assert ChangeSetDraft.model_validate(draft.model_dump(mode="json")) == draft
    request = ChangeSetRequest.model_validate({"change_set": payload})
    assert request.change_set == draft
    for mutate, field in INVALID:
        bad = copy.deepcopy(payload)
        mutate(bad)
        with pytest.raises(ValidationError) as caught:
            ChangeSetDraft.model_validate(bad)
        named = {str(part) for err in caught.value.errors() for part in err["loc"]}
        named |= {word.strip(".,:'[]") for err in caught.value.errors() for word in err["msg"].split()}
        assert field in named, (mutate.__name__, caught.value.errors())


def test_any_unit_of_the_fields_dimension_is_accepted() -> None:
    """AC3: the dimension is checked, not the symbol (conversion is by `eng_contract.units` in the check)."""
    payload = _load("change_set_all_kinds")
    _item(payload, "wall_section")["thickness"]["unit"] = "m"
    assert ChangeSetDraft.model_validate(payload).items[2].kind == "wall_section"


def test_refused_kinds_and_variants_parse() -> None:
    """Spec 4.3.2: refused kinds and variants parse so the check can refuse them with their gap id."""
    draft = ChangeSetDraft.model_validate(_load("change_set_refused"))
    assert [i.id for i in draft.items] == [f"r{n}" for n in range(1, 13)]


def test_frozen() -> None:
    """The model is frozen."""
    draft = ChangeSetDraft.model_validate(_load("change_set_all_kinds"))
    with pytest.raises(ValidationError):
        draft.note = "other"
