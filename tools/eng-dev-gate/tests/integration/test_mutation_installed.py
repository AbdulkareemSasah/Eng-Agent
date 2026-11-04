"""Integration test of the ``mutation`` step on an installed workspace member in a judged tree (B-049 review).

The member ``a`` is installed in the environment that uv builds from the judged tree, as every real member is. The
mutants must shadow that installation: weak tests give MU001, strong tests pass. The gate itself runs from another
interpreter that has neither ``a`` nor mutmut, as in a pull-request run (spec 4.16).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from support.coverage_toy import FULL_TESTS, MODULE, PARTIAL_TESTS
from support.judged_tree import ROOT_PYPROJECT, make_gate_root, member_pyproject
from support.repo import Repo, make_repo
from support.toy import GATE_YML

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="B-049: mutmut has no native Windows support; expires 2027-06-30"
)


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
    subprocess.run(["uv", "lock"], cwd=root, check=True, capture_output=True)  # noqa: S607  # B-049: uv from PATH
    tree.commit({}, "chore: lock")
    tree.commit({"pkgs/a/src/a/mod.py": MODULE})
    return tree, base


def _judge(tmp_path: Path, tests: str) -> tuple[int, list[str], str]:
    gate = make_gate_root(tmp_path / "base")
    head, base = _tree(tmp_path / "head", tests)
    result = head.run(["--gate-root", str(gate.root), "--format", "json", "mutation", "--package", "a", "--base", base])
    codes = [f["code"] for step in json.loads(result.out)["steps"] for f in step["findings"]] if result.out else []
    return result.code, codes, result.out + result.err


def test_strong_tests_kill_mutants_of_an_installed_member(tmp_path: Path) -> None:
    code, codes, text = _judge(tmp_path, FULL_TESTS)
    assert (code, codes) == (0, []), text


def test_weak_tests_of_an_installed_member_give_mu001(tmp_path: Path) -> None:
    code, codes, text = _judge(tmp_path, PARTIAL_TESTS)
    assert (code, codes) == (1, ["MU001"]), text
