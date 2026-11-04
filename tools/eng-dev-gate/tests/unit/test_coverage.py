"""Tests of the ``tests`` step (spec 4.12, AC50) with a scripted tool runner."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from eng_dev_gate.checks.registry import STEP_ORDER, STEPS, StepContext
from eng_dev_gate.checks.tests_step import DESELECTED_EXIT_CODE, tests
from eng_dev_gate.report import Finding
from eng_dev_gate.results import EnvironmentFaultError
from eng_dev_gate.toolrun import ToolResult
from eng_dev_gate.workspace import discover_members
from support.coverage_toy import make_toy
from support.repo import Repo


def _totals(statements: int, covered: int, branches: int, covered_branches: int) -> dict[str, dict[str, int]]:
    return {
        "totals": {
            "num_statements": statements,
            "covered_lines": covered,
            "num_branches": branches,
            "covered_branches": covered_branches,
        }
    }


class FakeCoverage:
    """Scripted runner: ``pytest_exit`` is the exit code of ``coverage run``; ``report`` is written by ``json``."""

    def __init__(self, report: object = None, pytest_exit: int = 0, json_exit: int = 0) -> None:
        self.report = report
        self.pytest_exit = pytest_exit
        self.json_exit = json_exit
        self.calls: list[tuple[list[str], Path]] = []

    def run(self, argv: Sequence[str], cwd: Path) -> ToolResult:
        self.calls.append((list(argv), cwd))
        if "json" in argv:
            if self.json_exit == 0:
                Path(argv[argv.index("-o") + 1]).write_text(json.dumps(self.report), encoding="utf-8")
            return ToolResult(exit_code=self.json_exit, output="json output")
        return ToolResult(exit_code=self.pytest_exit, output="pytest output")


def _step(repo: Repo, runner: FakeCoverage, line: int = 95, branch: int = 90) -> list[Finding]:
    make_toy(repo, line=line, branch=branch)
    (member,) = discover_members(repo.root)
    return tests(StepContext(repo.root, repo.root, member, runner))


def _codes(findings: list[Finding]) -> list[str]:
    return [f.code for f in findings]


def test_line_and_branch_separate(repo: Repo) -> None:
    """AC50: each percentage is compared with its own threshold; a good combined figure cannot hide a bad one."""
    assert _codes(_step(repo, FakeCoverage(_totals(100, 100, 100, 100)))) == []
    # 100 % lines, 50 % branches: combined would be 75 %, still only CV002 fires
    assert _codes(_step(repo, FakeCoverage(_totals(100, 100, 100, 50)))) == ["CV002"]
    assert _codes(_step(repo, FakeCoverage(_totals(100, 90, 100, 100)))) == ["CV001"]
    assert _codes(_step(repo, FakeCoverage(_totals(100, 90, 100, 50)))) == ["CV001", "CV002"]


def test_thresholds_are_inclusive_and_exact(repo: Repo) -> None:
    assert _codes(_step(repo, FakeCoverage(_totals(100, 95, 10, 9)))) == []
    assert _codes(_step(repo, FakeCoverage(_totals(1000, 949, 10, 9)))) == ["CV001"]
    assert _codes(_step(repo, FakeCoverage(_totals(100, 95, 1000, 899)))) == ["CV002"]


def test_nothing_to_measure_passes(repo: Repo) -> None:
    """No statements or no branches means nothing is uncovered (no division by zero)."""
    assert _codes(_step(repo, FakeCoverage(_totals(0, 0, 0, 0)))) == []


def test_command_lines(repo: Repo) -> None:
    runner = FakeCoverage(_totals(1, 1, 0, 0))
    _step(repo, runner)
    run_argv, json_argv = (c[0] for c in runner.calls)
    assert run_argv[1:3] == ["-m", "coverage"] and "--branch" in run_argv
    assert run_argv[run_argv.index("-m", 3) + 1] == "pytest"
    assert "eng_dev_gate.pytest_plugin" in run_argv and "-c" in run_argv
    assert "--rcfile" in run_argv and "--rcfile" in json_argv


def test_pytest_exit_codes(repo: Repo) -> None:
    ok = _totals(1, 1, 0, 0)
    assert _codes(_step(repo, FakeCoverage(ok, pytest_exit=1))) == ["ST001"]
    assert _codes(_step(repo, FakeCoverage(ok, pytest_exit=5))) == ["ST001"]
    assert _codes(_step(repo, FakeCoverage(ok, pytest_exit=DESELECTED_EXIT_CODE))) == ["CV003"]
    with pytest.raises(EnvironmentFaultError):
        _step(repo, FakeCoverage(ok, pytest_exit=3))


def test_report_faults(repo: Repo) -> None:
    with pytest.raises(EnvironmentFaultError):
        _step(repo, FakeCoverage(None, json_exit=1))
    with pytest.raises(EnvironmentFaultError):
        _step(repo, FakeCoverage({"totals": {}}))
    with pytest.raises(EnvironmentFaultError):
        _step(repo, FakeCoverage([1, 2]))


def test_registered_in_spec_order() -> None:
    names = [s.name for s in STEPS]
    assert names[-1] == "tests"
    assert [n for n in STEP_ORDER if n in names] == names
