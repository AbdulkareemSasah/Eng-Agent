"""Unit tests of the ``mutation`` step (spec 4.12, AC53): changed R1 and R2 modules only, score against mutation_min."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from eng_dev_gate.checks import mutation
from eng_dev_gate.checks.registry import StepContext
from eng_dev_gate.report import Severity
from eng_dev_gate.results import EnvironmentFaultError, UsageError
from eng_dev_gate.toolrun import ToolResult
from eng_dev_gate.workspace import Member
from support.repo import Repo
from support.toy import GATE_YML, root_pyproject

TABLE = (
    '[tool.eng-gate]\nprofile = "tool"\nlayer = "tool"\nimport_names = ["a"]\n'
    "coverage_line = 95\ncoverage_branch = 90\n"
    'r1_modules = ["src/a/core.py"]\nr2_modules = ["src/a/rules/*.py"]\nmutation_min = {minimum}\n'
)
HEAD = '[project]\nname = "a"\nversion = "0.1.0"\nrequires-python = ">=3.14"\ndependencies = []\n'


class FakeMutmut:
    """ToolRunner that plays mutmut: records the generated setup.cfg and answers ``results`` with ``statuses``."""

    def __init__(self, statuses: Sequence[str], run_exit: int = 0) -> None:
        self.statuses, self.run_exit = list(statuses), run_exit
        self.config: str | None = None
        self.calls: list[list[str]] = []

    def run(self, argv: Sequence[str], cwd: Path) -> ToolResult:
        self.calls.append(list(argv))
        if "run" in argv:
            self.config = (cwd / "setup.cfg").read_text(encoding="utf-8")
            return ToolResult(exit_code=self.run_exit, output="boom")
        lines = "".join(f"    a.core.x_f__mutmut_{i}: {s}\n" for i, s in enumerate(self.statuses))
        return ToolResult(exit_code=0, output=lines)


def _setup(repo: Repo, minimum: int = 80, table: str | None = None) -> tuple[str, Member]:
    """Commit a base with two R modules and some other modules; return the base SHA and the member."""
    files = {
        "pyproject.toml": root_pyproject(["pkgs/a"]),
        ".gate/gate.yml": GATE_YML,
        "pkgs/a/pyproject.toml": HEAD + (table if table is not None else TABLE.format(minimum=minimum)),
        "pkgs/a/src/a/__init__.py": "",
        "pkgs/a/src/a/core.py": "A = 1\n",
        "pkgs/a/src/a/other.py": "B = 1\n",
        "pkgs/a/src/a/gone.py": "C = 1\n",
        "pkgs/a/src/a/rules/__init__.py": "",
        "pkgs/a/src/a/rules/r1.py": "D = 1\n",
    }
    base = repo.commit(files)
    return base, Member(name="a", path="pkgs/a", directory=repo.root / "pkgs" / "a")


def _change(repo: Repo) -> None:
    repo.commit({"pkgs/a/src/a/core.py": "A = 2\n", "pkgs/a/src/a/other.py": "B = 2\n"})
    repo.git("rm", "-q", "pkgs/a/src/a/gone.py")
    repo.commit({"pkgs/a/src/a/rules/r2.py": "E = 1\n", "pkgs/a/src/a/rules/__init__.py": "# changed\n"})


def _context(repo: Repo, member: Member, runner: FakeMutmut, base: str | None) -> StepContext:
    return StepContext(repo.root, repo.root, member, runner, base=base)


def test_changed_modules_only(repo: Repo) -> None:
    base, member = _setup(repo)
    _change(repo)
    runner = FakeMutmut(["killed"] * 5)
    assert mutation.run_step(_context(repo, member, runner, base)) == []
    assert runner.config is not None
    listed = {line.strip() for line in runner.config.splitlines() if line.strip().startswith("src/")}
    assert listed == {"src/a/core.py", "src/a/rules/r2.py", "src/a/rules/__init__.py"}


def test_nothing_changed_runs_no_tool(repo: Repo) -> None:
    base, member = _setup(repo)
    repo.commit({"pkgs/a/src/a/other.py": "B = 3\n"})
    runner = FakeMutmut([])
    assert mutation.run_step(_context(repo, member, runner, base)) == []
    assert runner.calls == []


def test_package_without_r_modules_is_not_judged(repo: Repo) -> None:
    table = (
        TABLE.format(minimum=80)
        .replace('r1_modules = ["src/a/core.py"]\n', "")
        .replace('r2_modules = ["src/a/rules/*.py"]\n', "")
    )
    base, member = _setup(repo, table=table)
    _change(repo)
    runner = FakeMutmut(["survived"])
    assert mutation.run_step(_context(repo, member, runner, base)) == []
    assert runner.calls == []


@pytest.mark.parametrize(
    ("statuses", "minimum", "expected"),
    [
        (["killed", "killed", "killed", "timeout", "survived"], 80, []),  # 4 of 5 = 80 %, timeouts count as killed
        (["killed", "killed", "killed", "timeout", "survived"], 81, ["MU001"]),
        (["killed", "survived", "no tests", "suspicious", "skipped"], 80, ["MU001"]),  # only killed and timeout count
        ([], 100, []),  # nothing to mutate
    ],
)
def test_score_threshold(repo: Repo, statuses: list[str], minimum: int, expected: list[str]) -> None:
    base, member = _setup(repo, minimum=minimum)
    _change(repo)
    findings = mutation.run_step(_context(repo, member, FakeMutmut(statuses), base))
    assert [f.code for f in findings] == expected
    assert all(f.path == "pkgs/a" and f.severity is Severity.ERROR for f in findings)


def test_default_minimum_is_the_floor(repo: Repo) -> None:
    table = TABLE.format(minimum=80).replace("mutation_min = 80\n", "")
    base, member = _setup(repo, table=table)
    _change(repo)
    statuses = ["killed"] * 3 + ["survived"]  # 75 % is below the floor of 80
    assert [f.code for f in mutation.run_step(_context(repo, member, FakeMutmut(statuses), base))] == ["MU001"]


def test_mutation_settings_of_the_package_are_refused(repo: Repo) -> None:
    base, member = _setup(repo, table=TABLE.format(minimum=80) + "[tool.mutmut]\ndo_not_mutate = ['*']\n")
    _change(repo)
    with pytest.raises(UsageError, match=r"tool\.mutmut"):
        mutation.run_step(_context(repo, member, FakeMutmut(["killed"]), base))


def test_backend_failure_is_an_environment_fault(repo: Repo) -> None:
    base, member = _setup(repo)
    _change(repo)
    with pytest.raises(EnvironmentFaultError, match="MU002"):
        mutation.run_step(_context(repo, member, FakeMutmut([], run_exit=1), base))


def test_platform_without_backend(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    base, member = _setup(repo)
    _change(repo)
    monkeypatch.setattr(sys, "platform", "win32")
    runner = FakeMutmut(["killed"])
    findings = mutation.run_step(_context(repo, member, runner, base))  # local: reported, not failed
    assert [(f.code, f.severity) for f in findings] == [("MU002", Severity.NOTICE)]
    assert runner.calls == []
    monkeypatch.setenv("CI", "true")  # in CI a skipped mutation step fails (spec 4.12)
    with pytest.raises(EnvironmentFaultError, match="MU002"):
        mutation.run_step(_context(repo, member, runner, base))


def test_no_base_commit_is_a_notice(repo: Repo) -> None:
    _, member = _setup(repo)
    findings = mutation.run_step(_context(repo, member, FakeMutmut([]), None))
    assert [(f.code, f.severity) for f in findings] == [("MU002", Severity.NOTICE)]


def test_parse_results() -> None:
    text = (
        "warning: noise\n    a.x_f__mutmut_1: killed\n    a.x_f__mutmut_2: no tests\n\n    a.x_g__mutmut_1: timeout\n"
    )
    assert mutation.parse_results(text) == {"killed": 1, "no tests": 1, "timeout": 1}
