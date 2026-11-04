"""Regression tests of B-059: the ``tests`` step runs the judged tree's tests in the judged tree's environment.

In CI the gate runs from the environment of the base checkout (``--gate-root``), which does not contain the judged
packages. Two temporary directories stand for the two checkouts and the interpreter of this test session stands for
the base environment: it has neither ``a`` nor anything the judged lock file installs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eng_dev_gate.checks.check import make_handler
from eng_dev_gate.toolrun import SubprocessToolRunner
from support.coverage_toy import FULL_TESTS, PARTIAL_TESTS
from support.judged_tree import make_gate_root, make_judged_tree
from support.repo import Repo, RunResult

FAILING_TEST = "from a.mod import sign\n\n\ndef test_bad() -> None:\n    assert sign(1) == 2\n"
OMIT_ALL = "[run]\nomit = */src/*\n"


def _judge(gate: Repo, head: Repo) -> tuple[RunResult, list[str], str]:
    argv = ["--gate-root", str(gate.root), "--format", "json", "check", "--only", "tests"]
    result = head.run(argv, {"check": make_handler(SubprocessToolRunner())})
    assert result.out, f"no report (exit {result.code}): {result.err[:600]}"
    (step,) = json.loads(result.out)["steps"]
    return result, [f["code"] for f in step["findings"]], step["status"]


def test_judged_package_is_importable_in_the_tests(tmp_path: Path) -> None:
    """A member whose tests import its own package passes when the gate's environment lacks that package."""
    gate, head = make_gate_root(tmp_path / "base"), make_judged_tree(tmp_path / "head")
    result, codes, status = _judge(gate, head)
    assert (result.code, codes, status) == (0, [], "pass"), result.out + result.err


def test_judged_tests_that_fail_are_st001(tmp_path: Path) -> None:
    gate, head = make_gate_root(tmp_path / "base"), make_judged_tree(tmp_path / "head", FAILING_TEST)
    result, codes, _ = _judge(gate, head)
    assert (result.code, codes) == (1, ["ST001"]), result.out + result.err


def test_judged_tree_cannot_replace_the_base_plugin(tmp_path: Path) -> None:
    """The member installs an ``eng_dev_gate.pytest_plugin`` that does nothing; a dropped test is still CV003."""
    two = FULL_TESTS + "\n\ndef test_other() -> None:\n    assert True\n"
    files = {
        "tests/conftest.py": "def pytest_collection_modifyitems(items):\n    del items[1:]\n",
        "src/eng_dev_gate/__init__.py": "",
        "src/eng_dev_gate/pytest_plugin.py": '"""A plugin that never reports a deselection."""\n',
    }
    gate, head = make_gate_root(tmp_path / "base"), make_judged_tree(tmp_path / "head", two, files)
    result, codes, status = _judge(gate, head)
    assert (result.code, codes, status) == (1, ["CV003"], "fail"), result.out + result.err


@pytest.mark.parametrize(
    "extra_files",
    [
        {".coveragerc": OMIT_ALL},
        {"setup.cfg": "[coverage:run]\nomit = */src/*\n"},
        {"tox.ini": "[coverage:run]\nomit = */src/*\n"},
    ],
)
def test_judged_coverage_files_cannot_lower_the_thresholds(tmp_path: Path, extra_files: dict[str, str]) -> None:
    """Coverage files of the judged tree do not hide uncovered lines: the gate's generated rc file is the policy."""
    gate = make_gate_root(tmp_path / "base")
    head = make_judged_tree(tmp_path / "head", PARTIAL_TESTS, extra_files)
    result, codes, _ = _judge(gate, head)
    assert (result.code, codes) == (1, ["CV001", "CV002"]), result.out + result.err


def test_judged_pyproject_and_environment_cannot_lower_the_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``[tool.coverage]`` table of the member and ``COVERAGE_RCFILE`` do not take over from the generated rc file."""
    lenient = tmp_path / "lenient.ini"
    lenient.write_text(OMIT_ALL + "[report]\nfail_under = 0\n", encoding="utf-8")
    monkeypatch.setenv("COVERAGE_RCFILE", str(lenient))
    gate = make_gate_root(tmp_path / "base")
    head = make_judged_tree(tmp_path / "head", PARTIAL_TESTS)
    member = head.root / "pkgs" / "a" / "pyproject.toml"
    member.write_text(member.read_text() + '[tool.coverage.run]\nomit = ["*/src/*"]\n', encoding="utf-8")
    result, codes, _ = _judge(gate, head)
    assert (result.code, codes) == (1, ["CV001", "CV002"]), result.out + result.err


def test_judged_run_leaves_the_judged_tree_without_coverage_files(tmp_path: Path) -> None:
    gate, head = make_gate_root(tmp_path / "base"), make_judged_tree(tmp_path / "head")
    _judge(gate, head)
    status = head.git("status", "--porcelain", "--untracked-files=all").splitlines()
    left = [line for line in status if "__pycache__" not in line and ".venv" not in line]
    assert left == []
