"""Engine of the ``forbidden`` check (spec 4.8): the policy, parsed files, rule shape, scope and scanning.

A rule is a function of a parsed file and the policy. The engine decides which files a rule sees: ``src/`` of every
member for a ``src`` rule; ``tests/`` and every ``conftest.py`` for a ``tests`` rule; never spike files.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator

from eng_dev_gate.config import ConfigError, load_package_config
from eng_dev_gate.globs import matches_any
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import UsageError
from eng_dev_gate.workspace import Member

Name = Annotated[str, StringConstraints(min_length=1)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EscapeHatch(_Model):
    """FB001 policy: exact ``names`` and ``patterns`` (regexes that must fully match a function or class name)."""

    names: list[Name]
    patterns: list[Name]

    @field_validator("patterns")
    @classmethod
    def _compile(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"invalid pattern {pattern!r}: {error}") from error
        return patterns

    def matches_pattern(self, name: str) -> bool:
        """Return whether ``name`` fully matches one of the patterns."""
        return any(re.fullmatch(pattern, name) for pattern in self.patterns)


class HostSdk(_Model):
    """FB003 policy: top-level ``modules`` of the host program SDKs."""

    modules: list[Name]


class Cited(_Model):
    """FB005 form A1 policy: names of the callables that carry a cited value."""

    callables: list[Name]


class Versioned(_Model):
    """FB005 form A4 policy: names of the callables whose ``version=`` keyword is an integer identity (spec 4.8)."""

    callables: list[Name]


class RationalePolicy(_Model):
    """FB006 policy: names of the types that already forbid digits."""

    types: list[Name]


class ForbiddenConfig(_Model):
    """The whole ``.gate/forbidden.yml``; unknown keys are rejected and no list may be left out."""

    escape_hatch: EscapeHatch
    host_sdk: HostSdk
    io_modules: list[Name]
    cited: Cited
    versioned: Versioned
    rationale_policy: RationalePolicy = Field(alias="rationale")  # not named `rationale`: FB006 would flag it


@dataclass(frozen=True)
class ModuleGlobs:
    """The module globs of ``[tool.eng-gate]`` (relative to the package) that select where FB004 and FB005 apply."""

    check: tuple[str, ...] = ()
    calc: tuple[str, ...] = ()
    block: tuple[str, ...] = ()
    rule: tuple[str, ...] = ()

    def covers(self, local: str, *kinds: Literal["check", "calc", "block", "rule"]) -> bool:
        """Return whether ``local`` (relative to its package) matches a glob of one of the module ``kinds``."""
        return any(matches_any(local, getattr(self, kind)) for kind in kinds)


def parse_config(text: str, source: str) -> ForbiddenConfig:
    """Parse the text of a ``forbidden.yml``; ``source`` names it in errors.

    Raises:
        UsageError: the text is not YAML or does not fit the policy (exit 2).
    """
    try:
        return ForbiddenConfig.model_validate(yaml.safe_load(text))
    except yaml.YAMLError as error:
        raise UsageError(f"cannot read {source}: {error}") from error
    except ValidationError as error:
        raise UsageError(f"invalid {source}: {error}") from error


NO_MODULES = ModuleGlobs()  # a package without module globs


def _resolve(aliases: dict[str, str], node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([aliases.get(node.id, node.id), *reversed(parts)]).removeprefix("builtins.")


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Map local names to the dotted names they stand for: imports first, then ``name = dotted.name`` assignments."""
    aliases: dict[str, str] = {}
    nodes = list(ast.walk(tree))
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            aliases.update({a.asname or a.name: f"{node.module}.{a.name}" for a in node.names})
    for node in nodes:
        match node:
            case ast.Assign(targets=[ast.Name(id=name)], value=value) if target := _resolve(aliases, value):
                aliases[name] = target
    return aliases


@dataclass(frozen=True)
class Unit:
    """A parsed file: ``path`` (shown, relative to the workspace root), ``local`` (relative to its package)."""

    path: str
    local: str
    tree: ast.Module
    aliases: dict[str, str]
    modules: ModuleGlobs = NO_MODULES

    @property
    def in_host(self) -> bool:
        """Whether a directory below ``src`` is named ``host`` (FB003)."""
        return "host" in PurePosixPath(self.local).parts[1:-1]

    def qualname(self, node: ast.expr) -> str | None:
        """Return the dotted name ``node`` stands for with imports and simple aliases resolved, or None."""
        return _resolve(self.aliases, node)

    def finding(self, code: str, node: ast.AST, message: str) -> Finding:
        """Return the error ``code`` at the line of ``node``."""
        return Finding(
            code=code, severity=Severity.ERROR, path=self.path, line=getattr(node, "lineno", 1), message=message
        )


@dataclass(frozen=True)
class Rule:
    """A rule: ``code``, the ``scope`` of files it sees and ``check``, which returns its findings for one file."""

    code: str
    scope: Literal["src", "tests"]
    check: Callable[[Unit, ForbiddenConfig], list[Finding]]


def scan_file(
    path: str,
    local: str,
    data: bytes,
    config: ForbiddenConfig,
    rules: Sequence[Rule],
    modules: ModuleGlobs = NO_MODULES,
) -> list[Finding]:
    """Parse ``data`` and run ``rules`` on it, given the ``modules`` globs of its package; findings are ordered by line.

    A file that does not parse gives one FB000 finding and no other.
    """
    try:
        tree = ast.parse(data, filename=path)
    except (SyntaxError, ValueError) as error:
        line = getattr(error, "lineno", None) or 1
        return [
            Finding(code="FB000", severity=Severity.ERROR, path=path, line=line, message=f"does not parse: {error}")
        ]
    unit = Unit(path, local, tree, _aliases(tree), modules)
    return sorted((f for rule in rules for f in rule.check(unit, config)), key=lambda f: (f.line or 0, f.code))


def _module_globs(pyproject: Path) -> ModuleGlobs:
    try:
        table = load_package_config(pyproject)
    except ConfigError as error:
        if error.code == "CF006":
            return NO_MODULES
        raise
    return ModuleGlobs(
        tuple(table.check_modules), tuple(table.calc_modules), tuple(table.block_modules), tuple(table.rule_modules)
    )


def _python_files(directory: Path, pattern: str, base: Path) -> list[Path]:
    return [p for p in directory.rglob(pattern) if not any(part.startswith(".") for part in p.relative_to(base).parts)]


def scan_member(
    root: Path, member: Member, config: ForbiddenConfig, rules: Sequence[Rule], spike_globs: Sequence[str]
) -> list[Finding]:
    """Run ``rules`` on the files of ``member`` that are in the scope of each rule (spike files are never scanned).

    Raises:
        UsageError: a file cannot be read.
        ConfigError: the ``[tool.eng-gate]`` table of the member is invalid (CF001); a missing table is CF006 of
            the ``config`` step and gives no module globs here.
    """
    base = member.directory
    modules = _module_globs(base / "pyproject.toml")
    scoped = {
        "src": _python_files(base / "src", "*.py", base),
        "tests": [*_python_files(base / "tests", "*.py", base), *_python_files(base, "conftest.py", base)],
    }
    wanted: dict[Path, list[Rule]] = {}
    for scope, files in scoped.items():
        for path in files:
            wanted.setdefault(path, []).extend(r for r in rules if r.scope == scope and r not in wanted.get(path, []))
    findings: list[Finding] = []
    for path in sorted(wanted):
        shown = path.relative_to(root).as_posix()
        if not wanted[path] or matches_any(shown, spike_globs):
            continue
        try:
            data = path.read_bytes()
        except OSError as error:
            raise UsageError(f"cannot read {path}: {error}") from error
        findings.extend(scan_file(shown, path.relative_to(base).as_posix(), data, config, wanted[path], modules))
    return findings
