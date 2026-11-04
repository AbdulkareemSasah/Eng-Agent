"""The ``imports`` check (spec 4.10): layers, public modules, declared dependencies, Sasaah, third party, cycles."""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from importlib.metadata import packages_distributions
from pathlib import Path

from eng_dev_gate.config import load_package_config
from eng_dev_gate.report import CommandResult, Finding, Severity, StepResult, render
from eng_dev_gate.results import Status, UsageError
from eng_dev_gate.workspace import Member, discover_members

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_DYNAMIC = {"import_module", "__import__"}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class _Pkg:
    member: Member
    layer: int | str
    names: tuple[str, ...]
    public: frozenset[str]
    declared: frozenset[str]


def _load(member: Member) -> _Pkg:
    pyproject = member.directory / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise UsageError(f"cannot read {pyproject}: {error}") from error
    config = load_package_config(pyproject)
    requirements = list(data.get("project", {}).get("dependencies", []))
    for group in data.get("dependency-groups", {}).values():
        requirements += [r for r in group if isinstance(r, str)]
    declared = frozenset(_norm(m.group()) for r in requirements if (m := _NAME.match(r)))
    return _Pkg(member, config.layer, tuple(config.import_names), frozenset(config.public_modules), declared)


def _calls(node: ast.Call) -> str | None:
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
    arg = node.args[0] if node.args else None
    if name in _DYNAMIC and isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _imports(tree: ast.AST) -> Iterator[tuple[str, int, list[str]]]:
    """Yield ``(module, line, from-imported names)`` for each absolute import, including dynamic literal ones."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno, []
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module, node.lineno, [a.name for a in node.names]
        elif isinstance(node, ast.Call) and (literal := _calls(node)):
            yield literal, node.lineno, []


def _resolves(pkg: _Pkg, dotted: str) -> bool:
    """True when ``dotted`` is a module or package in the sources of ``pkg`` (resolved by the filesystem)."""
    base = pkg.member.directory / "src" / Path(*dotted.split("."))
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def _public(pkg: _Pkg, module: str, names: list[str]) -> bool:
    targets = [f"{module}.{n}" for n in names if _resolves(pkg, f"{module}.{n}")] or [module]
    return all(t in pkg.public and not any(p.startswith("_") for p in t.split(".")) for t in targets)


def _layer_ok(importer: _Pkg, other: _Pkg) -> bool:
    """IM001 (03 section 3 item 2). Product packages are outside the layer order (spec 4.10, Q9)."""
    if "tool" in (importer.layer, other.layer) or importer.layer == 1:
        return False
    if not isinstance(importer.layer, int) or not isinstance(other.layer, int):
        return True
    if other.layer < importer.layer:
        return True
    return importer.layer == other.layer == 3 and _norm(other.member.name) in importer.declared


def _file_findings(pkg: _Pkg, path: str, tree: ast.AST, world: dict[str, _Pkg], local: set[str]) -> list[Finding]:
    found: list[Finding] = []
    dists = packages_distributions()

    def add(code: str, line: int, message: str) -> None:
        found.append(Finding(code=code, severity=Severity.ERROR, path=path, line=line, message=message))

    for module, line, names in _imports(tree):
        top = module.split(".")[0]
        if top.lower().startswith("sasaah"):
            add("IM004", line, f"import of {module!r}: no import may start with 'sasaah'")
        elif top in world and world[top] is not pkg:
            other = world[top]
            if not _layer_ok(pkg, other):
                add(
                    "IM001",
                    line,
                    f"{pkg.member.name} (layer {pkg.layer}) must not import {other.member.name} (layer {other.layer})",
                )
            if not _public(other, module, names):
                add("IM002", line, f"{module!r} is not in public_modules of {other.member.name}")
            if _norm(other.member.name) not in pkg.declared:
                add(
                    "IM003", line, f"{other.member.name} is imported but not a declared dependency of {pkg.member.name}"
                )
        elif top in world or top in sys.stdlib_module_names or top in local or top == "__future__":
            continue
        elif not {_norm(d) for d in dists.get(top, [])} & pkg.declared:
            add("IM006", line, f"{top!r} does not belong to a distribution declared by {pkg.member.name}")
    return found


def _cycles(pkgs: list[_Pkg]) -> list[Finding]:
    by_name = {_norm(p.member.name): p for p in pkgs}
    edges = {n: sorted(d for d in p.declared if d in by_name) for n, p in by_name.items()}

    def reach(start: str) -> set[str]:
        seen: set[str] = set()
        todo = list(edges[start])
        while todo:
            node = todo.pop()
            if node not in seen:
                seen.add(node)
                todo += edges[node]
        return seen

    reached = {n: reach(n) for n in edges}
    groups = {frozenset(m for m in reached[n] if n in reached[m]) for n in edges if n in reached[n]}
    return [
        Finding(code="IM005", severity=Severity.ERROR, path=by_name[min(g)].member.path,
                message=f"dependency cycle between {', '.join(sorted(by_name[n].member.name for n in g))}")
        for g in sorted(groups, key=sorted)
    ]  # fmt: skip


def check_workspace(root: Path, only: str | None = None) -> list[Finding]:
    """Check every member of the workspace at ``root`` and return the IM findings.

    Args:
        root: the workspace root.
        only: report only findings of this member name (IM005 is kept when the member's name appears in the cycle).

    Raises:
        UsageError: unreadable workspace or member, or ``only`` names no member.
        ConfigError: CF001 or CF006, a member has no valid ``[tool.eng-gate]``.
    """
    pkgs = [_load(m) for m in discover_members(root)]
    if only is not None and only not in {p.member.name for p in pkgs}:
        raise UsageError(f"no workspace member named {only!r}")
    world = {n: p for p in pkgs for n in p.names}
    findings: list[Finding] = []
    for pkg in pkgs:
        if only not in (None, pkg.member.name):
            continue
        local = {p.name.removesuffix(".py") for d in ("src", "tests") for p in (pkg.member.directory / d).glob("*")}
        for folder in ("src", "tests"):
            for file in sorted((pkg.member.directory / folder).rglob("*.py")):
                try:
                    tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
                except (OSError, SyntaxError, UnicodeDecodeError) as error:
                    raise UsageError(f"cannot parse {file}: {error}") from error
                path = file.relative_to(root).as_posix()
                findings += _file_findings(pkg, path, tree, world, local)
    return findings + [f for f in _cycles(pkgs) if only is None or only in f.message]


def handle(args: argparse.Namespace) -> Status:
    """The ``imports`` command: print the result and return its status (``--package`` limits the report)."""
    context = args.gate_context
    result = CommandResult(
        command="imports",
        mode=context.config.mode.value,
        steps=[StepResult(name="imports", findings=check_workspace(context.root, args.package))],
    )
    result = context.with_findings(result)
    render(result, args.format, sys.stdout, os.environ)
    status: Status = result.status
    return status
