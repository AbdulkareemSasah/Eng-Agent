"""The ``tests`` step (spec 4.12, AC50): coverage run, JSON report, line and branch compared separately."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from eng_dev_gate import judged_run
from eng_dev_gate.config.package_config import load_package_config
from eng_dev_gate.pytest_plugin import DESELECTED_EXIT_CODE
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import EnvironmentFaultError
from eng_dev_gate.toolrun import python_module

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

__all__ = ["DESELECTED_EXIT_CODE", "tests"]

OUTPUT_LINES = 20  # last lines of pytest output quoted in ST001; presentation only
TEST_FAILURE_EXITS = (1, 5)  # pytest: 1 tests failed, 5 no tests collected; other codes are tool faults


def _totals(report: Path) -> dict[str, int]:
    """Read the four counts of coverage.py's JSON ``totals``; the report is tool output, so validate it."""
    try:
        totals = json.loads(report.read_text(encoding="utf-8"))["totals"]
        return {k: int(totals[k]) for k in ("num_statements", "covered_lines", "num_branches", "covered_branches")}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise EnvironmentFaultError(f"tests: unusable coverage report {report}: {error!r}") from error


def _pytest_cov_installed() -> bool:
    """True when pytest-cov, a dev dependency only, can be imported; ``--no-cov`` is unknown to pytest without it."""
    return importlib.util.find_spec("pytest_cov") is not None


def _below(covered: int, total: int, minimum: int) -> bool:
    """True when ``covered / total`` is under ``minimum`` percent; integer arithmetic, nothing to cover passes."""
    return covered * 100 < minimum * total


def _uv_available() -> bool:
    """True when ``uv`` can be found on ``PATH``; the tests of a judged tree run in an environment uv builds."""
    return shutil.which("uv") is not None


def _judged_command(root: Path, *argv: str) -> list[str]:
    """The argv that runs ``python argv`` in the environment of the judged tree at ``root``, from its lock file.

    ``--locked`` makes uv refuse a stale ``uv.lock`` (``_stale_lock`` judges that before, so uv's exit 2 never reaches
    the pytest exit codes); ``--all-packages`` and the ``dev`` group give the members and their test tools, as the setup
    action does for a push run. ``--quiet`` keeps uv's own warnings (an inherited ``VIRTUAL_ENV`` that is not the
    project's, a deprecated variable) out of the output, where they would fill the excerpt of a fault message.
    """
    return [
        "uv",
        "run",
        "--quiet",
        "--project",
        str(root),
        "--locked",
        "--all-packages",
        "--group",
        "dev",
        "python",
        *argv,
    ]


def _stale_lock(ctx: StepContext) -> Finding | None:
    """ST001 when the judged tree's ``uv.lock`` is stale or missing, else ``None``; its tests need that environment.

    The ``lock`` step reports the same fact for the workspace; this check keeps the tests step from turning it into an
    environment fault (``uv run --locked`` exits 2) that would hide every other finding of the run.
    """
    assert ctx.member is not None  # noqa: S101
    checked = ctx.runner.run(["uv", "lock", "--check", "--project", str(ctx.root)], ctx.root)
    if checked.exit_code == 0:
        return None
    head = " | ".join(checked.output.splitlines()[-OUTPUT_LINES:])
    message = f"tests: uv.lock of the judged tree is not up to date, so its environment cannot be built: {head}"
    return Finding(code="ST001", severity=Severity.ERROR, path=ctx.member.path, message=message)


def _coverage_arguments(rcfile: Path, plugin: str, no_cov: str | None) -> list[str]:
    """Arguments of ``coverage run`` for the pytest session; ``no_cov`` is the pytest-cov switch or its marker."""
    return [
        "run",
        "--branch",
        "--rcfile",
        str(rcfile),
        "-m",
        "pytest",
        "-c",
        "pyproject.toml",
        "-p",
        plugin,
        # a member's own pytest-cov addopts would otherwise take over measurement from this run
        *([no_cov] if no_cov else []),
        "tests",
    ]


def _judged_environment(ctx: StepContext) -> bool:
    """True in a pull-request run: the gate root is not the tree under check, so the tree needs its own environment."""
    return ctx.gate_root.resolve() != ctx.root.resolve()


def _run_coverage(ctx: StepContext, member_dir: Path, work: Path) -> tuple[int, str, Path]:
    rcfile = work / "coveragerc"
    rcfile.write_text(
        f"[run]\nsource_dirs = {(member_dir / 'src').as_posix()}\ndata_file = {(work / 'data').as_posix()}\n",
        encoding="utf-8",
    )
    rc = ["--rcfile", str(rcfile)]
    report = work / "coverage.json"
    if not _judged_environment(ctx):  # head run: the interpreter of the gate is the environment
        no_cov = "--no-cov" if _pytest_cov_installed() else None
        run = python_module("coverage", *_coverage_arguments(rcfile, "eng_dev_gate.pytest_plugin", no_cov))
        make = python_module("coverage", "json", *rc, "-o", str(report))
        make_cwd = member_dir
    else:  # pull-request run: the gate is the base commit's, the code under test needs the judged tree's environment
        # the script is the base commit's file and loads the base plugin under its own name; the rc file is generated
        # here, so neither the policy nor the plugin comes from the judged tree
        marker = judged_run.NO_COV_MARKER
        run = _judged_command(
            ctx.root,
            str(Path(judged_run.__file__).resolve()),
            *_coverage_arguments(rcfile, judged_run.BASE_PLUGIN, marker),
        )
        make = _judged_command(ctx.root, "-m", "coverage", "json", *rc, "-o", str(report))
        make_cwd = work  # nothing of the judged tree is on the import path of the report tool
    outcome = ctx.runner.run(run, member_dir)
    if outcome.exit_code not in (0, *TEST_FAILURE_EXITS, DESELECTED_EXIT_CODE):
        raise EnvironmentFaultError(f"tests: pytest exited {outcome.exit_code}: {outcome.output[:500]}")
    if outcome.exit_code == 0:  # coverage of a failed or incomplete run is not judged
        made = ctx.runner.run(make, make_cwd)
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
    if _judged_environment(ctx):
        if not _uv_available():
            raise EnvironmentFaultError("tests: uv is not available; the judged tree's tests need its uv environment")
        if (stale := _stale_lock(ctx)) is not None:
            return [stale]
    with tempfile.TemporaryDirectory(prefix="eng-gate-cov-") as folder:
        exit_code, output, report = _run_coverage(ctx, member.directory, Path(folder))
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
