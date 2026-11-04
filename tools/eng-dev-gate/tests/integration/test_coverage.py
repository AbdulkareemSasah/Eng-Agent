"""Integration tests of the ``tests`` step with the real coverage and pytest on a toy member (AC50)."""

from __future__ import annotations

import json

from eng_dev_gate.checks.check import make_handler
from eng_dev_gate.toolrun import SubprocessToolRunner
from support.coverage_toy import FULL_TESTS, PARTIAL_TESTS, make_toy
from support.repo import Repo, RunResult


def _run(repo: Repo) -> tuple[RunResult, list[str], str]:
    result = repo.run(["--format", "json", "check", "--only", "tests"], {"check": make_handler(SubprocessToolRunner())})
    (step,) = json.loads(result.out)["steps"]
    return result, [f["code"] for f in step["findings"]], step["status"]


def test_full_coverage_passes_and_leaves_no_files(repo: Repo) -> None:
    make_toy(repo)
    result, codes, status = _run(repo)
    assert (result.code, codes, status) == (0, [], "pass")
    left = [line for line in repo.git("status", "--porcelain").splitlines() if "__pycache__" not in line]
    assert left == []  # no .coverage data, rc file or report in the tree


def test_partial_coverage_reports_both_codes(repo: Repo) -> None:
    make_toy(repo, PARTIAL_TESTS)
    result, codes, _ = _run(repo)
    assert result.code == 1
    assert codes == ["CV001", "CV002"]


def test_lower_threshold_accepts_partial_coverage(repo: Repo) -> None:
    make_toy(repo, PARTIAL_TESTS, line=50, branch=50)
    assert _run(repo)[1] == []


def test_deselection_fails(repo: Repo) -> None:
    """AC50: a conftest that drops a test fails the run with CV003 even though the rest pass."""
    two = FULL_TESTS + "\n\ndef test_other() -> None:\n    assert True\n"
    conftest = "def pytest_collection_modifyitems(items):\n    del items[1:]\n"
    make_toy(repo, two, {"tests/conftest.py": conftest})
    result, codes, status = _run(repo)
    assert (result.code, codes, status) == (1, ["CV003"], "fail")


def test_failing_test_is_st001(repo: Repo) -> None:
    make_toy(repo, "def test_bad() -> None:\n    assert False\n")
    assert _run(repo)[1] == ["ST001"]
