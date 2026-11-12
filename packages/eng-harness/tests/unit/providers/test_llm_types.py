"""Structured output types for the language-model provider (spec 0009 AC21)."""

import pytest
from pydantic import ValidationError

from eng_harness.decisions.interfaces import ProviderOption, ProviderRequest
from eng_harness.providers._llm_types import build_output_type

_ENUM_REQUEST = ProviderRequest(
    request_id="dec_1",
    point="footing_fix_strategy",
    point_version=1,
    options=(
        ProviderOption(value="a", label="Option A"),
        ProviderOption(value="b", label="Option B"),
        ProviderOption(value="c", label="Option C"),
    ),
    state={"governing": "bearing"},
)

_REFS_REQUEST = ProviderRequest(
    request_id="dec_2",
    point="pick_member",
    point_version=2,
    options=(
        ProviderOption(value="0", label="First member"),
        ProviderOption(value="1", label="Second member"),
    ),
    state={"labels_field": ("North", "South")},
)


def test_output_type_is_strict() -> None:
    model = build_output_type(_ENUM_REQUEST)
    schema = model.model_json_schema()
    assert schema.get("additionalProperties") is False
    choice = schema["properties"]["choice"]
    assert choice["enum"] == ["a", "b", "c"]
    rationale = schema["properties"]["rationale"]
    assert rationale["minLength"] == 1
    assert rationale["maxLength"] == 300
    assert rationale["pattern"] == r"^\D+$"

    refs_model = build_output_type(_REFS_REQUEST)
    refs_choice = refs_model.model_json_schema()["properties"]["choice"]
    assert refs_choice["enum"] == ["0", "1"]

    good = model.model_validate({"choice": "b", "rationale": "Bearing governs."})
    assert good.choice == "b"

    with pytest.raises(ValidationError):
        model.model_validate({"choice": "d", "rationale": "Outside the options."})
    with pytest.raises(ValidationError):
        model.model_validate({"choice": "a", "rationale": "Has digit 2"})
    with pytest.raises(ValidationError):
        model.model_validate({"choice": "a", "rationale": "ok", "extra": "nope"})
