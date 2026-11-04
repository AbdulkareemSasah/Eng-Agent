"""The ``config`` step (spec 4.12): the package table, the floors and the weakening rules (CF001 to CF006)."""

from __future__ import annotations

import importlib.metadata
import shlex
import tomllib
from typing import TYPE_CHECKING, Any

from eng_dev_gate.config import ConfigError, check_floors, parse_package_config
from eng_dev_gate.report import Finding, Severity

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

Table = dict[str, Any]  # Any: TOML values are untyped data at this boundary

LINT_BASELINE = frozenset({"E", "W", "F", "I", "B", "UP", "SIM", "N", "S"})  # spec 4.12 lint baseline
RUFF_KEYS = frozenset({"line-length", "src", "exclude", "lint"})
MYPY_KEYS = frozenset({"strict", "plugins", "mypy_path", "python_version", "files", "overrides"})
PYTEST_KEYS = frozenset(
    {"testpaths", "pythonpath", "markers", "minversion", "asyncio_mode", "filterwarnings", "addopts"}
)
ADDOPTS = frozenset({"-ra", "-q", "--strict-markers", "--strict-config", "--import-mode=importlib"})  # spec 4.12
TESTS_GLOBS = frozenset({"tests/**", "**/tests/**"})
OVERRIDE_FILES = (
    "pytest.ini", "tox.ini", "setup.cfg", "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini", ".coveragerc",
)  # fmt: skip
RERUN_PLUGINS = frozenset({"pytest-rerunfailures", "flaky", "pytest-retry"})  # process/05 section 3


def _ruff(table: Table) -> list[str]:
    problems = [f"[tool.ruff] {k} is not allowed" for k in sorted(table.keys() - RUFF_KEYS)]
    if table.get("exclude", ["spikes"]) != ["spikes"]:
        problems.append("[tool.ruff] exclude may only be ['spikes']")
    lint = table.get("lint", {})
    problems += [f"[tool.ruff.lint] {k} is not allowed" for k in sorted(lint.keys() - {"select", "per-file-ignores"})]
    if not set(lint.get("select", [])) >= LINT_BASELINE:
        problems.append(
            "[tool.ruff.lint] select must contain the baseline families " + ", ".join(sorted(LINT_BASELINE))
        )
    for pattern, rules in lint.get("per-file-ignores", {}).items():
        if pattern not in TESTS_GLOBS or rules != ["S101"]:
            problems.append(f"[tool.ruff.lint.per-file-ignores] only tests/** with S101 is allowed, not {pattern!r}")
    return problems


def _mypy(table: Table, own: list[str]) -> list[str]:
    problems = [f"[tool.mypy] {k} is not allowed" for k in sorted(table.keys() - MYPY_KEYS)]
    if table.get("strict") is not True:
        problems.append("[tool.mypy] strict must be true")
    for override in table.get("overrides", []):
        modules = override.get("module", [])
        modules = [modules] if isinstance(modules, str) else modules
        if set(override) != {"module", "ignore_missing_imports"} or override["ignore_missing_imports"] is not True:
            problems.append("[[tool.mypy.overrides]] may only set ignore_missing_imports = true")
        problems += [
            f"[[tool.mypy.overrides]] module {m!r} is inside the package's own namespace"
            for m in modules
            if m.split(".")[0] in own or m.startswith("*")
        ]
    return problems


def _pytest(table: Table) -> list[str]:
    problems = [f"[tool.pytest.ini_options] {k} is not allowed" for k in sorted(table.keys() - PYTEST_KEYS)]
    addopts = table.get("addopts", [])
    tokens = shlex.split(addopts) if isinstance(addopts, str) else addopts
    problems += [f"[tool.pytest.ini_options] addopts {t!r} is not allowed" for t in tokens if t not in ADDOPTS]
    warnings = table.get("filterwarnings", [])
    for entry in [warnings] if isinstance(warnings, str) else warnings:
        if entry.split(":")[0].strip() == "ignore":
            problems.append("[tool.pytest.ini_options] filterwarnings must not ignore warnings")
    return problems


def _installed() -> set[str]:
    return {d.metadata["Name"].lower().replace("_", "-") for d in importlib.metadata.distributions()}


def config(ctx: StepContext) -> list[Finding]:
    """Check the member's ``[tool.eng-gate]``, its floors and the weakening rules of spec 4.12.

    Returns:
        CF001 (invalid or unreadable table), CF002 (below the floor), CF003 (weakening tool setting), CF004
        (override file), CF005 (rerun plugin installed), CF006 (no table); never raises for these.
    """
    assert ctx.member is not None  # noqa: S101 - package steps always have a member
    path = f"{ctx.member.path}/pyproject.toml"

    def error(code: str, message: str) -> Finding:
        return Finding(code=code, severity=Severity.ERROR, path=path, message=message)

    try:
        tools = tomllib.loads((ctx.member.directory / "pyproject.toml").read_text(encoding="utf-8")).get("tool", {})
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [error("CF001", f"cannot read {path}: {exc}")]
    findings: list[Finding] = []
    own: list[str] = []
    table = tools.get("eng-gate")
    if table is None:
        findings.append(error("CF006", f"{path} has no [tool.eng-gate] table"))
    elif not isinstance(table, dict):
        findings.append(error("CF001", "[tool.eng-gate] is not a table"))
    else:
        try:
            package = parse_package_config(table)
            own = package.import_names
            findings += check_floors(package, path)
        except ConfigError as exc:
            findings.append(error(exc.code, str(exc).removeprefix(f"{exc.code} ")))
    problems = _ruff(tools.get("ruff", {})) if "ruff" in tools else []
    problems += _mypy(tools["mypy"], own) if "mypy" in tools else []
    problems += _pytest(tools["pytest"].get("ini_options", {})) if "pytest" in tools else []
    problems += [
        f"[tool.coverage.{k}] is not allowed: the gate generates the configuration" for k in tools.get("coverage", {})
    ]
    findings += [error("CF003", p) for p in problems]
    findings += [
        error("CF004", f"{n} can change a tool's configuration")
        for n in OVERRIDE_FILES
        if (ctx.member.directory / n).exists()
    ]
    findings += [
        error("CF005", f"rerun plugin {n} is installed (process/05 section 3)")
        for n in sorted(_installed() & RERUN_PLUGINS)
    ]
    return findings
