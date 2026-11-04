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


def _strings(value: object) -> list[str] | None:
    """A string or a list of strings as a list; ``None`` when the value has any other shape."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    return None


def _sub(table: Table, key: str, label: str, problems: list[str]) -> Table:
    """The sub-table ``key`` (``{}`` when absent); a value of any other type is reported and read as empty."""
    value = table.get(key, {})
    if isinstance(value, dict):
        return value
    problems.append(f"{label} must be a table")
    return {}


def _ruff(table: Table) -> list[str]:
    problems = [f"[tool.ruff] {k} is not allowed" for k in sorted(table.keys() - RUFF_KEYS)]
    if table.get("exclude", ["spikes"]) != ["spikes"]:
        problems.append("[tool.ruff] exclude may only be ['spikes']")
    lint = _sub(table, "lint", "[tool.ruff.lint]", problems)
    problems += [f"[tool.ruff.lint] {k} is not allowed" for k in sorted(lint.keys() - {"select", "per-file-ignores"})]
    select = _strings(lint.get("select", []))
    if select is None or not set(select) >= LINT_BASELINE:
        problems.append(
            "[tool.ruff.lint] select must contain the baseline families " + ", ".join(sorted(LINT_BASELINE))
        )
    for pattern, rules in _sub(lint, "per-file-ignores", "[tool.ruff.lint.per-file-ignores]", problems).items():
        if pattern not in TESTS_GLOBS or rules != ["S101"]:
            problems.append(f"[tool.ruff.lint.per-file-ignores] only tests/** with S101 is allowed, not {pattern!r}")
    return problems


def _mypy(table: Table, own: list[str]) -> list[str]:
    problems = [f"[tool.mypy] {k} is not allowed" for k in sorted(table.keys() - MYPY_KEYS)]
    if table.get("strict") is not True:
        problems.append("[tool.mypy] strict must be true")
    overrides = table.get("overrides", [])
    for override in overrides if isinstance(overrides, list) else [overrides]:
        modules = _strings(override.get("module", [])) if isinstance(override, dict) else None
        if modules is None:
            problems.append("[[tool.mypy.overrides]] must be tables whose module is a string or a list of strings")
            continue
        if set(override) != {"module", "ignore_missing_imports"} or override["ignore_missing_imports"] is not True:
            problems.append("[[tool.mypy.overrides]] may only set ignore_missing_imports = true")
        for m in modules:
            if m.startswith("*"):
                problems.append(f"[[tool.mypy.overrides]] module {m!r} is a wildcard pattern, which is not allowed")
            elif m.split(".")[0] in own:
                problems.append(f"[[tool.mypy.overrides]] module {m!r} is inside the package's own namespace")
    return problems


def _pytest(tools: Table) -> list[str]:
    """Rules for ``[tool.pytest]``: only ``ini_options`` is allowed, because pytest 9 also reads other keys."""
    label = "[tool.pytest.ini_options]"
    problems = [f"[tool.pytest] {k} is not allowed" for k in sorted(tools.keys() - {"ini_options"})]
    table = _sub(tools, "ini_options", label, problems)
    problems += [f"{label} {k} is not allowed" for k in sorted(table.keys() - PYTEST_KEYS)]
    addopts = table.get("addopts", [])
    tokens = shlex.split(addopts) if isinstance(addopts, str) else _strings(addopts)
    if tokens is None:
        problems.append(f"{label} addopts must be a string or a list of strings")
    else:
        problems += [f"{label} addopts {t!r} is not allowed" for t in tokens if t not in ADDOPTS]
    entries = _strings(table.get("filterwarnings", []))
    if entries is None:
        problems.append(f"{label} filterwarnings must be a string or a list of strings")
    else:
        problems += [
            f"{label} filterwarnings must not ignore warnings" for e in entries if e.split(":")[0].strip() == "ignore"
        ]
    return problems


def _installed() -> set[str]:
    return {d.metadata["Name"].lower().replace("_", "-") for d in importlib.metadata.distributions()}


def config(ctx: StepContext) -> list[Finding]:
    """Check the member's ``[tool.eng-gate]``, its floors and the weakening rules of spec 4.12.

    Returns:
        CF001 (invalid or unreadable table), CF002 (below the floor), CF003 (weakening tool setting), CF004
        (override file), CF005 (rerun plugin installed), CF006 (no table); never raises for these.
    """
    if ctx.member is None:
        raise ValueError("the config step runs per package and needs a member")
    path = f"{ctx.member.path}/pyproject.toml"

    def error(code: str, message: str) -> Finding:
        return Finding(code=code, severity=Severity.ERROR, path=path, message=message)

    try:
        document = tomllib.loads((ctx.member.directory / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [error("CF001", f"cannot read {path}: {exc}")]
    findings: list[Finding] = []
    problems: list[str] = []
    tools = _sub(document, "tool", "[tool]", problems)
    project = _sub(document, "project", "[project]", problems)
    name = project.get("name")
    own = [name.replace("-", "_").replace(".", "_").lower()] if isinstance(name, str) else []  # fallback namespace
    table = tools.get("eng-gate")
    if table is None:
        findings.append(error("CF006", f"{path} has no [tool.eng-gate] table"))
    elif not isinstance(table, dict):
        findings.append(error("CF001", "[tool.eng-gate] is not a table"))
    else:
        try:
            package = parse_package_config(table)
            own = [*own, *package.import_names]
            findings += check_floors(package, path)
        except ConfigError as exc:
            findings.append(error(exc.code, str(exc).removeprefix(f"{exc.code} ")))
    for key, rule in (("ruff", _ruff), ("pytest", _pytest)):
        problems += rule(_sub(tools, key, f"[tool.{key}]", problems)) if key in tools else []
    problems += _mypy(_sub(tools, "mypy", "[tool.mypy]", problems), own) if "mypy" in tools else []
    problems += [
        f"[tool.coverage.{k}] is not allowed: the gate generates the configuration"
        for k in _sub(tools, "coverage", "[tool.coverage]", problems)
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
