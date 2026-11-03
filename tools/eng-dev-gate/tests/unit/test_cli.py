"""Tests of the CLI shell: exit codes (spec AC1) and the version option."""

from __future__ import annotations

import argparse
import json
from importlib.metadata import version

import pytest
from eng_dev_gate import __version__
from eng_dev_gate.cli import main
from eng_dev_gate.results import EnvironmentFaultError, ExitCode, Status, UsageError, exit_code_for

COMMANDS = [
    "check", "gate-check", "risk-floor", "test-first", "forbidden", "imports", "licenses", "ratchet",
    "secrets", "agents", "workflows", "mutation", "review", "windows-tests", "packages",
]  # fmt: skip


def test_exit_codes() -> None:
    """AC1: 0 pass or awaiting owner, 1 rule failed, 2 usage or configuration, 3 environment or tool."""
    assert int(ExitCode.OK) == 0
    assert int(ExitCode.FAILED) == 1
    assert int(ExitCode.USAGE) == 2
    assert int(ExitCode.ENVIRONMENT) == 3
    assert int(exit_code_for(Status.PASS)) == 0
    assert int(exit_code_for(Status.AWAITING_OWNER)) == 0
    assert int(exit_code_for(Status.SKIPPED)) == 0
    assert int(exit_code_for(Status.FAIL)) == 1

    def passing(_args: argparse.Namespace) -> Status:
        return Status.PASS

    def awaiting(_args: argparse.Namespace) -> Status:
        return Status.AWAITING_OWNER

    def failing(_args: argparse.Namespace) -> Status:
        return Status.FAIL

    def bad_config(_args: argparse.Namespace) -> Status:
        raise UsageError("malformed configuration")

    def broken_tool(_args: argparse.Namespace) -> Status:
        raise EnvironmentFaultError("git is missing")

    assert main(["check"], handlers={"check": passing}) == 0
    assert main(["check"], handlers={"check": awaiting}) == 0
    assert main(["check"], handlers={"check": failing}) == 1
    assert main(["check"], handlers={"check": bad_config}) == 2
    assert main(["check"], handlers={"check": broken_tool}) == 3


def test_usage_errors_exit_2() -> None:
    assert main([]) == 2
    assert main(["no-such-command"]) == 2
    assert main(["--no-such-option", "check"]) == 2
    assert main(["--format", "xml", "check"]) == 2


def test_unimplemented_command_is_not_a_pass(capsys: pytest.CaptureFixture[str]) -> None:
    """A registered command without a handler must never report success."""
    assert main(["check"]) == 2
    assert "not implemented" in capsys.readouterr().err


def test_all_spec_commands_are_registered() -> None:
    for command in COMMANDS:
        assert main([command, "--help"]) == 0


def test_version_option(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == f"eng-gate {__version__}"
    assert __version__ == version("eng-dev-gate")


def test_error_in_json_format_goes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--format", "json", "check"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["status"] == "error"


def test_run_exits_with_main_code(monkeypatch: pytest.MonkeyPatch) -> None:
    from eng_dev_gate.cli import run

    monkeypatch.setattr("sys.argv", ["eng-gate", "--version"])
    with pytest.raises(SystemExit) as stop:
        run()
    assert stop.value.code == 0


def test_python_dash_m_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr("sys.argv", ["eng-gate", "no-such-command"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("eng_dev_gate", run_name="__main__")
    assert stop.value.code == 2
