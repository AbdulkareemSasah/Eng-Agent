"""The ``windows-tests`` command (spec 4.14, AC63): run the paths each member declares in ``windows_tests``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path, PurePosixPath

from eng_dev_gate.checks.check import Handler, _workspace_root
from eng_dev_gate.config import load_gate_config
from eng_dev_gate.config.package_config import load_package_config
from eng_dev_gate.report import CommandResult, Finding, Severity, StepResult, render
from eng_dev_gate.results import EnvironmentFaultError, Status
from eng_dev_gate.toolrun import SubprocessToolRunner, ToolRunner
from eng_dev_gate.workspace import discover_members

STEP = "windows-tests"
TEST_FAILURE_EXITS = (1, 5)  # pytest: 1 tests failed, 5 nothing collected from the declared paths
OUTPUT_LINES = 20  # last lines of pytest output quoted in ST001; presentation only


def _problem(directory: Path, declared: str) -> str | None:
    """Why ``declared`` cannot be run (absolute, leaves the package, or missing), else ``None``."""
    path = PurePosixPath(declared)
    if path.is_absolute() or ".." in path.parts:
        return f"windows_tests path {declared!r} must be relative and stay inside the package"
    if not (directory / declared).exists():
        return f"windows_tests path {declared!r} does not exist"
    return None


def run_windows_tests(root: Path, runner: ToolRunner) -> list[StepResult]:
    """Run the declared paths of every workspace member with pytest, in the member folder, in the head environment.

    Members that declare nothing do not run. A failing member does not hide the next one. When no member declares
    paths the step is skipped with a notice (exit 0).

    Raises:
        ConfigError: a member has no valid ``[tool.eng-gate]`` table (CF001, CF006; exit 2).
        EnvironmentFaultError: pytest exited with a code other than pass, test failure or nothing collected (exit 3).
    """
    findings: list[Finding] = []
    ran = False
    for member in discover_members(root):
        declared = load_package_config(member.directory / "pyproject.toml").windows_tests
        if not declared:
            continue
        ran = True
        problems = [p for p in (_problem(member.directory, d) for d in declared) if p]
        if problems:
            findings += [Finding(code="ST001", severity=Severity.ERROR, path=member.path, message=p) for p in problems]
            continue
        argv = ["uv", "run", "--quiet", "--project", str(root), "--locked", "--all-packages", "--group", "dev",
                "python", "-m", "pytest", *declared]  # fmt: skip
        outcome = runner.run(argv, member.directory)
        if outcome.exit_code == 0:
            continue
        head = " | ".join(outcome.output.splitlines()[-OUTPUT_LINES:])
        if outcome.exit_code not in TEST_FAILURE_EXITS:
            raise EnvironmentFaultError(f"windows-tests: pytest exited {outcome.exit_code} in {member.path}: {head}")
        message = f"windows-tests: pytest exited {outcome.exit_code}: {head}"
        findings.append(Finding(code="ST001", severity=Severity.ERROR, path=member.path, message=message))
    reason = None if ran else "no workspace member declares windows_tests; nothing to run"
    return [StepResult(name=STEP, findings=findings, skipped_reason=reason)]


def make_handler(runner: ToolRunner | None = None) -> Handler:
    """Return the ``windows-tests`` handler; ``runner`` defaults to the subprocess adapter."""
    tools = runner or SubprocessToolRunner()

    def handler(args: argparse.Namespace) -> Status:
        root = _workspace_root(Path(args.root).resolve())
        mode = load_gate_config(root).mode
        result = CommandResult(command=STEP, mode=mode.value, steps=run_windows_tests(root, tools))
        render(result, args.format, sys.stdout, os.environ)
        return result.status

    return handler
