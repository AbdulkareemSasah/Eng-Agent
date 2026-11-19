"""`doctor` command: exit code passthrough, default callable, config path and env wiring (spec 0006 AC13; plan T16)."""

import io
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from eng_harness import doctor
from eng_harness.cli import CliDeps, ExitCode, main
from eng_harness.servers import ConfigError


def test_exit_code_passthrough() -> None:
    calls: list[dict[str, Any]] = []

    def fake_doctor(
        config_path: Path | None,
        *,
        json_output: bool,
        show_paths: bool,
        out: TextIO | None = None,
        env: Mapping[str, str] | None = None,
    ) -> int:
        calls.append(
            {
                "config_path": config_path,
                "json_output": json_output,
                "show_paths": show_paths,
                "out": out,
                "env": env,
            }
        )
        assert out is not None
        out.write("doctor-output\n")
        return 1 if json_output else 0

    for argv, expected_code, expected_json, expected_paths in [
        (["doctor"], 0, False, False),
        (["doctor", "--json", "--show-paths"], 1, True, True),
    ]:
        out, err = io.StringIO(), io.StringIO()
        deps = CliDeps(stdout=out, stderr=err, environ={}, doctor=fake_doctor)
        assert main(argv, deps=deps) == expected_code
        assert out.getvalue() == "doctor-output\n"
        assert err.getvalue() == ""
        assert calls[-1]["json_output"] is expected_json
        assert calls[-1]["show_paths"] is expected_paths
        assert calls[-1]["out"] is out


def test_doctor_default_is_doctor_run() -> None:
    assert CliDeps().doctor is doctor.run


def test_doctor_receives_config_path_and_environment(tmp_path: Path) -> None:
    seen: list[tuple[Path | None, Mapping[str, str] | None]] = []

    def recorder(
        config_path: Path | None,
        *,
        json_output: bool,
        show_paths: bool,
        out: TextIO | None = None,
        env: Mapping[str, str] | None = None,
    ) -> int:
        seen.append((config_path, env))
        return 0

    # 1. Found `harness.toml` in `--workspace` and updated `ENG_WORKSPACE` reach `doctor`.
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = ws / "harness.toml"
    cfg.write_text("[page]\nopen_browser = false\n", encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    assert (
        main(
            ["--workspace", str(ws), "doctor"],
            deps=CliDeps(stdout=out, stderr=err, environ={"FOO": "bar"}, doctor=recorder),
        )
        == ExitCode.OK
    )
    assert seen[-1][0] == cfg
    assert seen[-1][1] == {"FOO": "bar", "ENG_WORKSPACE": str(ws)}

    # 2. No `harness.toml` found -> `config_path` is `None`.
    out, err = io.StringIO(), io.StringIO()
    assert (
        main(
            ["doctor"],
            deps=CliDeps(stdout=out, stderr=err, environ={"BAR": "baz"}, doctor=recorder),
        )
        == ExitCode.OK
    )
    assert seen[-1][0] is None
    assert seen[-1][1] == {"BAR": "baz"}

    # 3. A `ConfigError` from `doctor` exits 2 naming the offending key.
    def failing(
        config_path: Path | None,
        *,
        json_output: bool,
        show_paths: bool,
        out: TextIO | None = None,
        env: Mapping[str, str] | None = None,
    ) -> int:
        raise ConfigError("servers.csi", "missing executable")

    out, err = io.StringIO(), io.StringIO()
    assert main(["doctor"], deps=CliDeps(stdout=out, stderr=err, environ={}, doctor=failing)) == ExitCode.USAGE
    assert "servers.csi" in err.getvalue()
