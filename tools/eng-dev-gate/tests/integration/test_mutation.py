"""Integration test of the ``mutation`` command with the real mutmut on a toy workspace (AC53)."""

from __future__ import annotations

import json
import sys

import pytest
from support.coverage_toy import FULL_TESTS, MODULE, PARTIAL_TESTS, member_pyproject
from support.repo import Repo
from support.toy import GATE_YML, root_pyproject

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="B-049: mutmut has no native Windows support; expires 2027-06-30"
)


def _toy(repo: Repo, tests: str) -> str:
    """Commit a base with a trivial module, then the change to the real module; return the base SHA."""
    base = repo.commit(
        {
            "pyproject.toml": root_pyproject(["pkgs/a"]),
            ".gate/gate.yml": GATE_YML,
            "pkgs/a/pyproject.toml": member_pyproject() + 'r1_modules = ["src/a/mod.py"]\nmutation_min = 80\n',
            "pkgs/a/src/a/__init__.py": "",
            "pkgs/a/src/a/mod.py": "def sign(value):\n    return 0\n",
            "pkgs/a/tests/test_mod.py": tests,
        }
    )
    repo.commit({"pkgs/a/src/a/mod.py": MODULE})
    return base


def _codes(out: str) -> list[str]:
    return [f["code"] for step in json.loads(out)["steps"] for f in step["findings"]]


def test_strong_tests_kill_the_mutants(repo: Repo) -> None:
    base = _toy(repo, FULL_TESTS)
    result = repo.run(["--format", "json", "mutation", "--package", "a", "--base", base])
    assert result.code == 0, result.out + result.err
    assert _codes(result.out) == []


def test_weak_tests_fail_with_mu001(repo: Repo) -> None:
    base = _toy(repo, PARTIAL_TESTS)
    result = repo.run(["--format", "json", "mutation", "--package", "a", "--base", base])
    assert result.code == 1, result.out + result.err
    assert _codes(result.out) == ["MU001"]
