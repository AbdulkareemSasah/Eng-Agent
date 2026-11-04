"""Template model tests (plan 0004 task T1; spec 0004 AC1 to AC6).

Fixtures are synthetic: every value is a placeholder, not an engineering value.
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest

from eng_harness.templates import Entry, Template, TemplateInvalid

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "templates" / "synthetic-full-0.1.0.json"
FILE_NAME = "synthetic-full-0.1.0.template.yaml"
CITE = "Synthetic placeholder, not an engineering value"


def _data() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return loaded


def _with_entry(key: str, entry: dict[str, Any]) -> dict[str, Any]:
    data = _data()
    data["materials"] = {"alpha": {key: entry}}
    return data


def _refused(data: object, file_name: str | None = FILE_NAME) -> TemplateInvalid:
    with pytest.raises(TemplateInvalid) as caught:
        Template.from_data(data, file_name=file_name)
    return caught.value


def _entry(value: object, unit: str | None = "MPa", **extra: object) -> dict[str, Any]:
    return {"value": value, "unit": unit, "citation": CITE, **extra}


def _bound(value: float, unit: str = "MPa") -> dict[str, Any]:
    return {"value": value, "unit": unit, "source": "Synthetic placeholder bound"}


def test_valid_template_loads() -> None:
    template = Template.from_data(_data(), file_name=FILE_NAME)
    assert template.meta.name == "synthetic-full"
    assert template.is_draft
    for section in (
        template.materials,
        template.sections,
        template.loads,
        template.combinations,
        template.limits,
        template.analysis,
        template.modeling,
        template.drawing,
    ):
        assert section
    leaf = template.materials["alpha"]["strength_MPa"]
    assert isinstance(leaf, Entry)
    assert (leaf.value, leaf.unit, leaf.citation) == (1, "MPa", CITE)
    unitless = template.analysis["method"]
    assert isinstance(unitless, Entry)
    assert unitless.unit is None
    assert [item.path for item in template.ask_each_run] == [
        "limits.ratio_limit_ratio",
        "analysis.stories",
        "analysis.mode",
    ]


def test_empty_sections_are_allowed() -> None:
    data = {"schema": "eng-template/1", "meta": _data()["meta"]}
    template = Template.from_data(data, file_name=FILE_NAME)
    assert template.materials == {}
    assert template.ask_each_run == []


@pytest.mark.parametrize("citation", [None, "", "   ", "short", "x" * 501])
def test_citation_required(citation: object) -> None:
    entry: dict[str, Any] = {"value": 1, "unit": "MPa", "citation": citation}
    error = _refused(_with_entry("strength_MPa", entry))
    assert (error.reason, error.path) == ("citation_missing", "materials.alpha.strength_MPa")


def test_citation_absent_key_is_missing() -> None:
    error = _refused(_with_entry("strength_MPa", {"value": 1, "unit": "MPa"}))
    assert error.reason == "citation_missing"


@pytest.mark.parametrize("citation", ["x" * 8, "x" * 500])
def test_citation_length_limits_are_inclusive(citation: str) -> None:
    entry = {"value": 1, "unit": "MPa", "citation": citation}
    Template.from_data(_with_entry("strength_MPa", entry), file_name=FILE_NAME)


def test_extra_keys_forbidden() -> None:
    top = _data()
    top["scripts"] = {}
    assert _refused(top).reason == "unknown_key"
    meta = _data()
    meta["meta"]["formula"] = "1+1"
    assert _refused(meta).reason == "unknown_key"
    error = _refused(_with_entry("strength_MPa", _entry(1, expr="2*3")))
    assert (error.reason, error.path) == ("unknown_key", "materials.alpha.strength_MPa.expr")
    ask = _data()
    ask["ask_each_run"][0]["default"] = 3
    assert _refused(ask).reason == "unknown_key"


def test_string_value_is_never_evaluated() -> None:
    template = Template.from_data(_with_entry("note", _entry("1+1", None)), file_name=FILE_NAME)
    leaf = template.materials["alpha"]["note"]
    assert isinstance(leaf, Entry)
    assert leaf.value == "1+1"


@pytest.mark.parametrize(
    ("key", "unit"),
    [
        ("strength_MPa", "kPa"),
        ("strength_MPa", None),
        ("depth_mm", "m"),
        ("moment_kNm", "kN*m"),
        ("name", "mm"),
        ("drift_ratio", None),
    ],
)
def test_canonical_units_only(key: str, unit: str | None) -> None:
    error = _refused(_with_entry(key, _entry(1, unit)))
    assert (error.reason, error.path) == ("unit_mismatch", f"materials.alpha.{key}")


@pytest.mark.parametrize(
    ("key", "unit"),
    [("strength_MPa", "MPa"), ("moment_kNm", "kN.m"), ("load_kN_m3", "kN/m3"), ("temp_C", "degC"), ("x_ratio", "1")],
)
def test_canonical_unit_accepted(key: str, unit: str) -> None:
    Template.from_data(_with_entry(key, _entry(1, unit)), file_name=FILE_NAME)


def test_values_and_bounds() -> None:
    for bad in (math.nan, math.inf, -math.inf, True, "1", None, [math.nan]):
        assert _refused(_with_entry("strength_MPa", _entry(bad))).reason == "value_invalid"

    bounds = {"min": _bound(1), "max": _bound(3)}
    Template.from_data(_with_entry("strength_MPa", _entry(2, bounds=bounds)), file_name=FILE_NAME)
    for value in (0.5, 3.5):
        error = _refused(_with_entry("strength_MPa", _entry(value, bounds=bounds)))
        assert (error.reason, error.path) == ("out_of_bounds", "materials.alpha.strength_MPa")

    bad_bounds: list[object] = [
        {"min": _bound(3), "max": _bound(1)},
        {"min": {"value": 1, "unit": "MPa"}},
        {"min": {"value": 1, "unit": "MPa", "source": "   "}},
        {"min": _bound(1, "kPa")},
        {},
    ]
    for bad in bad_bounds:
        assert _refused(_with_entry("strength_MPa", _entry(2, bounds=bad))).reason == "bounds_invalid"
    text = _entry("a", None, bounds={"min": _bound(1, "1")})
    assert _refused(_with_entry("label", text)).reason == "bounds_invalid"


@pytest.mark.parametrize("name", ["Upper", "1abc", "has space", "a" * 65, "", "under.score"])
def test_meta_name_rules(name: str) -> None:
    data = _data()
    data["meta"]["name"] = name
    assert _refused(data, None).reason == "meta_invalid"


@pytest.mark.parametrize("version", ["1", "1.0", "01.0.0", "1.0.0-", "v1.0.0", "1.0.0+", "1.0.0-01"])
def test_meta_version_must_be_semver(version: str) -> None:
    data = _data()
    data["meta"]["version"] = version
    assert _refused(data, None).reason == "meta_invalid"


@pytest.mark.parametrize("version", ["0.1.0", "1.2.3-rc.1", "1.0.0+build.5", "1.0.0-alpha+001"])
def test_meta_semver_accepted(version: str) -> None:
    data = _data()
    data["meta"]["version"] = version
    Template.from_data(data, file_name=f"synthetic-full-{version}.template.yaml")


def test_meta_rules() -> None:
    data = _data()
    data["meta"]["name"] = "plain"
    assert _refused(data, None).reason == "meta_invalid"  # synthetic: true needs the synthetic- prefix
    converse = _data()
    converse["meta"]["synthetic"] = False
    assert _refused(converse, None).reason == "meta_invalid"  # the prefix needs synthetic: true
    for name in ("synthetic-full-0.1.0.yaml", "other-0.1.0.template.yaml", "synthetic-full-0.2.0.template.yaml"):
        assert _refused(_data(), name).reason == "meta_invalid"
    for key, value in (("status", "final"), ("extends", "no-version"), ("description", "x" * 501)):
        bad = _data()
        bad["meta"][key] = value
        assert _refused(bad, None).reason == "meta_invalid"
    plain = _data()
    plain["meta"].update(name="plain", synthetic=False, extends="parent@1.0.0", status="approved")
    template = Template.from_data(plain, file_name="plain-0.1.0.template.yaml")
    assert not template.is_draft
    assert template.meta.extends == "parent@1.0.0"


def test_schema_marker_and_shapes() -> None:
    wrong = _data()
    wrong["schema"] = "eng-template/2"
    assert _refused(wrong).reason == "meta_invalid"
    assert _refused([1]).reason == "value_invalid"
    bad_section = _data()
    bad_section["loads"] = ["a"]
    assert _refused(bad_section).reason == "value_invalid"
    bad_key = _data()
    bad_key["loads"] = {"bad key": {"x": _entry(1, None)}}
    assert _refused(bad_key).reason == "unknown_key"
    scalar = _data()
    scalar["loads"] = {"floor": 3}
    assert _refused(scalar).reason == "value_invalid"


@pytest.mark.parametrize(
    "item",
    [
        {"path": "a.b_MPa", "label": "x", "kind": "quantity", "unit": "kPa"},
        {"path": "a.b", "label": "x", "kind": "quantity", "unit": "kPa"},
    ],
)
def test_ask_item_unit_must_match_suffix(item: dict[str, Any]) -> None:
    data = _data()
    data["ask_each_run"] = [item]
    assert _refused(data).reason == "unit_mismatch"


@pytest.mark.parametrize(
    "item",
    [
        {"path": "a.b", "label": "x", "kind": "count", "unit": "mm"},
        {"path": "a.b", "label": "x", "kind": "choice", "choices": ["only"]},
        {"path": "a.b", "label": "x", "kind": "text", "choices": ["a", "b"]},
        {"path": "a.b", "label": "x" * 121, "kind": "text"},
        {"path": "a b", "label": "x", "kind": "text"},
        {"path": "a.b", "label": "x", "kind": "magic"},
    ],
)
def test_ask_item_rules(item: dict[str, Any]) -> None:
    data = _data()
    data["ask_each_run"] = [item]
    assert _refused(data).reason == "value_invalid"
