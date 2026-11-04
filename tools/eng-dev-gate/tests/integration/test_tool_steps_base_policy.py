"""Regression tests of B-058: the format, lint and types steps judge the head tree with the base policy (spec 4.16).

In CI the gate runs from a checkout of the base commit (``--gate-root``) against the pull request checkout
(``--root``). The policy comes from the base ``pyproject.toml``; every relative pattern in it must apply to the judged
tree. Two temporary directories stand for the two checkouts.
"""

from __future__ import annotations

import json
from pathlib import Path

from eng_dev_gate.checks.check import make_handler
from eng_dev_gate.toolrun import SubprocessToolRunner
from support.judged_tree import lock
from support.repo import Repo, RunResult, make_repo
from support.toy import GATE_YML, member_pyproject

BASE_ROOT = (
    '[project]\nname = "toy-root"\nversion = "0"\nrequires-python = ">=3.14"\ndependencies = []\n'
    '[tool.uv]\npackage = false\n[tool.uv.workspace]\nmembers = ["pkgs/a"]\n[dependency-groups]\ndev = []\n'
    '[tool.ruff]\ntarget-version = "py314"\nline-length = 120\nextend-exclude = ["pkgs/a/src/a/excluded.py"]\n'
    '[tool.ruff.lint]\nselect = ["E", "F", "I", "S"]\n'
    '[tool.ruff.lint.per-file-ignores]\n"**/tests/**" = ["S101"]\n'
    '[tool.mypy]\nstrict = true\npython_version = "3.14"\nmypy_path = "pkgs/a/extra"\n'
    'exclude = ["^pkgs/a/src/a/excluded\\\\.py$"]\n'
)
# The head root configuration is weaker on purpose: it must never be used in place of the base policy.
HEAD_ROOT = BASE_ROOT.replace('select = ["E", "F", "I", "S"]', 'select = ["E"]').replace(
    '"**/tests/**" = ["S101"]', '"**/tests/**" = ["S101", "F401"]'
)
CLEAN = '"""A module."""\n\n\ndef double(value: int) -> int:\n    """Return twice ``value``."""\n    return value * 2\n'
TEST_WITH_ASSERT = (
    '"""A test."""\n\nfrom a.mod import double\n\n\ndef test_double() -> None:\n    assert double(2) == 4\n'
)
BAD_EXCLUDED = "import os\n\n\ndef f(a: int)->str:\n    return a\n"


def _tree(root: Path, root_pyproject: str, files: dict[str, str]) -> Repo:
    tree = make_repo(root)
    tree.commit(
        {
            "pyproject.toml": root_pyproject,
            ".gate/gate.yml": GATE_YML,
            "pkgs/a/pyproject.toml": member_pyproject("a"),
            "pkgs/a/src/a/__init__.py": "",
            "pkgs/a/src/a/mod.py": CLEAN,
            **files,
        }
    )
    lock(root)  # ``types`` builds the judged environment from the lock file (AC54a)
    tree.commit({}, "chore: lock")
    return tree


def _judge(gate: Repo, head: Repo, *steps: str) -> RunResult:
    """Run the steps the way CI does: policy from ``gate``, tree under judgement ``head``."""
    argv = ["--gate-root", str(gate.root), "--format", "json", "check", "--only", ",".join(steps)]
    return head.run(argv, {"check": make_handler(SubprocessToolRunner())})


def _statuses(result: RunResult) -> dict[str, str]:
    return {s["name"]: s["status"] for s in json.loads(result.out)["steps"]}


def test_base_policy_ignores_apply_to_the_judged_tree(tmp_path: Path) -> None:
    """``per-file-ignores`` ``**/tests/**`` of the base policy covers the tests of the judged tree."""
    gate = _tree(tmp_path / "base", BASE_ROOT, {})
    head = _tree(tmp_path / "head", HEAD_ROOT, {"pkgs/a/tests/test_mod.py": TEST_WITH_ASSERT})
    result = _judge(gate, head, "format", "lint")
    assert result.code == 0, result.out
    assert _statuses(result) == {"format": "pass", "lint": "pass"}


def test_base_policy_exclude_applies_to_the_judged_tree(tmp_path: Path) -> None:
    """A relative ``extend-exclude`` of the base policy names a file of the judged tree."""
    gate = _tree(tmp_path / "base", BASE_ROOT, {})
    head = _tree(tmp_path / "head", HEAD_ROOT, {"pkgs/a/src/a/excluded.py": BAD_EXCLUDED})
    result = _judge(gate, head, "format", "lint")
    assert result.code == 0, result.out


def test_base_policy_still_fails_what_it_forbids(tmp_path: Path) -> None:
    """The fix does not disable checks: ``S101`` outside tests fails, although the head policy does not select S."""
    gate = _tree(tmp_path / "base", BASE_ROOT, {})
    head = _tree(tmp_path / "head", HEAD_ROOT, {"pkgs/a/src/a/guard.py": '"""G."""\n\nassert __name__\n'})
    result = _judge(gate, head, "lint")
    assert result.code == 1
    assert _statuses(result) == {"lint": "fail"}
    (finding,) = json.loads(result.out)["steps"][0]["findings"]
    assert finding["code"] == "ST001"
    assert "S101" in finding["message"]
    assert "guard.py" in finding["message"]


def test_base_policy_still_fails_a_badly_formatted_file(tmp_path: Path) -> None:
    gate = _tree(tmp_path / "base", BASE_ROOT, {})
    head = _tree(tmp_path / "head", HEAD_ROOT, {"pkgs/a/src/a/ugly.py": "x = {  'a':1 }\n"})
    result = _judge(gate, head, "format")
    assert result.code == 1
    assert _statuses(result) == {"format": "fail"}


def test_base_mypy_paths_apply_to_the_judged_tree(tmp_path: Path) -> None:
    """``mypy_path`` and ``exclude`` of the base policy are relative to the judged tree."""
    gate = _tree(tmp_path / "base", BASE_ROOT, {})
    head = _tree(
        tmp_path / "head",
        HEAD_ROOT,
        {
            "pkgs/a/extra/helper.py": '"""Helper."""\n\n\ndef helper() -> int:\n    """Return one."""\n    return 1\n',
            "pkgs/a/src/a/uses.py": '"""Uses."""\n\nfrom helper import helper\n\nVALUE: int = helper()\n',
            "pkgs/a/src/a/excluded.py": BAD_EXCLUDED,
        },
    )
    result = _judge(gate, head, "types")
    assert result.code == 0, result.out


def test_the_steps_leave_no_tool_cache_in_the_judged_tree(tmp_path: Path) -> None:
    """Tool caches (ruff, mypy) never live in the tree under judgement, where a pull request could forge them."""
    gate = _tree(tmp_path / "base", BASE_ROOT, {})
    head = _tree(tmp_path / "head", HEAD_ROOT, {"pkgs/a/tests/test_mod.py": TEST_WITH_ASSERT})
    result = _judge(gate, head, "format", "lint", "types")
    assert result.code == 0, result.out
    assert not list(head.root.rglob(".mypy_cache"))
    assert not list(head.root.rglob(".ruff_cache"))


def test_a_planted_mypy_cache_cannot_hide_a_type_error(tmp_path: Path) -> None:
    """A cache directory in the pull request is ignored: the type error is still reported."""
    gate = _tree(tmp_path / "base", BASE_ROOT, {})
    head = _tree(tmp_path / "head", HEAD_ROOT, {"pkgs/a/src/a/wrong.py": "def f(a: int) -> str:\n    return a\n"})
    (head.root / ".mypy_cache" / "3.14").mkdir(parents=True)
    (head.root / ".mypy_cache" / "3.14" / "planted").write_text("not a cache", encoding="utf-8")
    result = _judge(gate, head, "types")
    assert result.code == 1
    assert _statuses(result) == {"types": "fail"}


def test_base_mypy_still_fails_a_type_error(tmp_path: Path) -> None:
    gate = _tree(tmp_path / "base", BASE_ROOT, {})
    head = _tree(tmp_path / "head", HEAD_ROOT, {"pkgs/a/src/a/wrong.py": "def f(a: int) -> str:\n    return a\n"})
    result = _judge(gate, head, "types")
    assert result.code == 1
    assert _statuses(result) == {"types": "fail"}
