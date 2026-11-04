"""The ``ToolRunner`` port and its subprocess adapter (spec 4.1): ruff, mypy and uv run without a shell."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from eng_dev_gate.results import EnvironmentFaultError

TOOL_TIMEOUT_SECONDS = 900  # upper bound for one tool call; a hung tool is an environment fault, not a rule result


class ToolResult(BaseModel):
    """Exit code and merged stdout and stderr of a finished tool."""

    model_config = ConfigDict(frozen=True)

    exit_code: int
    output: str


class ToolRunner(Protocol):
    """Runs an external tool."""

    def run(self, argv: Sequence[str], cwd: Path) -> ToolResult:
        """Run ``argv`` in ``cwd``; raise ``EnvironmentFaultError`` if the tool is missing or times out."""
        ...


def python_module(module: str, *args: str) -> list[str]:
    """Return the argv that runs ``module`` with the interpreter of the gate (``python -m <module>``)."""
    return [sys.executable, "-m", module, *args]


class SubprocessToolRunner:
    """``ToolRunner`` over ``subprocess.run`` (no shell); ``timeout_seconds`` bounds each call."""

    def __init__(self, timeout_seconds: float = TOOL_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout_seconds

    def run(self, argv: Sequence[str], cwd: Path) -> ToolResult:
        """Run ``argv`` in ``cwd``.

        Raises:
            EnvironmentFaultError: the executable is missing, cannot start, or the call timed out.
        """
        try:
            done = subprocess.run(  # noqa: S603
                list(argv),
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise EnvironmentFaultError(f"{argv[0]} timed out after {self._timeout} s") from error
        except OSError as error:
            raise EnvironmentFaultError(f"cannot run {argv[0]}: {error}") from error
        return ToolResult(exit_code=done.returncode, output=done.stdout + done.stderr)
