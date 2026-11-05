"""Provider configuration (spec 0009 section 3.1, AC1 to AC4): tables, endpoint rules, secret keys, timeouts."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_harness.providers import ProvidersConfig, load_providers_config

SECRET = "sk-test-VALUE-123"  # a synthetic value; it must never appear in a message

DECISION: dict[str, Any] = {
    "backend": "openrouter",
    "base_url": "https://example.test/api/v1",
    "model": "vendor/model-x",
    "model_version": "2026-01",
    "key_ref": "jev",
    "request_timeout_ms": 1500,
}
LLM: dict[str, Any] = {
    "base_url": "https://example.test/api/v1",
    "model": "vendor/model-y",
    "model_version": "2026-02",
    "key_ref": "llm",
    "request_timeout_ms": 20000,
    "max_output_tokens": 512,
}


def _load(decision: dict[str, Any] | None = None, llm: dict[str, Any] | None = None) -> ProvidersConfig:
    table: dict[str, Any] = {}
    if decision is not None:
        table["decision"] = decision
    if llm is not None:
        table["llm"] = llm
    return load_providers_config(table)


def _refused(table: dict[str, Any]) -> ContractError:
    with pytest.raises(ContractError) as info:
        load_providers_config(table)
    assert info.value.detail.code is ErrorCode.INVALID_ARGUMENT
    return info.value


def _field(table: dict[str, Any]) -> str | None:
    return _refused(table).detail.field


def test_valid_tables_and_refusals() -> None:
    config = _load(DECISION, LLM)
    assert config.decision is not None
    assert config.decision.backend == "openrouter"
    assert config.decision.name == "openrouter"  # default: the backend
    assert config.decision.local is False
    assert config.llm is not None
    assert config.llm.name == "llm"  # default
    assert config.llm.max_output_tokens == 512
    assert config.warnings == ()

    empty = load_providers_config({})
    assert empty.decision is None
    assert empty.llm is None
    assert load_providers_config({"decision": {**DECISION, "backend": "typesafe"}}).decision is not None

    assert _field({"decision": {**DECISION, "colour": 1}}) == "providers.decision.colour"
    assert _field({"other": {}}) == "providers.other"
    for required in ("base_url", "model", "model_version", "request_timeout_ms"):
        missing = {k: v for k, v in DECISION.items() if k != required}
        assert _field({"decision": missing}) == f"providers.decision.{required}"
    assert _field({"llm": {k: v for k, v in LLM.items() if k != "max_output_tokens"}}) == (
        "providers.llm.max_output_tokens"
    )
    assert _field({"decision": {k: v for k, v in DECISION.items() if k != "key_ref"}}) == "providers.decision.key_ref"
    assert _field({"decision": {**DECISION, "backend": "other"}}) == "providers.decision.backend"
    assert _field({"decision": {**DECISION, "name": "Bad Name"}}) == "providers.decision.name"
    assert _field({"decision": {**DECISION, "model": ""}}) == "providers.decision.model"
    assert _field({"decision": {**DECISION, "model_version": "x" * 41}}) == "providers.decision.model_version"
    assert _field({"llm": {**LLM, "max_output_tokens": 0}}) == "providers.llm.max_output_tokens"
    assert _field({"decision": "text"}) == "providers.decision"
    local = {k: v for k, v in DECISION.items() if k != "key_ref"}
    assert _load({**local, "base_url": "http://127.0.0.1:8080/v1", "local": True}).decision is not None


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/v1",  # http outside loopback
        "ftp://example.test/v1",
        "https://user:pw@example.test/v1",
        "https://example.test/v1?x=1",
        "https://example.test/v1?",
        "https://example.test/v1#frag",
        "https://example.test/v1#",
        "https://",
        "example.test/v1",
    ],
)
def test_endpoint_rules(url: str) -> None:
    assert _field({"decision": {**DECISION, "base_url": url}}) == "providers.decision.base_url"


def test_endpoint_rules_accepted_and_local() -> None:
    for url in ("http://localhost:11434/v1", "http://LOCALHOST/v1", "http://127.0.0.1/v1", "http://[::1]:80/v1"):
        assert _load({**DECISION, "base_url": url}).decision is not None
    local = {k: v for k, v in DECISION.items() if k != "key_ref"} | {"local": True}
    assert _load({**local, "base_url": "https://localhost/v1"}).decision is not None
    # local = true needs a loopback host, even over https
    assert _field({"decision": {**local, "base_url": "https://example.test/v1"}}) == "providers.decision.base_url"


@pytest.mark.parametrize("name", ["key", "api_key", "token", "secret", "password", "authorization", "API_Key", "Token"])
@pytest.mark.parametrize("table", ["decision", "llm"])
def test_secret_keys_refused(table: str, name: str) -> None:
    base = DECISION if table == "decision" else LLM
    error = _refused({table: {**base, name: SECRET}})
    text = str(error) + error.detail.message + (error.detail.hint or "") + repr(error.detail.received)
    assert name in error.detail.message
    assert "credential store" in error.detail.message
    assert SECRET not in text
    assert error.detail.received is None


def test_secret_value_never_in_other_messages() -> None:
    for table in (
        {"decision": {**DECISION, "request_timeout_ms": SECRET}},
        {"decision": {**DECISION, "backend": SECRET}},
        {"decision": {**DECISION, "base_url": f"https://u:{SECRET}@example.test/v1"}},
        {"decision": {**DECISION, "local": SECRET}},
    ):
        error = _refused(table)
        assert SECRET not in str(error) + repr(error.detail)


def test_timeout_ceiling() -> None:
    at_policy = _load({**DECISION, "request_timeout_ms": 1500}, {**LLM, "request_timeout_ms": 20000})
    assert at_policy.warnings == ()
    below = _load({**DECISION, "request_timeout_ms": 1499}, {**LLM, "request_timeout_ms": 19999})
    assert [(w.code, w.table) for w in below.warnings] == [
        ("request_timeout_below_policy", "providers.decision"),
        ("request_timeout_below_policy", "providers.llm"),
    ]
    assert _load({**DECISION, "request_timeout_ms": 1}).warnings[0].table == "providers.decision"
    assert _load({**DECISION, "request_timeout_ms": 90000}).warnings == ()
    for bad in (0, -5, 1.5, True, "1500"):
        assert _field({"decision": {**DECISION, "request_timeout_ms": bad}}) == "providers.decision.request_timeout_ms"
