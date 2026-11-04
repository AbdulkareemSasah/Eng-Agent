"""The ``lock``, ``format``, ``lint`` and ``types`` steps (spec 4.12): external tools with explicit configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import EnvironmentFaultError, UsageError
from eng_dev_gate.toolrun import python_module

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

OUTPUT_LINES = 20  # first lines of tool output quoted in ST001 (spec 4.12); presentation only


def _fail_or_fault(ctx: StepContext, step: str, tool: str, argv: list[str], cwd: Path) -> list[Finding]:
    result = ctx.runner.run(argv, cwd)
    if result.exit_code == 0:
        return []
    if result.exit_code != 1:  # ruff, mypy and uv exit 1 for a finding; anything else means the tool itself failed
        raise EnvironmentFaultError(f"{step}: {tool} exited {result.exit_code}: {result.output[:500]}")
    head = " | ".join(result.output.splitlines()[:OUTPUT_LINES])
    path = ctx.member.path if ctx.member else None
    return [Finding(code="ST001", severity=Severity.ERROR, path=path, message=f"{step}: {tool} exited 1: {head}")]


def _config_dir(ctx: StepContext, table: str) -> Path:
    """Directory of the configuration file: the member's own ``pyproject.toml`` if it has ``[tool.<table>]``."""
    assert ctx.member is not None  # noqa: S101 - package steps always have a member
    path = ctx.member.directory / "pyproject.toml"
    try:
        tools = tomllib.loads(path.read_text(encoding="utf-8")).get("tool", {})
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise UsageError(f"cannot read {path}: {error}") from error
    return ctx.member.directory if table in tools else ctx.gate_root


def lock(ctx: StepContext) -> list[Finding]:
    """``uv lock --check`` at the workspace root: ST001 when ``uv.lock`` is stale."""
    return _fail_or_fault(ctx, "lock", "uv", ["uv", "lock", "--check"], ctx.root)


def format_(ctx: StepContext) -> list[Finding]:
    """``ruff format --check`` on the package."""
    assert ctx.member is not None  # noqa: S101
    cwd = _config_dir(ctx, "ruff")
    argv = python_module("ruff", "format", "--check", "--config", "pyproject.toml", str(ctx.member.directory))
    return _fail_or_fault(ctx, "format", "ruff", argv, cwd)


def lint(ctx: StepContext) -> list[Finding]:
    """``ruff check`` on the package with the baseline rule set (spec 4.12)."""
    assert ctx.member is not None  # noqa: S101
    cwd = _config_dir(ctx, "ruff")
    argv = python_module("ruff", "check", "--config", "pyproject.toml", str(ctx.member.directory))
    return _fail_or_fault(ctx, "lint", "ruff", argv, cwd)


def types(ctx: StepContext) -> list[Finding]:
    """``mypy --strict`` on ``src/`` and ``tests/`` of the package (those that exist)."""
    assert ctx.member is not None  # noqa: S101
    cwd = _config_dir(ctx, "mypy")
    folders = [str(ctx.member.directory / d) for d in ("src", "tests") if (ctx.member.directory / d).is_dir()]
    argv = python_module("mypy", "--strict", "--config-file", "pyproject.toml", *folders)
    return _fail_or_fault(ctx, "types", "mypy", argv, cwd)
