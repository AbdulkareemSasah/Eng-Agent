"""The ``lock``, ``format``, ``lint`` and ``types`` steps (spec 4.12): external tools with explicit configuration."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import EnvironmentFaultError, UsageError
from eng_dev_gate.toolrun import python_module

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

OUTPUT_LINES = 20  # first lines of tool output quoted in ST001 (spec 4.12); presentation only
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_REQUIRES_PYTHON_MINIMUM = re.compile(r">=\s*(\d+)\.(\d+)")


def _fail_or_fault(ctx: StepContext, step: str, tool: str, argv: list[str], cwd: Path) -> list[Finding]:
    result = ctx.runner.run(argv, cwd)
    if result.exit_code == 0:
        return []
    if result.exit_code != 1:  # ruff, mypy and uv exit 1 for a finding; anything else means the tool itself failed
        raise EnvironmentFaultError(f"{step}: {tool} exited {result.exit_code}: {result.output[:500]}")
    head = " | ".join(result.output.splitlines()[:OUTPUT_LINES])
    path = ctx.member.path if ctx.member else None
    return [Finding(code="ST001", severity=Severity.ERROR, path=path, message=f"{step}: {tool} exited 1: {head}")]


def _read_pyproject(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise UsageError(f"cannot read {path}: {error}") from error


def _has_own_table(ctx: StepContext, table: str) -> bool:
    """True when the member's own ``pyproject.toml`` has ``[tool.<table>]``; it then configures the tool itself."""
    assert ctx.member is not None  # noqa: S101 - package steps always have a member
    return table in _read_pyproject(ctx.member.directory / "pyproject.toml").get("tool", {})


def _key(key: str) -> str:
    return key if _BARE_KEY.fullmatch(key) else json.dumps(key, ensure_ascii=False)


def _toml_value(value: object) -> str:
    """Serialize a value read by ``tomllib`` as an inline TOML value (the types of a ruff table)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_key(k)} = {_toml_value(v)}" for k, v in value.items()) + "}"
    raise UsageError(f"unsupported value in the base ruff configuration: {value!r}")


def _base_ruff_options(gate_root: Path) -> list[str]:
    """The ruff policy of the base commit as ``--config key=value`` options (spec 4.16).

    ruff anchors the relative patterns of a configuration *file* (``per-file-ignores``, ``extend-exclude``, ``src``)
    at the directory of that file, which is the base checkout and holds none of the judged files. Options given on the
    command line are anchored at the working directory instead, so the policy is passed as options with ``--isolated``
    (no file is discovered, the head tree cannot add to it) and the step runs in the judged tree. ``extend`` is
    refused: it would read a file of the judged tree. A ``target-version`` that the table leaves out is derived from
    ``requires-python`` as ruff does when it reads the file itself.
    """
    pyproject = _read_pyproject(gate_root / "pyproject.toml")
    table = dict(pyproject.get("tool", {}).get("ruff", {}))
    if "extend" in table:
        raise UsageError(f"{gate_root / 'pyproject.toml'}: [tool.ruff] extend is not allowed in the base policy")
    if "target-version" not in table:
        match = _REQUIRES_PYTHON_MINIMUM.search(str(pyproject.get("project", {}).get("requires-python", "")))
        if match:
            table["target-version"] = f"py{match.group(1)}{match.group(2)}"
    return [arg for key, value in table.items() for arg in ("--config", f"{_key(key)} = {_toml_value(value)}")]


def _ruff(ctx: StepContext, step: str, *args: str) -> list[Finding]:
    assert ctx.member is not None  # noqa: S101
    target = str(ctx.member.directory)
    if _has_own_table(ctx, "ruff"):
        argv = python_module("ruff", *args, "--config", "pyproject.toml", target)
        return _fail_or_fault(ctx, step, "ruff", argv, ctx.member.directory)
    argv = python_module("ruff", *args, "--isolated", *_base_ruff_options(ctx.gate_root), target)
    return _fail_or_fault(ctx, step, "ruff", argv, ctx.root)


def lock(ctx: StepContext) -> list[Finding]:
    """``uv lock --check`` at the workspace root: ST001 when ``uv.lock`` is stale."""
    return _fail_or_fault(ctx, "lock", "uv", ["uv", "lock", "--check"], ctx.root)


def format_(ctx: StepContext) -> list[Finding]:
    """``ruff format --check`` on the package."""
    return _ruff(ctx, "format", "format", "--check")


def lint(ctx: StepContext) -> list[Finding]:
    """``ruff check`` on the package with the baseline rule set (spec 4.12)."""
    return _ruff(ctx, "lint", "check")


def types(ctx: StepContext) -> list[Finding]:
    """``mypy --strict`` on ``src/`` and ``tests/`` of the package (those that exist).

    mypy resolves ``mypy_path``, ``files`` and ``exclude`` against the working directory and has no per-file anchor, so
    the base configuration is given by absolute path and the tool runs in the judged tree (spec 4.16).
    """
    assert ctx.member is not None  # noqa: S101
    folders = [str(ctx.member.directory / d) for d in ("src", "tests") if (ctx.member.directory / d).is_dir()]
    if _has_own_table(ctx, "mypy"):
        argv = python_module("mypy", "--strict", "--config-file", "pyproject.toml", *folders)
        return _fail_or_fault(ctx, "types", "mypy", argv, ctx.member.directory)
    argv = python_module("mypy", "--strict", "--config-file", str(ctx.gate_root / "pyproject.toml"), *folders)
    return _fail_or_fault(ctx, "types", "mypy", argv, ctx.root)
