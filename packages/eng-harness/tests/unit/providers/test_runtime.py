"""Phase-1 assembly of the decision runtime (spec 0009 AC49; plan 0009 T10a; gap PR-G1).

No provider is built, no release is kept and no point policy is read; each provider and each dropped release is
reported in the warnings and in the summary, and nothing in either holds an endpoint, a `key_ref` or a header.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from eng_contract.store import LocationClass, Workspace

from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings, ShadowRelease
from eng_harness.providers import DecisionRuntime, ProvidersConfig, assemble_decision_runtime, load_providers_config

# Built at runtime so the file holds no credential-shaped literal (secrets step).
KEY_REF = "-".join(("ref", "secret", "name"))
HOST = "endpoint-host.example.test"
DECISION: dict[str, Any] = {
    "backend": "openrouter",
    "base_url": f"https://{HOST}/api/v1",
    "model": "vendor/model-x",
    "model_version": "2026-01",
    "key_ref": KEY_REF,
    "request_timeout_ms": 1500,
}
LLM: dict[str, Any] = {
    "name": "local-llm",
    "base_url": "http://127.0.0.1:8080/v1",
    "model": "vendor/model-y",
    "model_version": "2026-02",
    "local": True,
    "request_timeout_ms": 20000,
    "max_output_tokens": 512,
}
RELEASE = ShadowRelease(point_version=1, basis="evaluation", record="eval_1")
EMPTY: dict[str, Any] = {"providers": [], "released": {}, "dropped_releases": []}


def _workspace(tmp_path: Path) -> Workspace:
    return Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)


def _config(decision: dict[str, Any] | None = None, llm: dict[str, Any] | None = None) -> ProvidersConfig:
    table = {k: v for k, v in (("decision", decision), ("llm", llm)) if v is not None}
    return load_providers_config(table)


def _assemble(
    tmp_path: Path,
    config: ProvidersConfig,
    settings: DecisionSettings | None = None,
    policies: dict[str, DecisionPolicy] | None = None,
) -> DecisionRuntime:
    return assemble_decision_runtime(config, settings or DecisionSettings(), _workspace(tmp_path), policies or {})


def test_no_provider_table_gives_phase1_runtime(tmp_path: Path) -> None:
    runtime = _assemble(tmp_path, _config())
    assert runtime.model is None
    assert runtime.llm is None
    assert runtime.releases == {}
    assert runtime.warnings == ()
    assert dict(runtime.summary) == EMPTY
    assert not (tmp_path / "ws").exists()  # nothing is created in the workspace


def test_configured_provider_not_built_is_reported(tmp_path: Path) -> None:
    runtime = _assemble(tmp_path, _config({**DECISION, "request_timeout_ms": 100}, LLM))
    assert runtime.model is None
    assert runtime.llm is None
    assert runtime.summary["providers"] == [
        {"name": "openrouter", "model": "vendor/model-x", "version": "2026-01", "is_local": False, "tier": 2,
         "status": "not_implemented"},
        {"name": "local-llm", "model": "vendor/model-y", "version": "2026-02", "is_local": True, "tier": 3,
         "status": "not_implemented"},
    ]  # fmt: skip
    assert runtime.warnings == (
        "request_timeout_below_policy: providers.decision",
        "provider openrouter (providers.decision) is not built: PR-G1",
        "provider local-llm (providers.llm) is not built: PR-G1",
    )


@pytest.mark.parametrize("policies", [{}, {"pick": DecisionPolicy(), "other": DecisionPolicy(shadow=True)}])
def test_no_release_kept_without_verification(tmp_path: Path, policies: dict[str, DecisionPolicy]) -> None:
    settings = DecisionSettings(shadow_released={"pick_b": RELEASE, "pick_a": RELEASE})
    runtime = _assemble(tmp_path, _config(), settings, policies)
    assert runtime.releases == {}
    assert dict(runtime.summary) == {
        **EMPTY,
        "dropped_releases": [{"point": "pick_a", "reason": "PR-G1"}, {"point": "pick_b", "reason": "PR-G1"}],
    }
    assert runtime.warnings == (
        "release of point pick_a is dropped, the point stays in shadow: PR-G1",
        "release of point pick_b is dropped, the point stays in shadow: PR-G1",
    )


def test_phase1_summary_has_no_secrets(tmp_path: Path) -> None:
    settings = DecisionSettings(shadow_released={"pick": RELEASE})
    runtime = _assemble(tmp_path, _config({**DECISION, "request_timeout_ms": 100}, LLM), settings)
    text = json.dumps(dict(runtime.summary)) + "\n".join(runtime.warnings)
    for needle in (KEY_REF, HOST, "https://", "127.0.0.1", "api/v1", "key_ref", "base_url", "header", "eval_1"):
        assert needle not in text
    assert json.loads(json.dumps(dict(runtime.summary))) == dict(runtime.summary)  # a plain JSON object
