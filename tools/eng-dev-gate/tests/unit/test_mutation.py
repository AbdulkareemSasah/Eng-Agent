"""Unit tests of the ``mutation`` step (spec 4.12, AC53): changed R1 and R2 modules only, score against mutation_min."""

from __future__ import annotations

import configparser
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
NO_MUTANT = "Failed: could not find any test case for any mutant"
HEAD = '[project]\nname = "a"\nversion = "0.1.0"\nrequires-python = ">=3.14"\ndependencies = []\n'


class FakeMutmut:
    """ToolRunner that plays mutmut: records the generated setup.cfg and answers ``results`` with ``statuses``."""

    def __init__(
        self, statuses: Sequence[str], run_exit: int = 0, run_output: str = "boom", lock_exit: int = 0
    ) -> None:
        self.statuses, self.run_exit, self.run_output, self.lock_exit = list(statuses), run_exit, run_output, lock_exit
        self.config: str | None = None
        self.calls: list[list[str]] = []

    def run(self, argv: Sequence[str], cwd: Path) -> ToolResult:
        self.calls.append(list(argv))
        if list(argv[:2]) == ["uv", "lock"]:
            return ToolResult(exit_code=self.lock_exit, output="lock is stale")
        if "results" in argv:
            lines = "".join(f"    a.core.x_f__mutmut_{i}: {s}\n" for i, s in enumerate(self.statuses))
            return ToolResult(exit_code=0, output=lines)
        if "run" in argv:
            self.config = (cwd / "setup.cfg").read_text(encoding="utf-8")
            return ToolResult(exit_code=self.run_exit, output=self.run_output)
        return ToolResult(exit_code=0, output="")


def _mutmut_option(config: str, key: str) -> list[str]:
    """The lines of a multi-line option of the generated ``[mutmut]`` section."""
    parser = configparser.ConfigParser()
    parser.read_string(config)
    return parser["mutmut"][key].split()


def _setup(repo: Repo, minimum: int = 80, table: str | None = None) -> tuple[str, Member]:
    """Commit a base with two R modules and some other modules; return the base SHA and the member."""
    files = {
        "pyproject.toml": root_pyproject(["pkgs/a"]),
        ".gate/gate.yml": GATE_YML,
        "pkgs/a/pyproject.toml": HEAD + (table if table is not None else TABLE.format(minimum=minimum)),
        "pkgs/a/src/a/__init__.py": "",
        "pkgs/a/src/a/core.py": "def a():\n    return 1\n",
        "pkgs/a/src/a/other.py": "B = 1\n",
        "pkgs/a/src/a/gone.py": "C = 1\n",
        "pkgs/a/src/a/rules/__init__.py": "",
        "pkgs/a/src/a/rules/r1.py": "def d():\n    return 1\n",
    }
    base = repo.commit(files)
    return base, Member(name="a", path="pkgs/a", directory=repo.root / "pkgs" / "a")


def _change(repo: Repo) -> None:
    repo.commit({"pkgs/a/src/a/core.py": "def a():\n    return 2\n", "pkgs/a/src/a/other.py": "B = 2\n"})
    repo.git("rm", "-q", "pkgs/a/src/a/gone.py")
    repo.commit(
        {"pkgs/a/src/a/rules/r2.py": "def e():\n    return 1\n", "pkgs/a/src/a/rules/__init__.py": "# changed\n"}
    )


def _context(repo: Repo, member: Member, runner: FakeMutmut, base: str | None) -> StepContext:
    return StepContext(repo.root, repo.root, member, runner, base=base)


def test_changed_modules_only(repo: Repo) -> None:
    base, member = _setup(repo)
    _change(repo)
    runner = FakeMutmut(["killed"] * 5)
    assert mutation.run_step(_context(repo, member, runner, base)) == []
    assert runner.config is not None
    assert set(_mutmut_option(runner.config, "only_mutate")) == {
        "src/a/core.py",
        "src/a/rules/r2.py",
    }


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
        (["killed"], 100, []),
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
        mutation.run_step(_context(repo, member, FakeMutmut(["killed"], run_exit=1), base))


def test_platform_without_backend(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    base, member = _setup(repo)
    _change(repo)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("CI", raising=False)  # the CI runner sets it; the local case needs it unset
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


def test_whole_source_tree_is_copied_and_the_member_addopts_are_off(repo: Repo) -> None:
    """The mutants must be a complete package so that they shadow an installed copy (B-049 review); addopts are off."""
    base, member = _setup(repo)
    _change(repo)
    runner = FakeMutmut(["killed"])
    mutation.run_step(_context(repo, member, runner, base))
    assert runner.config is not None
    assert _mutmut_option(runner.config, "source_paths") == ["src"]
    assert _mutmut_option(runner.config, "pytest_add_cli_args") == ["-o", "addopts="]


def test_fault_message_keeps_the_readable_tail_of_the_output(repo: Repo) -> None:
    frames = "".join(f"\r\u280b Generating mutants {i}" for i in range(400))
    base, member = _setup(repo)
    _change(repo)
    runner = FakeMutmut(
        [], run_exit=1, run_output=f"{frames}\nImportError: no module named x\nfailed to collect stats\n"
    )
    with pytest.raises(EnvironmentFaultError) as caught:
        mutation.run_step(_context(repo, member, runner, base))
    assert "failed to collect stats" in str(caught.value)
    assert "ImportError" in str(caught.value)
    assert "Generating" not in str(caught.value)


def test_judged_tree_runs_mutmut_in_its_own_environment(repo: Repo, tmp_path: Path) -> None:
    base, member = _setup(repo)
    _change(repo)
    runner = FakeMutmut(["killed"] * 3)
    ctx = StepContext(repo.root, tmp_path, member, runner, base=base)  # gate root differs from the judged tree
    assert mutation.run_step(ctx) == []
    ran = [call for call in runner.calls if "mutmut" in call]
    assert ran
    for call in ran:
        assert call[:2] == ["uv", "run"]
        assert call[call.index("--project") + 1] == str(repo.root)
        assert "--locked" in call
        assert call[call.index("python") + 1 :][:2] == ["-m", "mutmut"]


def test_judged_tree_with_a_stale_lock_is_st001(repo: Repo, tmp_path: Path) -> None:
    base, member = _setup(repo)
    _change(repo)
    runner = FakeMutmut(["killed"], lock_exit=2)
    findings = mutation.run_step(StepContext(repo.root, tmp_path, member, runner, base=base))
    assert [(f.code, f.severity) for f in findings] == [("ST001", Severity.ERROR)]
    assert not [call for call in runner.calls if "mutmut" in call]


def test_no_base_uses_the_merge_base_with_the_gate_branch(repo: Repo) -> None:
    base, member = _setup(repo)
    repo.git("update-ref", "refs/remotes/origin/build/v1", base)
    _change(repo)
    runner = FakeMutmut(["killed"] * 2)
    assert mutation.run_step(_context(repo, member, runner, None)) == []
    assert runner.config is not None  # mutation ran on the modules changed since the gate branch


def _constants_only(repo: Repo) -> None:
    """Change an R1 file and an R2 file that hold module-level constants and no function body."""
    repo.commit(
        {"pkgs/a/src/a/core.py": "__version__ = '2'\n", "pkgs/a/src/a/rules/r1.py": "D = (1, 2)\nclass K:\n    x = 1\n"}
    )


def test_files_without_a_function_body_pass_with_a_notice(repo: Repo) -> None:
    """Constants-only files give mutmut no test to attribute (MU002 fault before B-026); the step passes (MU003)."""
    base, member = _setup(repo)
    _constants_only(repo)
    runner = FakeMutmut(["survived"])
    findings = mutation.run_step(_context(repo, member, runner, base))
    assert [(f.code, f.severity, f.path) for f in findings] == [("MU003", Severity.NOTICE, "pkgs/a")]
    assert runner.calls == []


def test_only_files_with_a_function_body_are_mutated(repo: Repo) -> None:
    base, member = _setup(repo)
    repo.commit(
        {
            "pkgs/a/src/a/core.py": "__version__ = '2'\n",
            "pkgs/a/src/a/rules/r1.py": "D = lambda x: x\n",
            "pkgs/a/src/a/rules/r2.py": "class K:\n    def m(self):\n        return 1\n",
        }
    )
    runner = FakeMutmut(["killed"])
    assert mutation.run_step(_context(repo, member, runner, base)) == []
    assert runner.config is not None
    assert set(_mutmut_option(runner.config, "only_mutate")) == {"src/a/rules/r1.py", "src/a/rules/r2.py"}


def test_real_code_whose_mutants_no_test_covers_stays_a_failure(repo: Repo) -> None:
    base, member = _setup(repo)
    _change(repo)
    findings = mutation.run_step(_context(repo, member, FakeMutmut(["no tests"] * 3), base))
    assert [f.code for f in findings] == ["MU001"]


def test_an_unparsable_file_is_left_to_mutmut(repo: Repo) -> None:
    base, member = _setup(repo)
    repo.commit({"pkgs/a/src/a/core.py": "def (:\n"})
    runner = FakeMutmut(["killed"])
    assert mutation.run_step(_context(repo, member, runner, base)) == []
    assert runner.config is not None
    assert _mutmut_option(runner.config, "only_mutate") == ["src/a/core.py"]


def test_a_run_that_produces_no_mutant_is_mu003_not_a_fault(repo: Repo) -> None:
    """A module-level lambda passes the pre-filter, mutmut makes no mutant and exits 1 (B-079)."""
    base, member = _setup(repo)
    repo.commit({"pkgs/a/src/a/core.py": "X = lambda v: v\n"})
    findings = mutation.run_step(_context(repo, member, FakeMutmut([], run_exit=1, run_output=NO_MUTANT), base))
    assert [(f.code, f.severity, f.path) for f in findings] == [("MU003", Severity.NOTICE, "pkgs/a")]


def test_a_clean_run_with_an_empty_result_list_is_mu003(repo: Repo) -> None:
    base, member = _setup(repo)
    _change(repo)
    findings = mutation.run_step(_context(repo, member, FakeMutmut([]), base))
    assert [f.code for f in findings] == ["MU003"]


def test_mutants_that_exist_and_a_failed_run_stay_mu002(repo: Repo) -> None:
    base, member = _setup(repo)
    _change(repo)
    with pytest.raises(EnvironmentFaultError, match="MU002"):
        mutation.run_step(_context(repo, member, FakeMutmut(["no tests"] * 2, run_exit=1), base))


def test_a_crash_with_an_empty_result_list_stays_mu002(repo: Repo) -> None:
    base, member = _setup(repo)
    _change(repo)
    with pytest.raises(EnvironmentFaultError, match="MU002"):
        mutation.run_step(_context(repo, member, FakeMutmut([], run_exit=1), base))
