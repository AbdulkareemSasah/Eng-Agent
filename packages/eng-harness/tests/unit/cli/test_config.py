"""Configuration discovery and sections (spec 0006 AC4, AC70, section 4.2.4)."""

import io
from argparse import Namespace
from pathlib import Path

import pytest

from eng_harness.cli import CliDeps, ConfigError, HarnessConfig, main
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


def test_default_workspace_and_option_reach_lookup(tmp_path: Path) -> None:
    # 1. Default workspace `%LOCALAPPDATA%/eng/workspaces/default` is resolved for config lookup; BOM is accepted.
    local = tmp_path / "local"
    default_ws = local / "eng" / "workspaces" / "default"
    default_ws.mkdir(parents=True)
    (default_ws / "harness.toml").write_text("[page]\nmax_body_bytes = 4096\n", encoding="utf-8-sig")

    seen: list[tuple[HarnessConfig, Path | None, dict[str, str]]] = []

    def handler(args: Namespace, deps: CliDeps) -> int:
        seen.append((args.config_data, args.config_path, dict(deps.environ)))
        return 0

    env_default = {"LOCALAPPDATA": str(local)}
    assert (
        main(
            ["status"],
            deps=CliDeps(stdout=io.StringIO(), stderr=io.StringIO(), environ=env_default, handlers={"status": handler}),
        )
        == 0
    )
    assert seen[-1][0].page.max_body_bytes == 4096
    assert seen[-1][1] == default_ws / "harness.toml"
    assert seen[-1][2] == env_default

    # 2. `--workspace DIR` overrides `ENG_WORKSPACE` for lookup and is passed on in `deps.environ`.
    explicit_ws = tmp_path / "explicit"
    explicit_ws.mkdir()
    (explicit_ws / "harness.toml").write_text("[page]\nmax_body_bytes = 8192\n", encoding="utf-8-sig")
    other_ws = tmp_path / "other"
    caller_env = {"LOCALAPPDATA": str(local), "ENG_WORKSPACE": str(other_ws)}
    assert (
        main(
            ["--workspace", str(explicit_ws), "status"],
            deps=CliDeps(stdout=io.StringIO(), stderr=io.StringIO(), environ=caller_env, handlers={"status": handler}),
        )
        == 0
    )
    assert seen[-1][0].page.max_body_bytes == 8192
    assert seen[-1][1] == explicit_ws / "harness.toml"
    assert seen[-1][2]["ENG_WORKSPACE"] == str(explicit_ws)
    assert caller_env["ENG_WORKSPACE"] == str(other_ws)  # caller's mapping is never mutated

    # 3. With no workspace configured, `main` still calls the handler with default config and `config_path=None`.
    assert (
        main(
            ["status"],
            deps=CliDeps(stdout=io.StringIO(), stderr=io.StringIO(), environ={}, handlers={"status": handler}),
        )
        == 0
    )
    no_ws_cfg, no_ws_path, _ = seen[-1]
    assert no_ws_cfg == HarnessConfig()
    assert no_ws_path is None

    # 4. `load_config` directly accepts a UTF-8 byte-order mark.
    assert load_config(default_ws / "harness.toml").page.max_body_bytes == 4096


def test_local_workspace_error_skips_workspace_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from eng_contract.store import FakeLocationProbe, LocationClass

    import eng_harness.cli as cli_mod

    non_local_ws = tmp_path / "network_ws"
    non_local_ws.mkdir()
    _write(non_local_ws / "harness.toml", "[page]\nmax_body_bytes = 9999\n")

    explicit = _write(tmp_path / "explicit.toml", "[page]\nmax_body_bytes = 2048\n")
    from_env = _write(tmp_path / "env.toml", "[page]\nmax_body_bytes = 4096\n")

    monkeypatch.setattr(cli_mod, "default_location_probe", lambda: FakeLocationProbe(default=LocationClass.NETWORK))

    seen: list[tuple[HarnessConfig, Path | None, dict[str, str]]] = []

    def handler(args: Namespace, deps: CliDeps) -> int:
        seen.append((args.config_data, args.config_path, dict(deps.environ)))
        return 0

    # 1. Resolver raises LocalWorkspaceError: workspace harness.toml is not read; handler runs with defaults.
    env_ws = {"ENG_WORKSPACE": str(non_local_ws)}
    assert (
        main(
            ["status"],
            deps=CliDeps(stdout=io.StringIO(), stderr=io.StringIO(), environ=env_ws, handlers={"status": handler}),
        )
        == 0
    )
    assert len(seen) == 1
    assert seen[0][0] == HarnessConfig()
    assert seen[0][1] is None
    assert seen[0][2] == env_ws

    # 2. Explicitly configured `--config` remains eligible when workspace resolution fails.
    assert (
        main(
            ["--config", str(explicit), "status"],
            deps=CliDeps(stdout=io.StringIO(), stderr=io.StringIO(), environ=env_ws, handlers={"status": handler}),
        )
        == 0
    )
    assert len(seen) == 2
    assert seen[1][0].page.max_body_bytes == 2048
    assert seen[1][1] == explicit

    # 3. `ENG_HARNESS_CONFIG` remains eligible when `ENG_WORKSPACE` forces a relative-path LocalWorkspaceError.
    env_both = {"ENG_WORKSPACE": "relative/ws", "ENG_HARNESS_CONFIG": str(from_env)}
    assert (
        main(
            ["status"],
            deps=CliDeps(stdout=io.StringIO(), stderr=io.StringIO(), environ=env_both, handlers={"status": handler}),
        )
        == 0
    )
    assert len(seen) == 3
    assert seen[2][0].page.max_body_bytes == 4096
    assert seen[2][1] == from_env
    assert seen[2][2] == env_both
