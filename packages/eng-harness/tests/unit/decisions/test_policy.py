"""Decision policy, settings and small types (plan 0005 T1; spec 0005 AC6, AC7, section 4.2 and 4.3)."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings, ShadowRelease
from eng_harness.decisions.types import DecisionDefinitionError, Label, Pick, Rationale

GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden" / "decision_policy_defaults.json"


def test_defaults_match_golden() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert "12-decision-layer.md" in golden["source"]
    assert DecisionPolicy().model_dump() == golden["defaults"]


@pytest.mark.parametrize(
    "bad",
    [
        {"min_confidence": 0.84},
        {"min_confidence": 1.01},
        {"timeout_ms_model": 0},
        {"timeout_ms_llm": 0},
        {"unknown_field": 1},
    ],
)
def test_policy_bounds(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DecisionPolicy(**bad)  # type: ignore[arg-type]  # B-165: deliberately invalid values


def test_policy_accepts_boundaries_and_is_frozen() -> None:
    assert DecisionPolicy(min_confidence=0.85).min_confidence == 0.85
    assert DecisionPolicy(min_confidence=1.0).min_confidence == 1.0
    assert DecisionPolicy(timeout_ms_model=1).timeout_ms_model == 1
    with pytest.raises(ValidationError):
        DecisionPolicy().model = False


def test_settings_defaults_and_frozen() -> None:
    settings = DecisionSettings()
    assert (settings.max_options, settings.max_state_bytes) == (32, 4096)
    assert settings.local_only is False
    assert settings.export_enabled is False
    assert settings.sensitive_values == ()
    assert settings.extra_denied_tokens == ()
    assert dict(settings.shadow_released) == {}
    with pytest.raises(ValidationError):
        settings.max_options = 5
    with pytest.raises(ValidationError):
        DecisionSettings(max_options=0)
    with pytest.raises(ValidationError):
        DecisionSettings(unknown=1)  # type: ignore[call-arg]  # B-165: deliberately unknown field


def test_shadow_release_rules() -> None:
    release = ShadowRelease(point_version=1, basis="owner", record="owner decision")
    assert release.basis == "owner"
    with pytest.raises(ValidationError):
        ShadowRelease(point_version=0, basis="owner", record="x")
    with pytest.raises(ValidationError):
        ShadowRelease(point_version=1, basis="agent", record="x")  # type: ignore[arg-type]  # B-165: invalid basis
    with pytest.raises(ValidationError):
        ShadowRelease(point_version=1, basis="evaluation", record="")
    settings = DecisionSettings(shadow_released={"p": release})
    assert settings.shadow_released["p"] == release


@pytest.mark.parametrize("text", ["Bearing", "a" * 80, "plan size 2"])
def test_label_accepts(text: str) -> None:
    assert TypeAdapter(Label).validate_python(text) == text


@pytest.mark.parametrize("text", ["", "a" * 81, "a/b", "a\\b", "a@b", "a:b", "a\nb", "a\x00b", "a\x7fb"])
def test_label_refuses(text: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Label).validate_python(text)


@pytest.mark.parametrize("text", ["Only the bearing check fails.", "x", "y" * 300])
def test_rationale_accepts(text: str) -> None:
    assert TypeAdapter(Rationale).validate_python(text) == text


@pytest.mark.parametrize("text", ["", "z" * 301, "uses 2 bars", "arabic " + chr(0x663), "full " + chr(0xFF15)])
def test_rationale_refuses(text: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Rationale).validate_python(text)


def test_pick_holds_option_and_is_frozen() -> None:
    assert Pick(2).option == 2
    with pytest.raises(AttributeError):
        Pick(2).option = 3  # type: ignore[misc]  # B-165: mutation must be refused


def test_definition_error_is_value_error() -> None:
    assert issubclass(DecisionDefinitionError, ValueError)
