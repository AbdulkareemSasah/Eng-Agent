"""The ``mutation`` step (spec 4.12, AC53): mutmut on the changed R1 and R2 modules, MU001 below ``mutation_min``."""

from __future__ import annotations

import ast
import os
import re
import shutil
import sys
import tempfile
import tomllib
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from eng_dev_gate.checks.tests_step import _judged_command, _judged_environment, _stale_lock, _uv_available
from eng_dev_gate.config.floors import MUTATION_FLOOR
from eng_dev_gate.config.gate_config import load_gate_config
from eng_dev_gate.config.package_config import PackageConfig, load_package_config
from eng_dev_gate.event import event_path, read_event
from eng_dev_gate.gitio import Change, GitError, SubprocessGit
from eng_dev_gate.globs import matches_any
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import EnvironmentFaultError, UsageError
from eng_dev_gate.toolrun import python_module

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

_RESULT = re.compile(r"^\s+\S+: (.+)$")  # a line of ``mutmut results --all true``: "    <mutant>: <status>"
_KILLED = ("killed", "timeout")  # spec 4.12: the score counts timeouts as killed
_SPINNER = re.compile(r"^[\u2800-\u28ff]")  # the braille frames of the progress display of mutmut
_NO_MUTANT = "could not find any test case for any mutant"  # what mutmut says when no mutant has a test to run
_TAIL_LINES = 8  # lines of mutmut output quoted in MU002; presentation only
_IGNORED = (".git", "mutants", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache")


def parse_results(output: str) -> Counter[str]:
    """Count the mutants of a ``mutmut results --all true`` listing by status; other lines are ignored."""
    return Counter(m.group(1).strip() for line in output.splitlines() if (m := _RESULT.match(line)))


def changed_modules(config: PackageConfig, member_path: str, changes: list[Change]) -> list[str]:
    """Package-relative paths of the added, modified or renamed ``.py`` files that match an R1 or R2 glob."""
    prefix = "" if member_path == "." else f"{member_path}/"
    globs = [*config.r1_modules, *config.r2_modules]
    found = {
        change.path.removeprefix(prefix)
        for change in changes
        if change.status != "D" and change.path.startswith(prefix) and change.path.endswith(".py")
    }
    return sorted(path for path in found if matches_any(path, globs))


def _has_code(directory: Path, module: str) -> bool:
    """True if ``module`` holds a function, method or lambda body (constants-only files have no mutant a test reaches).

    A file that cannot be read or parsed counts as code, so that mutmut reports the fault.
    """
    try:
        tree = ast.parse((directory / module).read_text(encoding="utf-8"))
    except OSError, SyntaxError, ValueError:
        return True
    return any(isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) for node in ast.walk(tree))


def _notice(path: str, reason: str, code: str = "MU002") -> list[Finding]:
    return [Finding(code=code, severity=Severity.NOTICE, path=path, message=f"mutation not run: {reason}")]


def _event_base() -> str | None:
    """Base commit of the pull request in the event file (``GITHUB_EVENT_PATH``), if there is one."""
    path = event_path(None, os.environ)
    event = read_event(path) if path else None
    return event.pull_request.base_sha if event and event.pull_request else None


def _fault(tool: str, code: int, output: str) -> EnvironmentFaultError:
    """MU002 with the last readable lines of ``output``: carriage-return spinner frames are dropped first."""
    lines = [line.strip() for line in re.split(r"[\r\n]+", output)]
    kept = [line for line in lines if line and not _SPINNER.match(line)]
    return EnvironmentFaultError(f"MU002 mutation: {tool} exited {code}: {' | '.join(kept[-_TAIL_LINES:])}")


def _default_base(ctx: StepContext) -> str | None:
    """Merge base of ``HEAD`` with ``origin/<gate_branch>``, or ``None`` when that branch is not known locally."""
    git = SubprocessGit(ctx.root)
    try:
        return git.merge_base(f"origin/{load_gate_config(ctx.gate_root).gate_branch}", "HEAD")
    except GitError:
        return None


def _mutmut(ctx: StepContext, *args: str) -> list[str]:
    """The argv of ``mutmut args``: in the judged tree's environment when the gate root is another tree (spec 4.12)."""
    if _judged_environment(ctx):
        return _judged_command(ctx.root, "-m", "mutmut", *args)
    return python_module("mutmut", *args)


def run_step(ctx: StepContext) -> list[Finding]:
    """Mutate the R1 and R2 modules changed against the merge base and compare the score with ``mutation_min``.

    The score is (killed + timeout) over all mutants, in percent; no ``mutation_min`` means the floor of 80. The
    backend configuration is written by the gate into a copy of the package, so the package cannot choose what is
    mutated. Where mutmut cannot run (Windows, ADR-0002) the step reports a notice locally and fails in CI.

    Raises:
        UsageError: the package configures mutmut itself (exit 2).
        EnvironmentFaultError: MU002, mutmut failed or cannot run in CI (exit 3).
    """
    member = ctx.member
    if member is None:
        raise UsageError("mutation: the step needs a workspace member")
    config = load_package_config(member.directory / "pyproject.toml")
    if not (config.r1_modules or config.r2_modules):
        return []
    base = ctx.base or _event_base() or _default_base(ctx)
    if base is None:
        return _notice(member.path, "no base commit (pass --base, run in a pull request or fetch origin/<gate branch>)")
    git = SubprocessGit(ctx.root)
    modules = changed_modules(config, member.path, git.name_status(git.merge_base(base, "HEAD"), "HEAD"))
    if not modules:
        return []
    if not (modules := [module for module in modules if _has_code(member.directory, module)]):
        return _notice(member.path, "nothing to mutate: the changed files hold no function body", "MU003")
    if sys.platform == "win32":
        if os.environ.get("CI"):
            raise EnvironmentFaultError("MU002 mutation: mutmut has no native Windows support (ADR-0002)")
        return _notice(member.path, "mutmut has no native Windows support (ADR-0002)")
    pyproject = member.directory / "pyproject.toml"
    if "mutmut" in tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}):
        raise UsageError(f"{pyproject}: [tool.mutmut] is not allowed; the gate configures mutation")
    if _judged_environment(ctx):
        if not _uv_available():
            raise EnvironmentFaultError("MU002 mutation: uv is not available; the judged tree needs its environment")
        if (stale := _stale_lock(ctx)) is not None:
            return [stale]
    with tempfile.TemporaryDirectory(prefix="eng-gate-mut-") as work:
        copy = Path(work) / "member"
        shutil.copytree(member.directory, copy, ignore=shutil.ignore_patterns(*_IGNORED))
        # the whole source tree is copied so that the mutants form complete packages and shadow an installed member;
        # the pytest addopts of the member (coverage thresholds, plugins) are switched off for the mutated runs
        roots = "".join(f"\n    {root}" for root in sorted({module.split("/")[0] for module in modules}))
        listed = "".join(f"\n    {module}" for module in modules)
        # mutmut copies only the source, tests/, setup.cfg, pyproject.toml and lock files: the rest is listed (AC53b)
        skip = {"src", "tests", "setup.cfg", "pyproject.toml", *_IGNORED}
        extra = "".join(f"\n    {entry}" for entry in sorted(p.name for p in copy.iterdir() if p.name not in skip))
        (copy / "setup.cfg").write_text(
            f"[mutmut]\nsource_paths={roots}\nonly_mutate={listed}\nalso_copy={extra}\n"
            "pytest_add_cli_args=\n    -o\n    addopts=\n"
            "pytest_add_cli_args_test_selection=\n    tests/\n",
            encoding="utf-8",
        )
        ran = ctx.runner.run(_mutmut(ctx, "run"), copy)
        listing = ctx.runner.run(_mutmut(ctx, "results", "--all", "true"), copy)
        counts = parse_results(listing.output) if listing.exit_code == 0 else None
        stopped = ran.exit_code == 0 or _NO_MUTANT in ran.output  # mutmut ended without a fault of its own
        if counts is not None and not counts and stopped:
            # mutmut mutates less than _has_code admits (a module-level lambda, decorated methods only): AC53a
            return _notice(member.path, "nothing to mutate: mutmut produced no mutant", "MU003")
        if not stopped:
            raise _fault("mutmut run", ran.exit_code, ran.output)
        if counts is None:
            raise _fault("mutmut results", listing.exit_code, listing.output)
    # mutants no test covers ("no tests") are survivors: only killed and timeout count (AC53a)
    total, killed = counts.total(), sum(counts[status] for status in _KILLED)
    minimum = MUTATION_FLOOR if config.mutation_min is None else config.mutation_min
    if killed * 100 < minimum * total:
        message = f"mutation score {killed}/{total} is below {minimum} % on {', '.join(modules)}"
        return [Finding(code="MU001", severity=Severity.ERROR, path=member.path, message=message)]
    return []
