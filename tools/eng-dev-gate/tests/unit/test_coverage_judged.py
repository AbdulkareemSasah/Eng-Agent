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
    """Scripted runner: writes the coverage report for ``coverage json`` and records every call."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Path]] = []

    def run(self, argv: Sequence[str], cwd: Path) -> ToolResult:
        self.calls.append((list(argv), cwd))
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
    run_argv, run_cwd = runner.calls[0]
    assert run_argv[:8] == ["uv", "run", "--project", str(repo.root), "--locked", "--all-packages", "--group", "dev"]
    assert run_argv[8] == "python"
    assert Path(run_argv[9]) == Path(judged_run.__file__)
    assert run_cwd == repo.root / "pkgs" / "a"


def test_judged_tree_run_uses_the_base_plugin_and_the_generated_rc_file(repo: Repo, gate_root: Path) -> None:
    runner = Recorder()
    _judge(repo, gate_root, runner)
    run_argv, _ = runner.calls[0]
    assert run_argv[run_argv.index("-p") + 1] == judged_run.BASE_PLUGIN
    assert "eng_dev_gate.pytest_plugin" not in run_argv
    assert judged_run.NO_COV_MARKER in run_argv
    rcfile = Path(run_argv[run_argv.index("--rcfile") + 1])
    assert not rcfile.is_relative_to(repo.root)
    assert not rcfile.is_relative_to(gate_root)


def test_judged_tree_report_is_made_in_the_judged_environment(repo: Repo, gate_root: Path) -> None:
    runner = Recorder()
    _judge(repo, gate_root, runner)
    json_argv, json_cwd = runner.calls[1]
    assert json_argv[:9] == [
        "uv",
        "run",
        "--project",
        str(repo.root),
        "--locked",
        "--all-packages",
        "--group",
        "dev",
        "python",
    ]
    assert json_argv[9:12] == ["-m", "coverage", "json"]
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
    assert all(call[0][0] != "uv" for call in runner.calls)
