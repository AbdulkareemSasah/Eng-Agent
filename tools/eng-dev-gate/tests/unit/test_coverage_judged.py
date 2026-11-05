"""Tests of the ``tests`` step with a gate root other than the judged tree (B-059), with a scripted tool runner."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from eng_dev_gate import judged_run
from eng_dev_gate.checks import tests_step
from eng_dev_gate.checks.registry import StepContext
from eng_dev_gate.checks.tests_step import tests as run_step
from eng_dev_gate.results import EnvironmentFaultError
from eng_dev_gate.toolrun import ToolResult
from eng_dev_gate.workspace import discover_members
from support.coverage_toy import make_toy
from support.repo import Repo, make_repo

REPORT = {"totals": {"num_statements": 1, "covered_lines": 1, "num_branches": 0, "covered_branches": 0}}


class Recorder:
    """Scripted runner: writes the coverage report for ``coverage json`` and records every call.

    ``lock_exit`` is the exit code of ``uv lock --check``; ``run_exit`` the one of the pytest session.
    """

    def __init__(self, lock_exit: int = 0, run_exit: int = 0) -> None:
        self.calls: list[tuple[list[str], Path]] = []
        self._lock_exit, self._run_exit = lock_exit, run_exit

    def of_kind(self, kind: str) -> tuple[list[str], Path]:
        """The first recorded call of ``kind``: ``lock``, ``run`` (the coverage session) or ``json`` (the report)."""
        for argv, cwd in self.calls:
            if kind == "lock" and argv[:3] == ["uv", "lock", "--check"]:
                return argv, cwd
            if kind == "json" and "json" in argv:
                return argv, cwd
            if kind == "run" and "json" not in argv and argv[:2] == ["uv", "run"]:
                return argv, cwd
        raise AssertionError(f"no {kind} call in {self.calls}")

    def run(self, argv: Sequence[str], cwd: Path, *, timeout_seconds: float | None = None) -> ToolResult:
        self.calls.append((list(argv), cwd))
        if argv[:3] == ["uv", "lock", "--check"]:
            return ToolResult(exit_code=self._lock_exit, output="error: the lockfile needs to be updated")
        if "json" not in argv and argv[:2] == ["uv", "run"]:
            return ToolResult(exit_code=self._run_exit, output="")
        if "json" in argv:
            Path(argv[argv.index("-o") + 1]).write_text(json.dumps(REPORT), encoding="utf-8")
        return ToolResult(exit_code=0, output="")


def _judge(repo: Repo, gate_root: Path, runner: Recorder) -> None:
    make_toy(repo)
    (member,) = discover_members(repo.root)
    assert run_step(StepContext(repo.root, gate_root, member, runner)) == []


@pytest.fixture
def gate_root(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "base").root


def test_judged_tree_tests_run_through_uv_in_the_judged_project(repo: Repo, gate_root: Path) -> None:
    runner = Recorder()
    _judge(repo, gate_root, runner)
    run_argv, run_cwd = runner.of_kind("run")
    python = run_argv.index("python")
    assert run_argv[:2] == ["uv", "run"]
    assert run_argv[run_argv.index("--project") + 1] == str(repo.root)
    assert {"--locked", "--all-packages"} <= set(run_argv[:python])
    assert run_argv[run_argv.index("--group") + 1] == "dev"
    assert Path(run_argv[python + 1]) == Path(judged_run.__file__)
    assert run_cwd == repo.root / "pkgs" / "a"


def test_judged_tree_run_uses_the_base_plugin_and_the_generated_rc_file(repo: Repo, gate_root: Path) -> None:
    runner = Recorder()
    _judge(repo, gate_root, runner)
    run_argv, _ = runner.of_kind("run")
    assert run_argv[run_argv.index("-p") + 1] == judged_run.BASE_PLUGIN
    assert "eng_dev_gate.pytest_plugin" not in run_argv
    assert judged_run.NO_COV_MARKER in run_argv
    rcfile = Path(run_argv[run_argv.index("--rcfile") + 1])
    assert not rcfile.is_relative_to(repo.root)
    assert not rcfile.is_relative_to(gate_root)


def test_judged_tree_report_is_made_in_the_judged_environment(repo: Repo, gate_root: Path) -> None:
    runner = Recorder()
    _judge(repo, gate_root, runner)
    json_argv, json_cwd = runner.of_kind("json")
    python = json_argv.index("python")
    assert json_argv[:2] == ["uv", "run"]
    assert json_argv[json_argv.index("--project") + 1] == str(repo.root)
    assert {"--locked", "--all-packages"} <= set(json_argv[:python])
    assert json_argv[python + 1 : python + 4] == ["-m", "coverage", "json"]
    assert not json_cwd.is_relative_to(repo.root)  # nothing of the judged tree is on the import path


def test_without_uv_the_judged_tree_run_is_an_environment_fault(
    repo: Repo, gate_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tests_step, "_uv_available", lambda: False)
    runner = Recorder()
    make_toy(repo)
    (member,) = discover_members(repo.root)
    with pytest.raises(EnvironmentFaultError, match="uv"):
        run_step(StepContext(repo.root, gate_root, member, runner))
    assert runner.calls == []


def test_gate_root_equal_to_the_tree_keeps_the_head_run(repo: Repo) -> None:
    """Head mode (push runs, local runs): the gate's own interpreter, as before."""
    runner = Recorder()
    _judge(repo, repo.root, runner)
    assert runner.calls[0][0][1:3] == ["-m", "coverage"]
    assert all(call[0][:2] != ["uv", "lock"] for call in runner.calls)  # the lock step judges the lock file
    assert all(call[0][0] != "uv" for call in runner.calls)


def test_judged_tree_run_keeps_uv_warnings_out_of_the_output(repo: Repo, gate_root: Path) -> None:
    """An inherited ``VIRTUAL_ENV`` makes uv warn on stderr; the warning must not fill a fault message."""
    runner = Recorder()
    _judge(repo, gate_root, runner)
    for kind in ("run", "json"):
        assert "--quiet" in runner.of_kind(kind)[0][:8]


def test_stale_lock_file_is_st001_and_the_tests_do_not_run(repo: Repo, gate_root: Path) -> None:
    """``uv run --locked`` would exit 2, which is outside pytest's codes; the step judges the lock file first."""
    runner = Recorder(lock_exit=1)
    make_toy(repo)
    (member,) = discover_members(repo.root)
    (finding,) = run_step(StepContext(repo.root, gate_root, member, runner))
    assert finding.code == "ST001"
    assert "uv.lock" in finding.message
    assert "lockfile needs to be updated" in finding.message
    assert all(call[0][:2] != ["uv", "run"] for call in runner.calls)


def test_pytest_failure_in_the_judged_tree_is_still_st001(repo: Repo, gate_root: Path) -> None:
    runner = Recorder(run_exit=1)
    make_toy(repo)
    (member,) = discover_members(repo.root)
    (finding,) = run_step(StepContext(repo.root, gate_root, member, runner))
    assert finding.code == "ST001"
    assert "pytest exited 1" in finding.message
