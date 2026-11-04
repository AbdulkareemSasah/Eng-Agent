"""The ``tests`` step (spec 4.12, AC50): coverage run, JSON report, line and branch compared separately."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from eng_dev_gate.config.package_config import load_package_config
from eng_dev_gate.pytest_plugin import DESELECTED_EXIT_CODE
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import EnvironmentFaultError
from eng_dev_gate.toolrun import ToolRunner, python_module

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

__all__ = ["DESELECTED_EXIT_CODE", "tests"]

OUTPUT_LINES = 20  # first lines of pytest output quoted in ST001; presentation only
TEST_FAILURE_EXITS = (1, 5)  # pytest: 1 tests failed, 5 no tests collected; other codes are tool faults


def _totals(report: Path) -> dict[str, int]:
    """Read the four counts of coverage.py's JSON ``totals``; the report is tool output, so validate it."""
    try:
        totals = json.loads(report.read_text(encoding="utf-8"))["totals"]
        return {k: int(totals[k]) for k in ("num_statements", "covered_lines", "num_branches", "covered_branches")}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise EnvironmentFaultError(f"tests: unusable coverage report {report}: {error!r}") from error


def _below(covered: int, total: int, minimum: int) -> bool:
    """True when ``covered / total`` is under ``minimum`` percent; integer arithmetic, nothing to cover passes."""
    return covered * 100 < minimum * total


def _run_coverage(runner: ToolRunner, member_dir: Path, work: Path) -> tuple[int, str, Path]:
    rcfile = work / "coveragerc"
    rcfile.write_text(
        f"[run]\nsource_dirs = {(member_dir / 'src').as_posix()}\ndata_file = {(work / 'data').as_posix()}\n",
        encoding="utf-8",
    )
    rc = ["--rcfile", str(rcfile)]
    run = python_module(
        "coverage",
        "run",
        "--branch",
        *rc,
        "-m",
        "pytest",
        "-c",
        "pyproject.toml",
        "-p",
        "eng_dev_gate.pytest_plugin",
        "tests",
    )
    outcome = runner.run(run, member_dir)
    report = work / "coverage.json"
    if outcome.exit_code not in (0, *TEST_FAILURE_EXITS, DESELECTED_EXIT_CODE):
        raise EnvironmentFaultError(f"tests: pytest exited {outcome.exit_code}: {outcome.output[:500]}")
    if outcome.exit_code == 0:  # coverage of a failed or incomplete run is not judged
        made = runner.run(python_module("coverage", "json", *rc, "-o", str(report)), member_dir)
        if made.exit_code != 0:
            raise EnvironmentFaultError(f"tests: coverage json exited {made.exit_code}: {made.output[:500]}")
    return outcome.exit_code, outcome.output, report


def tests(ctx: StepContext) -> list[Finding]:
    """Run the package tests under coverage; CV001 line and CV002 branch below threshold, CV003 deselection.

    Percentages are covered over total, each against its own threshold from ``[tool.eng-gate]``. A failing test
    run is ST001 and its coverage is not judged.

    Raises:
        ConfigError: the package table is invalid (exit 2).
        EnvironmentFaultError: pytest or coverage crashed, or the report is unusable (exit 3).
    """
    assert ctx.member is not None  # noqa: S101 - package steps always have a member
    member = ctx.member
    config = load_package_config(member.directory / "pyproject.toml")
    with tempfile.TemporaryDirectory(prefix="eng-gate-cov-") as folder:
        exit_code, output, report = _run_coverage(ctx.runner, member.directory, Path(folder))
        if exit_code == DESELECTED_EXIT_CODE:
            message = "tests: a test was deselected; every test must run"
            return [Finding(code="CV003", severity=Severity.ERROR, path=member.path, message=message)]
        if exit_code != 0:
            head = " | ".join(output.splitlines()[-OUTPUT_LINES:])
            message = f"tests: pytest exited {exit_code}: {head}"
            return [Finding(code="ST001", severity=Severity.ERROR, path=member.path, message=message)]
        totals = _totals(report)
    findings: list[Finding] = []
    for code, kind, covered, total, minimum in (
        ("CV001", "line", totals["covered_lines"], totals["num_statements"], config.coverage_line),
        ("CV002", "branch", totals["covered_branches"], totals["num_branches"], config.coverage_branch),
    ):
        if _below(covered, total, minimum):
            message = f"{kind} coverage {covered}/{total} is below {minimum} %"
            findings.append(Finding(code=code, severity=Severity.ERROR, path=member.path, message=message))
    return findings
