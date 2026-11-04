"""Package skeleton tests (plan task T1; spec 0001 AC1)."""

import importlib
import pkgutil
import tomllib
from pathlib import Path

import eng_harness

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def _table(name: str) -> dict[str, object]:
    with (PACKAGE_ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    table = data[name]
    assert isinstance(table, dict)
    return table


def _public_modules() -> list[str]:
    tool = _table("tool")["eng-gate"]
    assert isinstance(tool, dict)
    modules = tool["public_modules"]
    assert isinstance(modules, list)
    return [str(module) for module in modules]


def test_version_matches_project() -> None:
    assert eng_harness.__version__ == _table("project")["version"]


def test_public_modules_import() -> None:
    modules = _public_modules()
    assert "eng_harness" in modules
    for name in modules:
        assert importlib.import_module(name).__name__ == name


def test_private_modules_are_underscored() -> None:
    public = set(_public_modules())
    for info in pkgutil.walk_packages(eng_harness.__path__, prefix="eng_harness."):
        if info.name in public:
            continue
        parts = info.name.split(".")[1:]
        assert any(part.startswith("_") for part in parts), info.name
