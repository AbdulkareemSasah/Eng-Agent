"""Tests of the subprocess tool runner (spec 4.1 ToolRunner)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from eng_dev_gate import toolrun
from eng_dev_gate.results import EnvironmentFaultError
from eng_dev_gate.toolrun import SubprocessToolRunner, python_module


def test_exit_code_and_merged_output(tmp_path: Path) -> None:
    code = "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"
    result = SubprocessToolRunner().run([sys.executable, "-c", code], tmp_path)
    assert result.exit_code == 3
    assert "out" in result.output
    assert "err" in result.output


def test_missing_executable_is_environment_fault(tmp_path: Path) -> None:
    with pytest.raises(EnvironmentFaultError, match="no-such-tool-xyz"):
        SubprocessToolRunner().run(["no-such-tool-xyz"], tmp_path)


def test_timeout_is_environment_fault(tmp_path: Path) -> None:
    with pytest.raises(EnvironmentFaultError, match="timed out"):
        SubprocessToolRunner(timeout_seconds=1).run([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path)


def test_per_call_timeout_overrides_the_bound_of_the_runner(tmp_path: Path) -> None:
    """AC53c: ``timeout_seconds`` of one call replaces the runner's own bound and the message names it."""
    sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
    with pytest.raises(toolrun.ToolTimeoutError, match=r"timed out after 0\.5 s") as caught:
        SubprocessToolRunner(timeout_seconds=900).run(sleeper, tmp_path, timeout_seconds=0.5)
    assert isinstance(caught.value, EnvironmentFaultError)


def test_default_bound_is_the_mutation_bound() -> None:
    """T42 (amendment B-619): one tool call is bounded by the workspace mutation bound, not the former 900 s."""
    from eng_dev_gate.config.gate_config import load_gate_config

    workspace = Path(__file__).resolve().parents[4]
    assert load_gate_config(workspace).limits.mutation_run_seconds == toolrun.TOOL_TIMEOUT_SECONDS


def test_python_module_uses_current_interpreter() -> None:
    assert python_module("ruff", "check") == [sys.executable, "-m", "ruff", "check"]
