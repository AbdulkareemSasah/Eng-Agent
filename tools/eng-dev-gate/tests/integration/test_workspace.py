"""Tests of workspace member discovery from [tool.uv.workspace]."""

from __future__ import annotations

from pathlib import Path

import pytest
from eng_dev_gate.results import UsageError
from eng_dev_gate.workspace import discover_members
from support.repo import Repo


def _pyproject(name: str) -> str:
    return f'[project]\nname = "{name}"\nversion = "0.1.0"\n'


def _root(members: str, exclude: str = "") -> str:
    return f"[tool.uv.workspace]\nmembers = {members}\n{exclude}"


def test_discovers_members(repo: Repo) -> None:
    """Explicit paths and globs expand to members with name and POSIX path, sorted by path; excludes apply."""
    repo.write(
        {
            "pyproject.toml": _root('["tools/a", "packages/*"]', 'exclude = ["packages/skip"]\n'),
            "tools/a/pyproject.toml": _pyproject("pkg-a"),
            "packages/one/pyproject.toml": _pyproject("pkg-one"),
            "packages/skip/pyproject.toml": _pyproject("pkg-skip"),
            "packages/notes/readme.md": "no project here\n",
        }
    )
    members = discover_members(repo.root)
    assert [(m.name, m.path) for m in members] == [("pkg-one", "packages/one"), ("pkg-a", "tools/a")]
    assert members[0].directory == repo.root / "packages" / "one"


def test_missing_workspace_table_is_usage_error(repo: Repo) -> None:
    """A root without [tool.uv.workspace] is a configuration error."""
    repo.write({"pyproject.toml": "[project]\nname = 'x'\n"})
    with pytest.raises(UsageError):
        discover_members(repo.root)


def test_missing_root_pyproject_is_usage_error(tmp_path: Path) -> None:
    """No root pyproject.toml is a configuration error."""
    with pytest.raises(UsageError):
        discover_members(tmp_path)


def test_explicit_member_without_pyproject_is_usage_error(repo: Repo) -> None:
    """An explicit member path that has no pyproject.toml is reported, not skipped."""
    repo.write({"pyproject.toml": _root('["tools/gone"]'), "tools/gone/readme.md": "x\n"})
    with pytest.raises(UsageError):
        discover_members(repo.root)


def test_member_without_project_name_is_usage_error(repo: Repo) -> None:
    """A member whose pyproject.toml has no [project].name is invalid."""
    repo.write({"pyproject.toml": _root('["tools/a"]'), "tools/a/pyproject.toml": "[tool.x]\ny = 1\n"})
    with pytest.raises(UsageError):
        discover_members(repo.root)


def test_malformed_toml_is_usage_error(repo: Repo) -> None:
    """Malformed TOML exits 2."""
    repo.write({"pyproject.toml": "[tool.uv.workspace\n"})
    with pytest.raises(UsageError):
        discover_members(repo.root)
