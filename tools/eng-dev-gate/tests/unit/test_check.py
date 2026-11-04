"""Tests of the check orchestrator (spec 4.12; AC47) with a fake tool runner."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from eng_dev_gate.checks.check import make_handler
from eng_dev_gate.checks.registry import STEP_ORDER, STEPS
from eng_dev_gate.results import EnvironmentFaultError
from eng_dev_gate.toolrun import ToolResult
from support.repo import Repo, RunResult
from support.toy import make_workspace, member_pyproject


class FakeRunner:
    """Scripted ToolRunner: ``codes`` maps a step key (lock, format, lint, types) to an exit code."""

    def __init__(self, codes: dict[str, int] | None = None, output: str = "") -> None:
        self.codes = codes or {}
        self.output = output
        self.calls: list[tuple[list[str], Path]] = []

    @staticmethod
    def key(argv: Sequence[str]) -> str:
        if argv[0] == "uv":
            return "lock"
        if "mypy" in argv:
            return "types"
        return "format" if "format" in argv else "lint"

    def run(self, argv: Sequence[str], cwd: Path) -> ToolResult:
        self.calls.append((list(argv), cwd))
        return ToolResult(exit_code=self.codes.get(self.key(argv), 0), output=self.output)


def _run(repo: Repo, runner: FakeRunner, *argv: str) -> RunResult:
    # the tests and secrets steps have their own tests (test_coverage.py, test_secrets.py)
    return repo.run(
        ["--format", "json", "check", "--skip", "tests,secrets,docs-fresh,licenses,workflows", *argv],
        {"check": make_handler(runner)},
    )


def _statuses(result: RunResult) -> dict[str, str]:
    return {s["name"]: s["status"] for s in json.loads(result.out)["steps"]}


def test_step_order_and_aggregate(repo: Repo) -> None:
    """AC47: spec order, every step reported, a failing step does not stop the others, exit code is the worst."""
    make_workspace(repo, ["a"])
    assert [s.name for s in STEPS] == [
        "lock", "config", "format", "lint", "types", "forbidden", "ratchet", "secrets", "tests",
        "docs-fresh", "licenses", "workflows",
    ]  # fmt: skip
    assert [n for n in STEP_ORDER if n in {s.name for s in STEPS}] == [s.name for s in STEPS]
    assert STEP_ORDER[:5] == ("lock", "config", "format", "lint", "types")
    assert len(STEP_ORDER) == 14
    ok = _run(repo, FakeRunner())
    assert ok.code == 0
    assert list(_statuses(ok).items()) == [
        ("lock", "pass"), ("config", "pass"), ("format", "pass"), ("lint", "pass"), ("types", "pass"),
        ("forbidden", "pass"), ("ratchet", "pass"),
    ]  # fmt: skip
    bad = _run(repo, FakeRunner({"format": 1, "types": 1}))
    assert bad.code == 1
    assert list(_statuses(bad).items()) == [
        ("lock", "pass"), ("config", "pass"), ("format", "fail"), ("lint", "pass"), ("types", "fail"),
        ("forbidden", "pass"), ("ratchet", "pass"),
    ]  # fmt: skip
    assert json.loads(bad.out)["status"] == "fail"


def test_fail_fast_stops_after_first_failure(repo: Repo) -> None:
    make_workspace(repo, ["a"])
    result = _run(repo, FakeRunner({"format": 1}), "--fail-fast")
    assert result.code == 1
    assert list(_statuses(result)) == ["lock", "config", "format"]


def test_only_and_skip(repo: Repo) -> None:
    make_workspace(repo, ["a"])
    assert list(_statuses(_run(repo, FakeRunner(), "--only", "lint", "--only", "types"))) == ["lint", "types"]
    assert list(_statuses(_run(repo, FakeRunner(), "--skip", "lock,types"))) == [
        "config", "format", "lint", "forbidden", "ratchet",
    ]  # fmt: skip
    assert _run(repo, FakeRunner(), "--only", "nonsense").code == 2


def test_st001_reports_step_tool_exit_code_and_first_lines(repo: Repo) -> None:
    make_workspace(repo, ["a"])
    output = "\n".join(f"line {i}" for i in range(100))
    result = _run(repo, FakeRunner({"lint": 1}, output))
    (finding,) = [f for s in json.loads(result.out)["steps"] if s["name"] == "lint" for f in s["findings"]]
    assert finding["code"] == "ST001"
    assert finding["severity"] == "error"
    for text in ("lint", "ruff", "exited 1", "line 0"):
        assert text in finding["message"]
    assert "line 99" not in finding["message"]


def test_tool_crash_is_an_environment_error(repo: Repo) -> None:
    """Exit codes other than 0 and 1 mean the tool itself failed: exit 3, never a rule result."""
    make_workspace(repo, ["a"])
    assert _run(repo, FakeRunner({"types": 2})).code == 3

    class Missing:
        def run(self, argv: Sequence[str], cwd: Path) -> ToolResult:
            raise EnvironmentFaultError(f"{argv[0]} is not installed")

    assert repo.run(["check"], {"check": make_handler(Missing())}).code == 3


def test_explicit_tool_configuration(repo: Repo) -> None:
    """Tools get the explicit policy of the gate root (ruff: isolated options, mypy: file) and strict mode."""
    make_workspace(repo, ["a"])
    runner = FakeRunner()
    _run(repo, runner)
    by_key = {runner.key(argv): (argv, cwd) for argv, cwd in runner.calls}
    assert by_key["lock"][0] == ["uv", "lock", "--check"]
    assert by_key["lock"][1] == repo.root
    for key in ("format", "lint"):
        argv, cwd = by_key[key]
        assert "--isolated" in argv  # no configuration file is discovered, so stray files cannot change the tool
        assert "line-length = 120" in argv  # the policy of the gate root's [tool.ruff], as options
        assert cwd == repo.root
        assert argv[-1] == str(repo.root / "pkgs" / "a")
    assert "--check" in by_key["format"][0]
    argv = by_key["types"][0]
    assert argv[argv.index("--config-file") + 1] == str(repo.root / "pyproject.toml")
    assert by_key["types"][1] == repo.root
    assert "--strict" in argv
    assert str(repo.root / "pkgs" / "a" / "src") in argv


def test_member_ruff_table_selects_member_config_and_directory(repo: Repo) -> None:
    """A member with its own [tool.ruff] is linted with its own file from its own directory (first-party detection)."""
    make_workspace(repo, ["a"])
    repo.commit({"pkgs/a/pyproject.toml": member_pyproject("a") + "[tool.ruff]\n"})
    runner = FakeRunner()
    _run(repo, runner)
    argv, cwd = next((a, c) for a, c in runner.calls if runner.key(a) == "lint")
    assert cwd == repo.root / "pkgs" / "a"
    assert argv[argv.index("--config") + 1] == "pyproject.toml"


def test_workspace_selection(repo: Repo) -> None:
    make_workspace(repo, ["a", "b"])
    both = _statuses(_run(repo, FakeRunner()))
    assert list(both) == [
        "lock", "config:a", "config:b", "format:a", "format:b", "lint:a", "lint:b", "types:a", "types:b",
        "forbidden:a", "forbidden:b", "ratchet",
    ]  # fmt: skip
    one = _statuses(_run(repo, FakeRunner(), "--package", "b"))
    assert list(one) == ["lock", "config", "format", "lint", "types", "forbidden", "ratchet"]
    assert _run(repo, FakeRunner(), "--package", "missing").code == 2
    argv = [
        "--root",
        str(repo.root / "pkgs" / "a"),
        "--format",
        "json",
        "check",
        "--skip",
        "tests,docs-fresh,licenses,workflows",
    ]
    inside = repo.run(argv, {"check": make_handler(FakeRunner())})
    assert json.loads(inside.out)["steps"][1]["name"] == "config"


def test_text_output_starts_with_mode(repo: Repo) -> None:
    make_workspace(repo, ["a"])
    result = repo.run(["check", "--skip", "tests,docs-fresh,licenses,workflows"], {"check": make_handler(FakeRunner())})
    assert result.out.splitlines()[0] == "mode: bootstrap"
