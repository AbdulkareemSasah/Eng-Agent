"""Tests of the package configuration, the floors and the root gate.yml (spec 4.12, section 5; AC48)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from eng_dev_gate.checks import config_step
from eng_dev_gate.checks.registry import StepContext
from eng_dev_gate.config import (
    FLOORS,
    ConfigError,
    PackageConfig,
    check_floors,
    load_gate_config,
    load_package_config,
    parse_package_config,
)
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.toolrun import ToolResult
from eng_dev_gate.workspace import Member

ROOT = Path(__file__).resolve().parents[4]


def _table(**overrides: Any) -> dict[str, Any]:  # Any: TOML table values
    table: dict[str, Any] = {
        "profile": "tool", "layer": "tool", "import_names": ["pkg"], "coverage_line": 95, "coverage_branch": 90,
    }  # fmt: skip
    table.update(overrides)
    return table


def _codes(config: PackageConfig) -> list[str]:
    return [f.code for f in check_floors(config, "pyproject.toml")]


def test_floors() -> None:
    """AC48: thresholds below the floor of the profile are CF002; the floors are those of spec 4.12."""
    assert {p: (f.line, f.branch) for p, f in FLOORS.items()} == {
        "contract": (95, 90), "server": (85, 75), "codes": (95, 90), "harness": (85, 75), "tool": (95, 90),
    }  # fmt: skip
    assert _codes(parse_package_config(_table())) == []
    low_line = check_floors(parse_package_config(_table(coverage_line=94)), "pyproject.toml")
    assert [(f.code, f.severity, f.path) for f in low_line] == [("CF002", Severity.ERROR, "pyproject.toml")]
    assert _codes(parse_package_config(_table(coverage_branch=89))) == ["CF002"]
    assert _codes(parse_package_config(_table(coverage_line=10, coverage_branch=10))) == ["CF002", "CF002"]
    server = {"profile": "server", "layer": 2}
    assert _codes(parse_package_config(_table(**server, coverage_line=85, coverage_branch=75))) == []
    assert _codes(parse_package_config(_table(**server, coverage_line=84, coverage_branch=75))) == ["CF002"]
    harness = {"profile": "harness", "layer": 4, "coverage_line": 85, "coverage_branch": 75}
    assert _codes(parse_package_config(_table(**harness))) == []


def test_mutation_floor() -> None:
    """Spec 4.12: mutation_min is at least 80 when declared; required for contract and codes, and with R1 or R2."""
    assert _codes(parse_package_config(_table(mutation_min=80))) == []
    assert _codes(parse_package_config(_table(mutation_min=79))) == ["CF002"]
    assert _codes(parse_package_config(_table(r2_modules=["src/**"]))) == ["CF002"]
    assert _codes(parse_package_config(_table(r1_modules=["src/**"], mutation_min=80))) == []
    contract = {"profile": "contract", "layer": 1}
    assert _codes(parse_package_config(_table(**contract))) == ["CF002"]
    assert _codes(parse_package_config(_table(**contract, mutation_min=80))) == []
    codes = {"profile": "codes", "layer": 3}
    assert _codes(parse_package_config(_table(**codes))) == ["CF002"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"profile": "unknown"},
        {"layer": 2},  # inconsistent with profile tool
        {"import_names": []},
        {"coverage_line": 101},
        {"coverage_branch": -1},
        {"coverage_line": True},
        {"coverage_line": "95"},
        {"mutation_min": 101},
        {"surprise": 1},
        {"bootstrap": {"enabled": False}},  # package configuration cannot carry the mode (AC4)
        {"generated": [{"path": "a"}]},
        {"windows_tests": "tests/win"},
    ],
)
def test_invalid_table_is_cf001(overrides: dict[str, Any]) -> None:
    """An invalid [tool.eng-gate] table is CF001."""
    with pytest.raises(ConfigError) as caught:
        parse_package_config(_table(**overrides))
    assert caught.value.code == "CF001"


def test_optional_fields_and_generated() -> None:
    """Optional lists default to empty; generated entries carry path, module and args."""
    config = parse_package_config(_table(generated=[{"path": "docs/x.json", "module": "pkg.gen", "args": ["--x"]}]))
    assert (config.r1_modules, config.windows_tests, config.public_modules) == ([], [], [])
    assert config.generated[0].args == ["--x"]


def test_load_package_config(tmp_path: Path) -> None:
    """The table is read from pyproject.toml; a missing table is CF006, a broken file is CF001."""
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[tool.eng-gate]\nprofile = "tool"\nlayer = "tool"\nimport_names = ["p"]\n'
        "coverage_line = 95\ncoverage_branch = 90\n",
        encoding="utf-8",
    )
    assert load_package_config(path).profile == "tool"
    path.write_text("[project]\nname = 'x'\n", encoding="utf-8")
    with pytest.raises(ConfigError) as missing:
        load_package_config(path)
    assert missing.value.code == "CF006"
    path.write_text('[tool]\n"eng-gate" = 5\n', encoding="utf-8")
    with pytest.raises(ConfigError) as scalar:
        load_package_config(path)
    assert scalar.value.code == "CF001"
    path.write_text("[tool.eng-gate\n", encoding="utf-8")
    with pytest.raises(ConfigError) as broken:
        load_package_config(path)
    assert broken.value.code == "CF001"


def test_own_package_table_meets_floors() -> None:
    """The gate's own pyproject.toml parses and meets the floor of its profile."""
    config = load_package_config(ROOT / "tools" / "eng-dev-gate" / "pyproject.toml")
    assert check_floors(config, "tools/eng-dev-gate/pyproject.toml") == []


def test_root_gate_yml_initial_values() -> None:
    """The committed root gate.yml is valid with the initial values of spec 4.4 (bootstrap on, build/v1)."""
    config = load_gate_config(ROOT)
    assert config.bootstrap.enabled is True
    assert config.gate_branch == "build/v1"
    assert config.main_branch == "main"
    assert config.limits.max_task_lines == 400
    assert config.agents.unmanaged_ok == ["design/**"]
    assert "uv.lock" in config.generated_globs


# ---- config step: weakening rules (spec 4.12 table; AC49, AC54) ----

BASE = (
    '[project]\nname = "pkg"\nversion = "0.1.0"\n[tool.eng-gate]\nprofile = "tool"\nlayer = "tool"\n'
    'import_names = ["pkg"]\ncoverage_line = 95\ncoverage_branch = 90\n'
)
RULES = '["E", "W", "F", "I", "B", "UP", "SIM", "N", "S"]'
CLEAN_TABLES = (
    '[tool.ruff]\nline-length = 120\nsrc = ["src"]\nexclude = ["spikes"]\n'
    '[tool.ruff.lint]\nselect = ["E", "W", "F", "I", "B", "UP", "SIM", "N", "S", "RUF"]\n'
    '[tool.ruff.lint.per-file-ignores]\n"tests/**" = ["S101"]\n'
    '[tool.mypy]\nstrict = true\npython_version = "3.14"\nfiles = ["src"]\n'
    '[[tool.mypy.overrides]]\nmodule = ["yaml.*"]\nignore_missing_imports = true\n'
    '[tool.pytest.ini_options]\ntestpaths = ["tests"]\nminversion = "9"\n'
    'addopts = "-ra -q --strict-markers --strict-config --import-mode=importlib"\n'
    'filterwarnings = ["error", "default::DeprecationWarning"]\n'
)


class _NoRunner:
    def run(self, argv: Sequence[str], cwd: Path) -> ToolResult:
        raise AssertionError("the config step runs no tool")


def _config_step(tmp_path: Path, pyproject: str, files: dict[str, str] | None = None) -> list[Finding]:
    directory = tmp_path / "pkgs" / "pkg"
    directory.mkdir(parents=True)
    (directory / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    for name, text in (files or {}).items():
        (directory / name).write_text(text, encoding="utf-8")
    member = Member(name="pkg", path="pkgs/pkg", directory=directory)
    return config_step.config(StepContext(tmp_path, tmp_path, member, _NoRunner()))


def _step_codes(tmp_path: Path, pyproject: str) -> list[str]:
    return sorted(f.code for f in _config_step(tmp_path, pyproject))


def test_clean_tables_pass(tmp_path: Path) -> None:
    """The closed allowed set of the table in spec 4.12 raises no finding."""
    assert _config_step(tmp_path, BASE + CLEAN_TABLES) == []


@pytest.mark.parametrize(
    "extra",
    [
        f"[tool.ruff.lint]\nselect = {RULES}\nignore = ['E501']\n",
        f"[tool.ruff.lint]\nselect = {RULES}\nextend-ignore = ['E501']\n",
        '[tool.ruff.lint]\nselect = ["E", "W", "F", "I", "B", "UP", "SIM", "N"]\n',
        "[tool.ruff]\nline-length = 100\n",
        f'[tool.ruff.lint]\nselect = {RULES}\n[tool.ruff.lint.per-file-ignores]\n"src/**" = ["S101"]\n',
        f'[tool.ruff.lint]\nselect = {RULES}\n[tool.ruff.lint.per-file-ignores]\n"tests/**" = ["S101", "E501"]\n',
        f'[tool.ruff]\nexclude = ["src"]\n[tool.ruff.lint]\nselect = {RULES}\n',
        f'[tool.ruff]\nextend = "../../pyproject.toml"\n[tool.ruff.lint]\nselect = {RULES}\n',
        "[tool.mypy]\nstrict = false\n",
        "[tool.mypy]\npython_version = '3.14'\n",
        "[tool.mypy]\nstrict = true\nignore_errors = true\n",
        "[tool.mypy]\nstrict = true\nwarn_unreachable = true\n",
        '[tool.mypy]\nstrict = true\n[[tool.mypy.overrides]]\nmodule = "pkg.*"\nignore_missing_imports = true\n',
        '[tool.mypy]\nstrict = true\n[[tool.mypy.overrides]]\nmodule = ["yaml"]\ndisallow_untyped_defs = false\n',
        '[tool.pytest.ini_options]\naddopts = "-ra --deselect tests/a.py::t"\n',
        '[tool.pytest.ini_options]\naddopts = "-ra -k fast"\n',
        '[tool.pytest.ini_options]\naddopts = "-m slow"\n',
        '[tool.pytest.ini_options]\naddopts = "--ignore=tests/a.py"\n',
        '[tool.pytest.ini_options]\naddopts = "-p no:cacheprovider"\n',
        '[tool.pytest.ini_options]\nfilterwarnings = ["ignore::UserWarning"]\n',
        "[tool.pytest.ini_options]\nxfail_strict = false\n",
        "[tool.coverage.run]\nomit = ['src/x.py']\n",
        "[tool.coverage.report]\nfail_under = 1\n",
    ],
)
def test_weakening_rules(tmp_path: Path, extra: str) -> None:
    """AC49: each setting outside the allowed set is CF003."""
    assert "CF003" in _step_codes(tmp_path, BASE + extra)


@pytest.mark.parametrize(
    "name", ["pytest.ini", "tox.ini", "setup.cfg", "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini", ".coveragerc"]
)
def test_override_files_are_cf004(tmp_path: Path, name: str) -> None:
    """AC49: a configuration file beside the package's pyproject.toml is CF004."""
    findings = _config_step(tmp_path, BASE, {name: "\n"})
    assert [(f.code, f.severity) for f in findings] == [("CF004", Severity.ERROR)]
    assert name in findings[0].message


def test_rerun_plugins_are_cf005(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC49: pytest-rerunfailures, flaky and pytest-retry (process/05 section 3) are CF005, names normalised."""

    class _Dist:
        def __init__(self, name: str) -> None:
            self.metadata = {"Name": name}

    monkeypatch.setattr(
        config_step.importlib.metadata,
        "distributions",
        lambda: [_Dist("pytest"), _Dist("pytest_rerunfailures"), _Dist("Flaky"), _Dist("pytest-retry")],
    )
    assert [f.code for f in _config_step(tmp_path, BASE)] == ["CF005"] * 3


def test_invalid_table_and_floor_are_reported_not_raised(tmp_path: Path) -> None:
    """CF001 (invalid table, unreadable file), CF002 (below the floor) and CF006 (no table) are findings."""
    assert _step_codes(tmp_path, BASE.replace("coverage_line = 95", "coverage_line = 80")) == ["CF002"]
    assert _step_codes(tmp_path / "a", BASE.replace('layer = "tool"', "layer = 3")) == ["CF001"]
    assert _step_codes(tmp_path / "b", '[project]\nname = "pkg"\n') == ["CF006"]
    assert _step_codes(tmp_path / "c", "[tool.eng-gate\n") == ["CF001"]
    assert _step_codes(tmp_path / "d", '[tool]\n"eng-gate" = 5\n') == ["CF001"]
