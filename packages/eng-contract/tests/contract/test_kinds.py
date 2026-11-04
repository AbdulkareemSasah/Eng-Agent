"""Kind names, the registry and the model.* kinds (plan T11; spec 4.10, AC46, AC47)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds import NEUTRAL_KINDS, KindName, KindNotRegistered, KindRegistry
from eng_contract.kinds import model as model_kinds
from eng_contract.params import ContractDefinitionError

_DATA = Path(__file__).resolve().parent.parent / "data" / "kinds"
_MODEL_KINDS = (
    "model.stories/1",
    "model.grid_system/1",
    "model.frame_placements/1",
    "model.area_placements/1",
    "model.sections/1",
    "model.materials/1",
    "model.load_set/1",
    "model.joint_restraints/1",
)
_KIND = TypeAdapter(KindName)


class _Other(BaseModel):
    pass


def _folder(kind: str) -> Path:
    return _DATA / kind.replace("/", "-")


@pytest.mark.parametrize("name", ["model.stories/1", "harness.model_diff/1", "a.b_c.d/9999"])
def test_kind_name_accepted(name: str) -> None:
    assert _KIND.validate_python(name) == name


@pytest.mark.parametrize("name", ["model.stories", "model.stories/0", "model.stories/10000", "model/1", "Model.a/1"])
def test_kind_name_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        _KIND.validate_python(name)


def test_kind_names_and_registry() -> None:
    assert set(_MODEL_KINDS) <= set(NEUTRAL_KINDS)
    assert NEUTRAL_KINDS["model.stories/1"] is model_kinds.Stories
    with pytest.raises(KindNotRegistered) as caught:
        NEUTRAL_KINDS["model.nothing/1"]  # noqa: B018  # B-020: the lookup itself is the behavior under test
    assert isinstance(caught.value, ContractError)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert "model.nothing/1" not in NEUTRAL_KINDS
    assert NEUTRAL_KINDS.get("model.nothing/1") is None
    with pytest.raises(KindNotRegistered):
        NEUTRAL_KINDS["model.stories"]  # no version: not a name, so not registered


def test_registry_extend() -> None:
    extended = NEUTRAL_KINDS.extend({"harness.model_diff/1": _Other})
    assert extended["harness.model_diff/1"] is _Other
    assert "harness.model_diff/1" not in NEUTRAL_KINDS  # immutable: extend returns a new registry
    assert set(NEUTRAL_KINDS) <= set(extended)
    assert isinstance(extended, KindRegistry)


@pytest.mark.parametrize(
    "mapping",
    [
        {"model.extra/1": _Other},  # neutral family
        {"geom.polylines/1": _Other},
        {"model.stories/1": _Other},  # duplicate
        {"harness.model_diff": _Other},  # not a kind name
        {"harness.model_diff/0": _Other},
    ],
)
def test_registry_extend_rejects(mapping: dict[str, type[BaseModel]]) -> None:
    with pytest.raises(ContractDefinitionError):
        NEUTRAL_KINDS.extend(mapping)


def test_registry_extend_rejects_duplicate_of_extension() -> None:
    extended = NEUTRAL_KINDS.extend({"harness.model_diff/1": _Other})
    with pytest.raises(ContractDefinitionError):
        extended.extend({"harness.model_diff/1": _Other})


def _fixtures() -> list[tuple[str, Path]]:
    return [(kind, path) for kind in _MODEL_KINDS for path in sorted(_folder(kind).glob("*.json"))]


def test_every_model_kind_has_valid_and_invalid_fixtures() -> None:
    for kind in _MODEL_KINDS:
        names = {p.name for p in _folder(kind).glob("*.json")}
        assert "valid.json" in names, kind
        assert len(names) >= 3, kind


@pytest.mark.parametrize(("kind", "path"), _fixtures(), ids=lambda v: v.stem if isinstance(v, Path) else v)
def test_fixtures(kind: str, path: Path) -> None:
    case: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    model = NEUTRAL_KINDS[kind]
    if path.name == "valid.json":
        parsed = model.model_validate(case)
        assert model.model_validate(parsed.model_dump(mode="json")) == parsed  # round trip
        return
    with pytest.raises(ValidationError) as caught:
        model.model_validate(case["payload"])
    assert case["rule"] in str(caught.value), case["rule"]


@pytest.mark.parametrize("kind", _MODEL_KINDS)
def test_payload_models_forbid_extra_fields(kind: str) -> None:
    valid = json.loads((_folder(kind) / "valid.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        NEUTRAL_KINDS[kind].model_validate({**valid, "surprise": 1})


def test_unit_suffix_fields_carry_the_unit_annotation() -> None:
    stories = model_kinds.Stories.model_json_schema()
    assert stories["properties"]["base_elevation_mm"]["x-eng-unit"] == "mm"
    story = stories["$defs"]["Story"]["properties"]
    assert story["height_mm"]["x-eng-unit"] == "mm"
    assert "x-eng-unit" not in story["name"]
    mats = model_kinds.Materials.model_json_schema()["$defs"]["Material"]["properties"]
    assert mats["E_MPa"]["x-eng-unit"] == "MPa"
    assert mats["gamma_kN_m3"]["x-eng-unit"] == "kN/m3"
    assert mats["nu_ratio"]["x-eng-unit"] == "1"


def test_names_are_one_to_two_hundred_characters() -> None:
    base = json.loads((_folder("model.stories/1") / "valid.json").read_text(encoding="utf-8"))
    for bad in ("", "x" * 201):
        base["stories"][0]["name"] = bad
        with pytest.raises(ValidationError):
            model_kinds.Stories.model_validate(base)
