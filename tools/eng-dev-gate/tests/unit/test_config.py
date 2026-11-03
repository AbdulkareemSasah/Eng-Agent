"""Tests of the package configuration, the floors and the root gate.yml (spec 4.12, section 5; AC48)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from eng_dev_gate.config import (
    FLOORS,
    ConfigError,
    PackageConfig,
    check_floors,
    load_gate_config,
    load_package_config,
    parse_package_config,
)
from eng_dev_gate.report import Severity

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
