"""Tests of the entry point that runs coverage and pytest inside the judged tree's environment (B-059)."""

from __future__ import annotations

import ast
import runpy
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from eng_dev_gate import judged_run, pytest_plugin


@pytest.fixture(autouse=True)
def _restore_import_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """``main`` edits ``sys.path`` and registers a module; leave both as the session had them."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    yield
    sys.modules.pop(judged_run.BASE_PLUGIN, None)


def test_base_plugin_is_loaded_from_the_base_file_under_its_own_name(tmp_path: Path) -> None:
    """A package in the judged environment named like the gate's cannot stand in for the base plugin."""
    fake = tmp_path / "eng_dev_gate"
    fake.mkdir()
    (fake / "__init__.py").write_text("", encoding="utf-8")
    (fake / "pytest_plugin.py").write_text("FAKE = True\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    module = judged_run.load_base_plugin()
    assert sys.modules[judged_run.BASE_PLUGIN] is module
    assert Path(module.__file__ or "").resolve() == Path(pytest_plugin.__file__ or "").resolve()
    assert module.DESELECTED_EXIT_CODE == pytest_plugin.DESELECTED_EXIT_CODE


@pytest.mark.parametrize("installed", [True, False])
def test_no_cov_marker_is_resolved_in_the_judged_environment(installed: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(judged_run, "_pytest_cov_installed", lambda: installed)
    resolved = judged_run.resolve_arguments(["run", "-m", "pytest", judged_run.NO_COV_MARKER, "tests"])
    assert resolved == ["run", "-m", "pytest", *(["--no-cov"] if installed else []), "tests"]


def _main(argv: Sequence[str], monkeypatch: pytest.MonkeyPatch, status: int = 0) -> tuple[int, list[list[str]]]:
    import coverage.cmdline

    seen: list[list[str]] = []

    def fake(args: list[str] | None = None) -> int:
        seen.append(list(args or []))
        return status

    monkeypatch.setattr(coverage.cmdline, "main", fake)
    return judged_run.main(argv), seen


def test_main_hands_the_arguments_to_coverage_and_returns_its_status(monkeypatch: pytest.MonkeyPatch) -> None:
    code, seen = _main(["run", "-m", "pytest", "-p", judged_run.BASE_PLUGIN], monkeypatch, status=7)
    assert (code, seen) == (7, [["run", "-m", "pytest", "-p", judged_run.BASE_PLUGIN]])
    assert judged_run.BASE_PLUGIN in sys.modules


def test_main_puts_the_working_directory_first_in_place_of_the_script_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script_dir = str(Path(judged_run.__file__).resolve().parent)
    monkeypatch.setattr(sys, "path", [script_dir, "elsewhere"])
    monkeypatch.chdir(tmp_path)
    _main(["run"], monkeypatch)
    assert sys.path[0] == str(tmp_path)
    assert script_dir not in sys.path


def test_main_reports_a_missing_tool_as_exit_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "coverage", None)  # makes ``import coverage`` raise ImportError
    monkeypatch.setitem(sys.modules, "coverage.cmdline", None)
    assert judged_run.main(["run"]) == 2
    assert "judged environment" in capsys.readouterr().err


def test_script_entry_point_exits_with_the_status(monkeypatch: pytest.MonkeyPatch) -> None:
    import coverage.cmdline

    monkeypatch.setattr(coverage.cmdline, "main", lambda args=None: 3)
    monkeypatch.setattr(sys, "argv", ["judged_run.py", "run"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(Path(judged_run.__file__)), run_name="__main__")
    assert stopped.value.code == 3


def test_base_plugin_imports_nothing_from_the_gate_package() -> None:
    """It runs in the judged environment, where ``eng_dev_gate`` may be the pull request's copy: any import of the
    gate package from the plugin would resolve to that copy and let a pull request replace part of the plugin."""
    tree = ast.parse(Path(pytest_plugin.__file__ or "").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import reaches the package of the judged tree"
            imported.add(node.module or "")
    assert not {name for name in imported if name.split(".")[0] == "eng_dev_gate"}
