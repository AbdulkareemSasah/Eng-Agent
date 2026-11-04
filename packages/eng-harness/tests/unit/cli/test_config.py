"""Configuration discovery and sections (spec 0006 AC4, section 4.2.4)."""

from pathlib import Path

import pytest

from eng_harness.cli import ConfigError, HarnessConfig
from eng_harness.cli._config import load_config, resolve_config_path


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_discovery_and_sections(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    in_workspace = _write(workspace / "harness.toml", "[page]\nmax_body_bytes = 100\n")
    from_env = _write(tmp_path / "env.toml", "[page]\nmax_body_bytes = 200\n")
    explicit = _write(tmp_path / "arg.toml", "[page]\nmax_body_bytes = 300\n")
    env = {"ENG_HARNESS_CONFIG": str(from_env)}
    assert resolve_config_path(explicit, env, workspace) == explicit
    assert resolve_config_path(None, env, workspace) == from_env
    assert resolve_config_path(None, {}, workspace) == in_workspace
    assert resolve_config_path(None, {}, tmp_path) is None
    assert load_config(None) == HarnessConfig()
    config = load_config(
        _write(
            tmp_path / "all.toml",
            '[engine]\ndefault_mode = "approve_each_write"\nengineer = "A. Name"\nmax_attempts_cap = 4\n'
            "[progress]\nheartbeat_s = 5\nstale_after_heartbeats = 2\nhistory_runs = 7\nmin_samples = 2\n"
            "queue_lines = 50\n[page]\nopen_browser = false\nack_timeout_s = 3\nmax_failed_requests = 4\n"
            'display_max_chars = 80\n[project_lane.tool_a]\nrecord = "gap-1"\n'
            "[providers.decision]\nanything = 1\n[servers.csi]\nx = 1\n",
        )
    )
    assert config.engine.default_mode == "approve_each_write"
    assert config.engine.max_attempts_cap == 4
    assert config.progress.heartbeat_s == 5
    assert config.page.open_browser is False
    assert config.page.max_body_bytes == 32768
    assert config.project_lane["tool_a"].record == "gap-1"
    assert "decision" in config.providers
    defaults = HarnessConfig()
    assert (defaults.engine.default_mode, defaults.progress.heartbeat_s, defaults.page.display_max_chars) == (
        "work_on_copy",
        10,
        500,
    )
    assert (defaults.progress.stale_after_heartbeats, defaults.progress.min_samples) == (3, 3)


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("[page]\nbogus = 1\n", "page.bogus"),
        ('[page]\nmax_body_bytes = "x"\n', "page.max_body_bytes"),
        ("[progress]\nheartbeat_s = 0\n", "progress.heartbeat_s"),
        ("[progress]\nstale_after_heartbeats = 1\n", "progress.stale_after_heartbeats"),
        ('[engine]\ndefault_mode = "reckless"\n', "engine.default_mode"),
        ('[engine]\nengineer = ""\n', "engine.engineer"),
        ("[unknown]\na = 1\n", "unknown"),
        ("[page\n", "bad.toml"),
    ],
)
def test_invalid_configuration_names_the_key(tmp_path: Path, text: str, key: str) -> None:
    with pytest.raises(ConfigError) as caught:
        load_config(_write(tmp_path / "bad.toml", text))
    assert caught.value.key == key


def test_missing_explicit_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        resolve_config_path(tmp_path / "none.toml", {}, None)
    with pytest.raises(ConfigError):
        resolve_config_path(None, {"ENG_HARNESS_CONFIG": str(tmp_path / "none.toml")}, None)
