"""The ``ToolRunner`` port and its subprocess adapter (spec 4.1): ruff, mypy and uv run without a shell."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from eng_dev_gate.results import EnvironmentFaultError

TOOL_TIMEOUT_SECONDS = 7200  # one tool call, as limits.mutation_run_seconds (T42); a hung tool is an environment fault


class ToolResult(BaseModel):
    """Exit code and merged stdout and stderr of a finished tool."""

    model_config = ConfigDict(frozen=True)

    exit_code: int
    output: str


class ToolTimeoutError(EnvironmentFaultError):
    """A tool ran longer than the bound that applied to the call."""


class ToolRunner(Protocol):
    """Runs an external tool."""

    def run(self, argv: Sequence[str], cwd: Path, *, timeout_seconds: float | None = None) -> ToolResult:
        """Run ``argv`` in ``cwd``; ``timeout_seconds`` (s) replaces the runner's own bound for this call.

        Raises:
            EnvironmentFaultError: the tool is missing; ``ToolTimeoutError`` if it times out.
        """
        ...


def python_module(module: str, *args: str) -> list[str]:
    """Return the argv that runs ``module`` with the interpreter of the gate (``python -m <module>``)."""
    return [sys.executable, "-m", module, *args]


class SubprocessToolRunner:
    """``ToolRunner`` over ``subprocess.run`` (no shell); ``timeout_seconds`` bounds each call."""

    def __init__(self, timeout_seconds: float = TOOL_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout_seconds

    def run(self, argv: Sequence[str], cwd: Path, *, timeout_seconds: float | None = None) -> ToolResult:
        """Run ``argv`` in ``cwd``; ``timeout_seconds`` (s), when given, replaces the bound of the runner.

        Raises:
            ToolTimeoutError: the call ran past the bound that applied.
            EnvironmentFaultError: the executable is missing or cannot start.
        """
        bound = self._timeout if timeout_seconds is None else timeout_seconds
        try:
            done = subprocess.run(  # noqa: S603  # B-034: no shell; the arguments are a list
                list(argv),
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=bound,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ToolTimeoutError(f"{argv[0]} timed out after {bound} s") from error
        except OSError as error:
            raise EnvironmentFaultError(f"cannot run {argv[0]}: {error}") from error
        return ToolResult(exit_code=done.returncode, output=done.stdout + done.stderr)
