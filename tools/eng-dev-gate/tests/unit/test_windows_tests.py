"""Tests of the ``windows-tests`` command (spec 4.14, AC63): the declared paths run; none declared is a notice."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from eng_dev_gate.checks import windows_tests
from eng_dev_gate.cli import main
from eng_dev_gate.results import EnvironmentFaultError, Status
from eng_dev_gate.toolrun import ToolResult
from support.toy import GATE_YML


class Recorder:
    """ToolRunner that records each call and answers with the exit codes it was given, in order."""

    def __init__(self, *exit_codes: int) -> None:
        self.calls: list[tuple[list[str], Path]] = []
        self._codes = list(exit_codes)

    def run(self, argv: Sequence[str], cwd: Path, *, timeout_seconds: float | None = None) -> ToolResult:
        self.calls.append((list(argv), cwd))
        return ToolResult(exit_code=self._codes.pop(0) if self._codes else 0, output="1 failed\n")


def _workspace(tmp_path: Path, declared: dict[str, list[str] | None]) -> Path:
    """A toy workspace with one member per name; ``None`` declares no ``windows_tests`` key."""
    members = ", ".join(f'"pkgs/{n}"' for n in declared)
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "r"\nversion = "0"\n[tool.uv.workspace]\nmembers = [{members}]\n', encoding="utf-8"
    )
    (tmp_path / ".gate").mkdir()
    gate_yml = GATE_YML
    (tmp_path / ".gate" / "gate.yml").write_text(gate_yml, encoding="utf-8")
    for name, paths in declared.items():
        folder = tmp_path / "pkgs" / name
        (folder / "tests").mkdir(parents=True)
        for rel in paths or []:
            (folder / rel).parent.mkdir(parents=True, exist_ok=True)
            (folder / rel).write_text("", encoding="utf-8")
        extra = "" if paths is None else "windows_tests = [" + ", ".join(f'"{p}"' for p in paths) + "]\n"
        (folder / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0"\n[tool.eng-gate]\nprofile = "tool"\nlayer = "tool"\n'
            f'import_names = ["{name}"]\ncoverage_line = 95\ncoverage_branch = 90\n{extra}',
            encoding="utf-8",
        )
    return tmp_path


def test_declared_paths(tmp_path: Path) -> None:
    """AC63: exactly the declared paths run, per package, in the package folder; undeclared packages do not run."""
    root = _workspace(tmp_path, {"a": ["tests/test_w.py", "tests/win/test_x.py"], "b": None, "c": []})
    runner = Recorder()
    steps = windows_tests.run_windows_tests(root, runner)
    ((argv, cwd),) = runner.calls
    assert cwd == root / "pkgs" / "a"
    assert argv[-2:] == ["tests/test_w.py", "tests/win/test_x.py"]
    assert "pytest" in argv
    assert [s.name for s in steps] == ["windows-tests"]
    assert steps[0].status is Status.PASS


def test_none_declared_is_a_notice_and_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _workspace(tmp_path, {"a": None, "b": []})
    runner = Recorder()
    assert main(["--root", str(root), "windows-tests"], {"windows-tests": windows_tests.make_handler(runner)}) == 0
    assert runner.calls == []
    assert "no workspace member declares windows_tests" in capsys.readouterr().out


def test_failing_tests_fail_the_step(tmp_path: Path) -> None:
    root = _workspace(tmp_path, {"a": ["tests/test_w.py"], "b": ["tests/test_w.py"]})
    runner = Recorder(1, 0)
    steps = windows_tests.run_windows_tests(root, runner)
    assert len(runner.calls) == 2  # a failing package does not hide the next one
    assert steps[0].status is Status.FAIL
    (finding,) = steps[0].findings
    assert (finding.code, finding.path) == ("ST001", "pkgs/a")
    assert "exited 1" in finding.message


def test_declared_paths_that_collect_nothing_fail(tmp_path: Path) -> None:
    root = _workspace(tmp_path, {"a": ["tests/test_w.py"]})
    steps = windows_tests.run_windows_tests(root, Recorder(5))
    assert steps[0].status is Status.FAIL


@pytest.mark.parametrize("bad", ["../x.py", "/abs/x.py", "tests/missing.py"])
def test_invalid_or_missing_paths_fail_without_running(tmp_path: Path, bad: str) -> None:
    root = _workspace(tmp_path, {"a": ["tests/test_w.py"]})
    pyproject = root / "pkgs" / "a" / "pyproject.toml"
    pyproject.write_text(pyproject.read_text(encoding="utf-8").replace("tests/test_w.py", bad), encoding="utf-8")
    runner = Recorder()
    steps = windows_tests.run_windows_tests(root, runner)
    assert runner.calls == []
    assert steps[0].status is Status.FAIL
    assert bad in steps[0].findings[0].message


def test_tool_fault_is_an_environment_fault(tmp_path: Path) -> None:
    root = _workspace(tmp_path, {"a": ["tests/test_w.py"]})
    with pytest.raises(EnvironmentFaultError):
        windows_tests.run_windows_tests(root, Recorder(4))
