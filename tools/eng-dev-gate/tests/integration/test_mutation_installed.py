"""Integration test of the ``mutation`` step on an installed workspace member in a judged tree (B-049 review).

The member ``a`` is installed in the environment that uv builds from the judged tree, as every real member is. The
mutants must shadow that installation: weak tests give MU001, strong tests pass. The gate itself runs from another
interpreter that has neither ``a`` nor mutmut, as in a pull-request run (spec 4.16).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from support.coverage_toy import FULL_TESTS, MODULE, PARTIAL_TESTS
from support.judged_tree import ROOT_PYPROJECT, lock, make_gate_root, member_pyproject
from support.repo import Repo, make_repo
from support.toy import GATE_YML


def _tree(root: Path, tests: str) -> tuple[Repo, str]:
    """A judged tree with an installable member, its lock file, a trivial base module and a changed head."""
    tree = make_repo(root)
    table = member_pyproject() + 'r1_modules = ["src/a/mod.py"]\nmutation_min = 80\n'
    base = tree.commit(
        {
            "pyproject.toml": ROOT_PYPROJECT.replace('"coverage>=7.14.0"', '"coverage>=7.14.0", "mutmut>=3.8.1"'),
            ".gate/gate.yml": GATE_YML,
            "pkgs/a/pyproject.toml": table,
            "pkgs/a/src/a/__init__.py": "",
            "pkgs/a/src/a/mod.py": "def sign(value):\n    return 0\n",
            "pkgs/a/tests/test_mod.py": tests,
        }
    )
    lock(root)
    tree.commit({}, "chore: lock")
    tree.commit({"pkgs/a/src/a/mod.py": MODULE})
    return tree, base


def _judge(tmp_path: Path, tests: str) -> tuple[int, list[str], str]:
    gate = make_gate_root(tmp_path / "base")
    head, base = _tree(tmp_path / "head", tests)
    result = head.run(["--gate-root", str(gate.root), "--format", "json", "mutation", "--package", "a", "--base", base])
    codes = [f["code"] for step in json.loads(result.out)["steps"] for f in step["findings"]] if result.out else []
    return result.code, codes, result.out + result.err


def _verdict(outcome: tuple[int, list[str], str], code: int, codes: list[str]) -> None:
    """Assert the outcome; on Windows mutmut cannot run (ADR-0002) and the step says so with MU002 instead."""
    got_code, got_codes, text = outcome
    if sys.platform == "win32":
        assert "MU002" in text, text
    else:
        assert (got_code, got_codes) == (code, codes), text


def test_strong_tests_kill_mutants_of_an_installed_member(tmp_path: Path) -> None:
    _verdict(_judge(tmp_path, FULL_TESTS), 0, [])


def test_weak_tests_of_an_installed_member_give_mu001(tmp_path: Path) -> None:
    _verdict(_judge(tmp_path, PARTIAL_TESTS), 1, ["MU001"])
