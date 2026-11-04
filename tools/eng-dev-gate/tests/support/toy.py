"""Fixture: a toy uv workspace inside a temporary repository (root pyproject, gate.yml, member packages)."""

from __future__ import annotations

from support.repo import Repo

GATE_YML = """bootstrap:
  enabled: true
  gate_branch: build/v1
main_branch: main
spec_globs: ['**/docs/specs/*.md']
plan_globs: ['**/docs/plans/*.md']
test_globs: ['**/tests/**']
generated_globs: ['uv.lock']
spike_globs: ['spikes/**']
limits:
  diff_lines: 200
  max_task_lines: 400
  test_run_seconds: 600
  max_file_bytes: 1048576
"""

CLEAN_MODULE = (
    '"""A clean module."""\n\n\n'
    "def double(value: int) -> int:\n"
    '    """Return twice ``value``."""\n'
    "    return value * 2\n"
)


def root_pyproject(members: list[str]) -> str:
    """Return the toy root ``pyproject.toml`` with the baseline ruff and strict mypy tables."""
    listed = ", ".join(f'"{m}"' for m in members)
    return (
        '[project]\nname = "toy-root"\nversion = "0"\nrequires-python = ">=3.14"\ndependencies = []\n'
        f"[tool.uv]\npackage = false\n[tool.uv.workspace]\nmembers = [{listed}]\n"
        '[tool.ruff]\ntarget-version = "py314"\nline-length = 120\n'
        '[tool.ruff.lint]\nselect = ["E", "W", "F", "I"]\n'
        '[tool.mypy]\nstrict = true\npython_version = "3.14"\n'
    )


def member_pyproject(name: str) -> str:
    """Return the ``pyproject.toml`` of a toy member (``name`` is also its import name)."""
    return f'[project]\nname = "{name}"\nversion = "0.1.0"\nrequires-python = ">=3.14"\ndependencies = []\n'


def make_workspace(repo: Repo, names: list[str], module: str = CLEAN_MODULE) -> None:
    """Write a toy workspace with one member ``pkgs/<name>`` per name, each with ``module`` as ``src/<name>/mod.py``."""
    files = {
        "pyproject.toml": root_pyproject([f"pkgs/{n}" for n in names]),
        ".gate/gate.yml": GATE_YML,
    }
    for name in names:
        files[f"pkgs/{name}/pyproject.toml"] = member_pyproject(name)
        files[f"pkgs/{name}/src/{name}/__init__.py"] = ""
        files[f"pkgs/{name}/src/{name}/mod.py"] = module
    repo.commit(files)
