"""``test-first`` part 2 (spec 4.7 step 4.3 to 4.5): the base worktree, the pytest runs and the classification.

Every new or changed test must fail at the merge base (TF004 otherwise) and pass at the head (TF005 otherwise). A run
that cannot give a verdict is TF009 and a base that is not isolated is TF011; both exit 3 (:class:`RunFaultError`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from eng_dev_gate import judged_run
from eng_dev_gate.checks.tests_step import _judged_command
from eng_dev_gate.config.package_config import load_package_config
from eng_dev_gate.gitio import SubprocessGit
from eng_dev_gate.pytest_plugin import BLOCKED_ENV
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import EnvironmentFaultError
from eng_dev_gate.toolrun import ToolResult
from eng_dev_gate.workspace import Member, discover_members

if TYPE_CHECKING:
    from eng_dev_gate.checks.test_first import Selection

_PROBE = (
    "import importlib.util, sys\nfor n in sys.argv[1:]:\n    s = importlib.util.find_spec(n)\n"
    "    print(n, (s.origin or '') if s else '', sep='\\t')\n"
)  # prints ``<import name> TAB <file that the name resolves to>``


_SCRIPT = str(Path(judged_run.__file__).resolve())  # the gate's stdlib-only entry point for the base run


class RunFaultError(EnvironmentFaultError):
    """TF009 (pytest could not give a verdict) or TF011 (the base is not isolated): exit 3."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code} {message}")


class Runner(Protocol):
    """Runs a command with an environment and a time limit."""

    def run(self, argv: Sequence[str], cwd: Path, env: Mapping[str, str], timeout_seconds: float) -> ToolResult:
        """Run ``argv`` in ``cwd``; raise :class:`RunFaultError` when it cannot start or exceeds the limit."""
        ...


class SubprocessRunner:
    """:class:`Runner` over ``subprocess.run`` (no shell)."""

    def run(self, argv: Sequence[str], cwd: Path, env: Mapping[str, str], timeout_seconds: float) -> ToolResult:
        """Run ``argv`` and return its exit code and merged output.

        Raises:
            RunFaultError: TF009, the command cannot start or ran longer than ``timeout_seconds``.
        """
        try:
            done = subprocess.run(  # noqa: S603  # B-046: no shell; the arguments are a list
                list(argv), cwd=cwd, env=dict(env), capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout_seconds, check=False,
            )  # fmt: skip
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RunFaultError("TF009", f"{argv[0]} could not finish within {timeout_seconds} s: {error}") from error
        return ToolResult(exit_code=done.returncode, output=done.stdout + done.stderr)


class WorktreeGit(SubprocessGit):
    """The git calls that manage the temporary worktree."""

    def run_git(self, *args: str) -> str:
        """Run ``git args`` in the working directory; raise ``GitError`` on failure."""
        return self._run(*args)


def interpreter(root: Path, judged: bool) -> list[str]:
    """The Python command of the runs: the gate's own, or (``judged``, in a pull request) the judged tree's."""
    return _judged_command(root) if judged else [sys.executable]


@contextmanager
def base_worktree(git: WorktreeGit, merge_base: str, commit: str, paths: Sequence[str]) -> Iterator[Path]:
    """Yield a detached worktree of ``merge_base`` holding the ``paths`` of ``commit``; remove it in all cases.

    Raises:
        GitError: git failed (exit 3).
    """
    folder = Path(tempfile.mkdtemp(prefix="eng-gate-tf-"))
    tree = folder / "base"
    try:
        git.run_git("worktree", "add", "--detach", str(tree), merge_base)
        try:
            WorktreeGit(tree).run_git("checkout", commit, "--", *paths)
            yield tree
        finally:
            git.run_git("worktree", "remove", "--force", str(tree))
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def outcomes(report: Path, tests: Sequence[str]) -> dict[str, set[str]]:
    """Read a JUnit report: per test id (``<path>::[<Class>::]<function>``, relative to the run folder), the kinds.

    A kind is ``passed``, ``failed`` (failure or error) or ``skipped`` (skip or xfail). Parametrized cases are all
    kept. A collection error is reported under the module name and fails every test of that module.

    Raises:
        RunFaultError: TF009, the report is missing or unreadable, or a test has no result.
    """
    try:
        cases = [
            (c.get("classname", ""), c.get("name", ""), c)
            for c in ET.parse(report).getroot().iter("testcase")  # noqa: S314  # B-046: pytest's own file, in a temp folder
        ]
    except (OSError, ET.ParseError) as error:
        raise RunFaultError("TF009", f"pytest left no readable result file: {error}") from error
    found: dict[str, set[str]] = {}
    for test in tests:
        path, _, rest = test.partition("::")
        module = path.removesuffix(".py").replace("/", ".")
        *classes, function = rest.split("::")
        classname = ".".join([module, *classes])
        found[test] = {
            "failed" if case.find("failure") is not None or case.find("error") is not None
            else "skipped" if case.find("skipped") is not None else "passed"
            for cn, name, case in cases
            if (cn == classname and name.split("[")[0] == function) or (cn == "" and name == module)
        }  # fmt: skip
        if not found[test]:
            raise RunFaultError("TF009", f"pytest reported no result for {test}")
    return found


def _environment(tree: Path, members: Sequence[Member]) -> dict[str, str]:
    """The environment of a run: ``PYTHONPATH`` is the ``src`` folders of the members of ``tree`` and nothing else."""
    sources = [str(tree / m.path / "src") for m in members if (tree / m.path / "src").is_dir()]
    return {**os.environ, "PYTHONPATH": os.pathsep.join(sources), "PYTHONDONTWRITEBYTECODE": "1"}


def _probe(
    runner: Runner, python: Sequence[str], tree: Path, member: Member, env: Mapping[str, str], limit: int,
    hidden: Sequence[str] = (),
) -> None:  # fmt: skip
    """TF011 unless every import name of the package that exists in ``tree`` resolves to a file inside ``tree``."""
    folder = tree / member.path
    if hidden:  # the package is new in the pull request: its names are blocked, none may resolve (AC27a)
        done = runner.run([*python, _SCRIPT, "probe", *hidden], folder, env, limit)
        where = dict(line.partition("\t")[::2] for line in done.output.splitlines())
        if done.exit_code != 0 or any(where.get(n) for n in hidden):
            raise RunFaultError("TF011", f"a name of the new package {member.path} resolves in the base run: {where}")
        return
    names = [
        n for n in load_package_config(folder / "pyproject.toml").import_names
        if (folder / "src" / n).is_dir() or (folder / "src" / f"{n}.py").is_file()
    ]  # fmt: skip
    if not names:
        return
    done = runner.run([*python, "-c", _PROBE, *names], folder, env, limit)
    where = dict(line.partition("\t")[::2] for line in done.output.splitlines())
    for name in names:
        origin = where.get(name, "")
        if done.exit_code != 0 or not origin or not Path(origin).resolve().is_relative_to(tree.resolve()):
            raise RunFaultError(
                "TF011", f"package {name} does not resolve inside the base worktree: {origin or 'nowhere'}"
            )


def _run(
    runner: Runner, python: Sequence[str], folder: Path, env: Mapping[str, str], files: Sequence[str], report: Path,
    limit: int, hidden: Sequence[str] = (),
) -> bool:  # fmt: skip
    """Run pytest on ``files`` in ``folder``, writing ``report``; exit 0 and 1 are verdicts, others TF009.

    ``hidden`` names (set in ``env``) are blocked by the base plugin; ``True``: a conftest.py imported one (red).
    """
    start = [_SCRIPT, "pytest", "-p", judged_run.BASE_PLUGIN] if hidden else ["-m", "pytest"]
    argv = [*python, *start, "-p", "no:cacheprovider", "--continue-on-collection-errors",
            "--rootdir", str(folder), "--junitxml", str(report), *files]  # fmt: skip
    done = runner.run(argv, folder, env, limit)
    if hidden and done.exit_code == 4 and "TF011: " in done.output:
        return True
    if done.exit_code not in (0, 1):
        tail = " | ".join(done.output.splitlines()[-5:])
        raise RunFaultError("TF009", f"pytest exited {done.exit_code} in {folder}: {tail}")
    return False


def judge(
    root: Path,
    git: WorktreeGit,
    merge_base: str,
    selection: Selection,
    runner: Runner,
    python: Sequence[str],
    limit: int,
) -> list[Finding]:
    """Run the selected tests at the merge base and at the head ``root``; return TF004 and TF005 findings.

    Args:
        root: the checked-out head.
        merge_base: the merge base commit of the pull request.
        selection: the first test commit and its new or changed tests.
        runner: runs the probe and pytest.
        python: the Python command (:func:`interpreter`).
        limit: seconds allowed per pytest run (``limits.test_run_seconds``).

    Raises:
        RunFaultError: TF009 or TF011, see the module docstring.
        GitError: git failed.
        UsageError: the head has no workspace.
    """
    members = discover_members(root)
    groups: dict[Member, list[str]] = {}
    for test in selection.tests:
        owner = max((m for m in members if test.startswith(f"{m.path}/")), key=lambda m: len(m.path), default=None)
        if owner is None:
            raise RunFaultError("TF009", f"no workspace member owns the test {test}")
        groups.setdefault(owner, []).append(test)
    findings: list[Finding] = []
    with base_worktree(git, merge_base, selection.commit, selection.paths) as base:
        for number, (member, ids) in enumerate(groups.items()):
            local = [t.removeprefix(f"{member.path}/") for t in ids]
            files = sorted({t.partition("::")[0] for t in local})
            new = not (base / member.path / "pyproject.toml").is_file()
            hidden = load_package_config(root / member.path / "pyproject.toml").import_names if new else []
            for tree, wanted in ((base, "failed"), (root, "passed")):
                env = _environment(tree, members)
                blocked = hidden if tree is base else []
                if blocked:
                    env[BLOCKED_ENV] = ",".join(blocked)
                if tree is base:
                    _probe(runner, python, base, member, env, limit, blocked)
                report = base.parent / f"{number}-{wanted}.xml"
                red = _run(runner, python, tree / member.path, env, files, report, limit, blocked)
                found = {t: {"failed"} for t in local} if red else outcomes(report, local)
                for test, local_id in zip(ids, local, strict=True):
                    kinds = found[local_id]
                    # red: some case failed (a parametrized test gains cases); green: every case passed
                    if (wanted not in kinds) if tree is base else (kinds != {wanted}):
                        code, what = ("TF004", "red at the base") if tree is base else ("TF005", "green at the head")
                        message = f"test {test} is not {what} (reported {', '.join(sorted(kinds))})"
                        path = test.partition("::")[0]
                        findings.append(Finding(code=code, severity=Severity.ERROR, path=path, message=message))
    return findings
