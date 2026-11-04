"""Fixture: a judged tree whose member is installable, and a separate gate root, for the PR-mode ``tests`` step.

The member ``a`` has a build system and no ``pythonpath`` setting, so its tests import ``a`` only when ``a`` is
installed in the interpreter that runs them. The gate under test runs in the environment of this very test session,
which does not contain ``a``: that is the situation of a pull-request run (spec 4.16, B-059).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from support.coverage_toy import FULL_TESTS, MODULE
from support.repo import Repo, make_repo
from support.toy import GATE_YML

ROOT_PYPROJECT = (
    '[project]\nname = "toy-root"\nversion = "0"\nrequires-python = ">=3.14"\ndependencies = []\n'
    '[tool.uv]\npackage = false\n[tool.uv.workspace]\nmembers = ["pkgs/a"]\n'
    '[dependency-groups]\ndev = ["pytest>=9.2.0", "coverage>=7.14.0"]\n'
)
GATE_ROOT_PYPROJECT = (
    '[project]\nname = "toy-gate-root"\nversion = "0"\nrequires-python = ">=3.14"\ndependencies = []\n'
    "[tool.uv]\npackage = false\n"
)


def member_pyproject(line: int = 95, branch: int = 90) -> str:
    """Return the ``pyproject.toml`` of the installable toy member ``a`` (no ``pythonpath``, a uv build system)."""
    return (
        '[project]\nname = "a"\nversion = "0.1.0"\nrequires-python = ">=3.14"\ndependencies = []\n'
        '[build-system]\nrequires = ["uv_build>=0.11.32,<0.12"]\nbuild-backend = "uv_build"\n'
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        '[tool.eng-gate]\nprofile = "tool"\nlayer = "tool"\nimport_names = ["a"]\n'
        f"coverage_line = {line}\ncoverage_branch = {branch}\n"
    )


def make_judged_tree(
    root: Path, tests: str = FULL_TESTS, extra_files: dict[str, str] | None = None, **limits: int
) -> Repo:
    """Create the judged tree in ``root``: workspace root, member ``pkgs/a`` with ``tests`` and a fresh ``uv.lock``.

    ``extra_files`` are paths relative to the member; they are written before the lock file is made.
    """
    tree = make_repo(root)
    files = {
        "pyproject.toml": ROOT_PYPROJECT,
        ".gate/gate.yml": GATE_YML,
        "pkgs/a/pyproject.toml": member_pyproject(**limits),
        "pkgs/a/src/a/__init__.py": "",
        "pkgs/a/src/a/mod.py": MODULE,
        "pkgs/a/tests/test_mod.py": tests,
    }
    files.update({f"pkgs/a/{name}": text for name, text in (extra_files or {}).items()})
    tree.commit(files)
    subprocess.run(["uv", "lock"], cwd=root, check=True, capture_output=True)  # noqa: S607
    tree.commit({}, "chore: lock")
    return tree


def make_gate_root(root: Path) -> Repo:
    """Create a separate gate root: policy files only, and nothing the judged tree needs."""
    gate = make_repo(root)
    gate.commit({"pyproject.toml": GATE_ROOT_PYPROJECT, ".gate/gate.yml": GATE_YML})
    return gate
