"""Provider key management CLI (spec 0009 AC8)."""

import io
from pathlib import Path

import pytest
from fakes.credential_stores import FakeCredentialStore

from eng_harness.providers import __main__ as providers_cli

_HARNESS = """
[providers.decision]
backend = "openrouter"
base_url = "https://example.test/v1"
model = "vendor/model-x"
model_version = "2026-01"
key_ref = "jev"
request_timeout_ms = 1500

[providers.llm]
base_url = "https://example.test/v1"
model = "vendor/model-y"
model_version = "2026-02"
key_ref = "llm"
request_timeout_ms = 20000
max_output_tokens = 512
"""
_SECRET = "-".join(("sk", "cli", "secret"))


@pytest.fixture
def harness_config(tmp_path: Path) -> Path:
    path = tmp_path / "harness.toml"
    path.write_text(_HARNESS, encoding="utf-8")
    return path


@pytest.fixture
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeCredentialStore:
    store = FakeCredentialStore()
    monkeypatch.setattr(providers_cli, "build_store", lambda: store)
    return store


def test_set_key_status_delete(
    harness_config: Path,
    fake_store: FakeCredentialStore,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(f"{_SECRET}\n".encode()), encoding="utf-8"))
    assert providers_cli.main(["--config", str(harness_config), "set-key", "jev"]) == 0
    assert fake_store.get("jev") is not None

    with pytest.raises(SystemExit) as refused:
        providers_cli.main(["--config", str(harness_config), "set-key", "jev", _SECRET])
    assert refused.value.code == 2

    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    with pytest.raises(SystemExit) as empty:
        providers_cli.main(["--config", str(harness_config), "set-key", "llm"])
    assert empty.value.code == 2

    assert providers_cli.main(["--config", str(harness_config), "status"]) == 0
    status = capsys.readouterr().out
    assert "jev: key present" in status
    assert "llm: key absent" in status
    assert _SECRET not in status

    assert providers_cli.main(["--config", str(harness_config), "delete-key", "jev"]) == 0
    capsys.readouterr()
    assert providers_cli.main(["--config", str(harness_config), "status"]) == 0
    status = capsys.readouterr().out
    assert "jev: key absent" in status
