"""Kind names, the registry and the neutral kinds (plan T11, T12; spec 4.10, AC44, AC46 to AC48)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds import NEUTRAL_KINDS, KindName, KindNotRegistered, KindRegistry
from eng_contract.kinds import model as model_kinds
from eng_contract.kinds.basis import DesignBasis as Basis
from eng_contract.kinds.issues import ModelCheck
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.params import ContractDefinitionError
from eng_contract.units import QUANTITY_KINDS

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
_OTHER_KINDS = (
    "forces.joint_reactions/1",
    "forces.member_end/1",
    "forces.story_drifts/1",
    "basis.design_basis/1",
    "basis.engineer_input/1",
    "verdicts.set/1",
    "issues.model_check/1",
)
_ALL_KINDS = _MODEL_KINDS + _OTHER_KINDS
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
    assert set(_ALL_KINDS) <= set(NEUTRAL_KINDS)
    assert NEUTRAL_KINDS["model.stories/1"] is model_kinds.Stories
    with pytest.raises(KindNotRegistered) as caught:
        NEUTRAL_KINDS["model.nothing/1"]
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
    return [(kind, path) for kind in _ALL_KINDS for path in sorted(_folder(kind).glob("*.json"))]


def test_every_kind_has_valid_and_invalid_fixtures() -> None:
    for kind in _ALL_KINDS:
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


@pytest.mark.parametrize("kind", _ALL_KINDS)
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


def test_registry_is_a_sized_mapping() -> None:
    assert len(NEUTRAL_KINDS) == len(list(NEUTRAL_KINDS)) >= len(_ALL_KINDS)


def test_combination_may_reference_load_cases_the_host_defines() -> None:
    payload = json.loads((_folder("model.load_set/1") / "valid.json").read_text(encoding="utf-8"))
    payload["combinations"][0]["items"][0]["case"] = {"case": "EQX", "case_type": "load_case", "step": "Max"}
    assert model_kinds.LoadSet.model_validate(payload).combinations[0].items[0].case.step == "Max"


def _valid(kind: str) -> dict[str, Any]:
    case: dict[str, Any] = json.loads((_folder(kind) / "valid.json").read_text(encoding="utf-8"))
    return case


def test_unit_annotations_of_forces() -> None:
    reactions = NEUTRAL_KINDS["forces.joint_reactions/1"].model_json_schema()["$defs"]["JointReaction"]["properties"]
    assert reactions["FX_kN"]["x-eng-unit"] == "kN"
    assert reactions["MZ_kNm"]["x-eng-unit"] == "kN.m"
    drifts = NEUTRAL_KINDS["forces.story_drifts/1"].model_json_schema()["$defs"]["StoryDrift"]["properties"]
    assert drifts["drift_ratio"]["x-eng-unit"] == "1"
    assert drifts["z_mm"]["x-eng-unit"] == "mm"


def _basis(**field: Any) -> Basis:
    payload = _valid("basis.design_basis/1")
    payload["fields"]["limits.drift_ratio"].update(field)
    return Basis.model_validate(payload)


def test_basis_sources() -> None:
    assert _basis().fields["limits.drift_ratio"].source == "template:office_rc@1"
    for source in ("engineer:Sam@2026-02-01T08:00:00.000Z", "model:res_01JABCDEFGHJKMNPQRSTVWXYZ0#/fields/a/value"):
        assert _basis(source=source, citation=None).fields["limits.drift_ratio"].source == source
    for bad in (
        "template:@1",
        "template:office_rc",
        "engineer:Sam@2026-02-30T08:00:00.000Z",
        "engineer:@2026-02-01T08:00:00.000Z",
        "model:",
        "other:x@1",
        "",
    ):
        with pytest.raises(ValidationError, match="malformed source"):
            _basis(source=bad, citation="x")
    with pytest.raises(ValidationError, match="citation"):
        _basis(citation=None)
    # a path without a unit suffix takes any known unit or none; a suffixed path takes exactly the suffix's unit
    payload = _valid("basis.design_basis/1")
    payload["fields"]["site.name"]["unit"] = "mm"
    assert Basis.model_validate(payload).fields["site.name"].unit == "mm"
    payload["fields"]["materials.cover_mm"]["unit"] = None
    with pytest.raises(ValidationError, match="does not match the unit suffix"):
        Basis.model_validate(payload)


def _basis_at(path: str, unit: str | None) -> Basis:
    payload = _valid("basis.design_basis/1")
    payload["fields"] = {path: {**payload["fields"]["site.name"], "unit": unit}}
    return Basis.model_validate(payload)


def test_basis_path_unit_suffixes() -> None:
    # every suffix of spec 4.7.2 is accepted at the end of the last segment with the canonical unit of its kind
    for kind in QUANTITY_KINDS.values():
        for path in (f"compare.value{kind.suffix}", f"compare.{kind.suffix}", f"a.b.c.d{kind.suffix}"):
            assert path in _basis_at(path, kind.canonical_unit).fields
    for path, unit in (("compare.stress_MPa", "MPa"), ("bounds.w_kN_m", "kN/m"), ("limits.drift_ratio", "1")):
        assert path in _basis_at(path, unit).fields
    assert "compare._MPa" in _basis_at("compare._MPa", "MPa").fields
    assert "compare.x_mm2_mm" in _basis_at("compare.x_mm2_mm", "mm").fields  # the longer suffix is not read as the end
    with pytest.raises(ValidationError, match=r"does not match the unit suffix \(MPa\)"):
        _basis_at("compare.stress_MPa", "kPa")
    with pytest.raises(ValidationError, match=r"does not match the unit suffix \(MPa\)"):
        _basis_at("compare._MPa", None)
    for bad in (
        "Compare.stress_MPa",  # capital in the first segment
        "compare_MPa.stress",  # a suffix only in the last segment
        "compare.Stress_MPa",  # capital before the suffix
        "compare.stress_Mpa",  # not written as the table writes it
        "compare.stress_mPa",
        "compare.stress_MPA",
        "compare.stress_MPa.max",  # suffix not at the end of the last segment
        "compare.stress_MPa_x",
        "compare.stress_MPax",
        "compare.stress_kN_mm",  # one suffix only
        "compare.x_MPa_mm",
        "stress_MPa",  # no dot
        "compare.stress.MPa",
        "compare.",
    ):
        with pytest.raises(ValidationError, match="String should match pattern"):
            _basis_at(bad, "MPa")


def test_basis_missing_lists_absent_and_unconfirmed() -> None:
    basis = Basis.model_validate(_valid("basis.design_basis/1"))
    assert basis.missing([]) == []
    assert basis.missing(["limits.drift_ratio", "site.name"]) == []
    assert basis.missing(["materials.cover_mm", "limits.drift_ratio", "loads.live_kPa"]) == [
        "materials.cover_mm",
        "loads.live_kPa",
    ]
    assert basis.missing(iter(["materials.cover_mm"])) == ["materials.cover_mm"]


def _set_with_ref(ref: str | None, traces: int = 1) -> dict[str, Any]:
    payload = _valid("verdicts.set/1")
    payload["verdicts"][0]["trace_ref"] = ref
    payload["traces"] = payload["traces"] * traces
    return payload


def test_verdict_set_trace_refs() -> None:
    assert VerdictSet.model_validate(_set_with_ref("#/traces/0")).verdicts[0].trace_ref == "#/traces/0"
    assert VerdictSet.model_validate(_set_with_ref("#/traces/1", traces=2))
    for ref, rule in (
        ("#/traces/1", "out of range"),
        ("res_01JABCDEFGHJKMNPQRSTVWXYZ0#/traces/0", "LocalTraceRef"),
        ("res_01JABCDEFGHJKMNPQRSTVWXYZ0", "LocalTraceRef"),
    ):
        with pytest.raises(ValidationError, match=rule):
            VerdictSet.model_validate(_set_with_ref(ref))
    # a host verdict may omit its trace; a set without traces holds no reference
    empty = _valid("verdicts.set/1")
    empty["verdicts"] = [empty["verdicts"][1]]
    empty["traces"] = []
    empty["counts"] = {"PASS": 0, "FAIL": 1, "NOT_APPLICABLE": 0, "NEEDS_ENGINEER": 0, "ERROR": 0}
    assert VerdictSet.model_validate(empty).draft is False
    empty["verdicts"][0]["trace_ref"] = "#/traces/0"
    with pytest.raises(ValidationError, match="out of range"):
        VerdictSet.model_validate(empty)


def test_model_check_counts_by_severity() -> None:
    payload = _valid("issues.model_check/1")
    assert ModelCheck.model_validate(payload).summary.errors == 1
    payload["issues"][1]["severity"] = "info"
    with pytest.raises(ValidationError, match="counts must match"):
        ModelCheck.model_validate(payload)
