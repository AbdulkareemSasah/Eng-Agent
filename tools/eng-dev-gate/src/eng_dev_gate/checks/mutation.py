"""The ``mutation`` step (spec 4.12, AC53): mutmut on the changed R1 and R2 modules, MU001 below ``mutation_min``."""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import tomllib
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from eng_dev_gate.config.floors import MUTATION_FLOOR
from eng_dev_gate.config.package_config import PackageConfig, load_package_config
from eng_dev_gate.event import event_path, read_event
from eng_dev_gate.gitio import Change, SubprocessGit
from eng_dev_gate.globs import matches_any
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import EnvironmentFaultError, UsageError
from eng_dev_gate.toolrun import python_module

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

_RESULT = re.compile(r"^\s+\S+: (.+)$")  # a line of ``mutmut results --all true``: "    <mutant>: <status>"
_KILLED = ("killed", "timeout")  # spec 4.12: the score counts timeouts as killed
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


def _notice(path: str, reason: str) -> list[Finding]:
    return [Finding(code="MU002", severity=Severity.NOTICE, path=path, message=f"mutation not run: {reason}")]


def _event_base() -> str | None:
    """Base commit of the pull request in the event file (``GITHUB_EVENT_PATH``), if there is one."""
    path = event_path(None, os.environ)
    event = read_event(path) if path else None
    return event.pull_request.base_sha if event and event.pull_request else None


def _fault(tool: str, code: int, output: str) -> EnvironmentFaultError:
    return EnvironmentFaultError(f"MU002 mutation: {tool} exited {code}: {output[:500]}")


def run_step(ctx: StepContext) -> list[Finding]:
    """Mutate the R1 and R2 modules changed against the merge base and compare the score with ``mutation_min``.

    The score is (killed + timeout) over all mutants, in percent; no ``mutation_min`` means the floor of 80. The
    backend configuration is written by the gate into a copy of the package, so the package cannot choose what is
    mutated. Where mutmut cannot run (Windows, ADR-0002) the step reports a notice locally and fails in CI.

    Raises:
        UsageError: the package configures mutmut itself (exit 2).
        EnvironmentFaultError: MU002, mutmut failed or cannot run in CI (exit 3).
    """
    assert ctx.member is not None  # noqa: S101  # B-049: package steps always have a member
    member = ctx.member
    config = load_package_config(member.directory / "pyproject.toml")
    if not (config.r1_modules or config.r2_modules):
        return []
    base = ctx.base or _event_base()
    if base is None:
        return _notice(member.path, "no base commit (pass --base or run in a pull request)")
    git = SubprocessGit(ctx.root)
    modules = changed_modules(config, member.path, git.name_status(git.merge_base(base, "HEAD"), "HEAD"))
    if not modules:
        return []
    if sys.platform == "win32":
        if os.environ.get("CI"):
            raise EnvironmentFaultError("MU002 mutation: mutmut has no native Windows support (ADR-0002)")
        return _notice(member.path, "mutmut has no native Windows support (ADR-0002)")
    pyproject = member.directory / "pyproject.toml"
    if "mutmut" in tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}):
        raise UsageError(f"{pyproject}: [tool.mutmut] is not allowed; the gate configures mutation")
    with tempfile.TemporaryDirectory(prefix="eng-gate-mut-") as work:
        copy = Path(work) / "member"
        shutil.copytree(member.directory, copy, ignore=shutil.ignore_patterns(*_IGNORED))
        listed = "".join(f"\n    {module}" for module in modules)
        (copy / "setup.cfg").write_text(
            f"[mutmut]\nsource_paths={listed}\npytest_add_cli_args_test_selection=\n    tests/\n", encoding="utf-8"
        )
        ran = ctx.runner.run(python_module("mutmut", "run"), copy)
        if ran.exit_code != 0:
            raise _fault("mutmut run", ran.exit_code, ran.output)
        listing = ctx.runner.run(python_module("mutmut", "results", "--all", "true"), copy)
        if listing.exit_code != 0:
            raise _fault("mutmut results", listing.exit_code, listing.output)
    counts = parse_results(listing.output)
    total, killed = counts.total(), sum(counts[status] for status in _KILLED)
    minimum = MUTATION_FLOOR if config.mutation_min is None else config.mutation_min
    if total and killed * 100 < minimum * total:
        message = f"mutation score {killed}/{total} is below {minimum} % on {', '.join(modules)}"
        return [Finding(code="MU001", severity=Severity.ERROR, path=member.path, message=message)]
    return []
