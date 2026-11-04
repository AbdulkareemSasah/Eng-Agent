"""Rules FB001, FB002, FB003 and FB007 of the ``forbidden`` check (spec 4.8); the names come from the policy file."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from eng_dev_gate.checks.forbidden.engine import ForbiddenConfig, Rule, Unit
from eng_dev_gate.report import Finding

# FB002: calls of these dotted names execute dynamic code (spec 4.8); ``shell=True`` is checked separately.
DYNAMIC_CALLS = frozenset(
    {"eval", "exec", "compile", "__import__", "os.system", "os.popen", "runpy.run_module", "runpy.run_path"}
)
Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _calls(unit: Unit) -> Iterator[tuple[ast.Call, str | None]]:
    for node in ast.walk(unit.tree):
        if isinstance(node, ast.Call):
            yield node, unit.qualname(node.func)


def _identifiers(node: ast.AST) -> list[str]:
    """Return the identifiers ``node`` names: variables, attributes, parameters, keywords, imports, definitions."""
    match node:
        case ast.Name(id=name) | ast.Attribute(attr=name) | ast.arg(arg=name) | ast.keyword(arg=str() as name):
            return [name]
        case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name) | ast.ClassDef(name=name):
            return [name]
        case ast.alias(name=name, asname=asname):
            return [*name.split("."), *([asname] if asname else [])]
    return []


def _docstrings(tree: ast.Module) -> set[int]:
    """Return the ids of the nodes that are docstrings: they are documentation, not code."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | Definition) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def fb001(unit: Unit, config: ForbiddenConfig) -> list[Finding]:
    """FB001: a string, identifier or attribute equal to an escape-hatch name, or a definition named like one."""
    hatch = config.escape_hatch
    names = set(hatch.names)
    docstrings = _docstrings(unit.tree)
    found: list[Finding] = []
    for node in ast.walk(unit.tree):
        text = [node.value] if isinstance(node, ast.Constant) and isinstance(node.value, str) else _identifiers(node)
        if id(node) in docstrings:
            continue
        if hit := names.intersection(text):
            found.append(unit.finding("FB001", node, f"escape-hatch name {sorted(hit)[0]!r}"))
        elif isinstance(node, Definition) and hatch.matches_pattern(node.name):
            found.append(unit.finding("FB001", node, f"{node.name!r} matches an escape-hatch pattern"))
    return found


def fb002(unit: Unit, _config: ForbiddenConfig) -> list[Finding]:
    """FB002: a call in ``DYNAMIC_CALLS``, or ``shell=True``."""
    found: list[Finding] = []
    for call, name in _calls(unit):
        shell = any(
            k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in call.keywords
        )
        if name in DYNAMIC_CALLS or shell:
            found.append(unit.finding("FB002", call, f"dynamic code execution: {name or 'call'} (shell={shell})"))
    return found


def fb003(unit: Unit, config: ForbiddenConfig) -> list[Finding]:
    """FB003: an import of a host SDK module, or ``clr.AddReference``, outside a ``host`` directory."""
    if unit.in_host:
        return []
    modules = set(config.host_sdk.modules)
    found: list[Finding] = []
    for node in ast.walk(unit.tree):
        if isinstance(node, ast.Import):
            hit = any(alias.name.split(".")[0] in modules for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            hit = not node.level and (node.module or "").split(".")[0] in modules
        else:
            hit = isinstance(node, ast.Call) and unit.qualname(node.func) == "clr.AddReference"
        if hit:
            found.append(unit.finding("FB003", node, "host SDK use outside a host directory"))
    return found


def fb007(unit: Unit, _config: ForbiddenConfig) -> list[Finding]:
    """FB007: a call of the builtin ``print``, also through an alias."""
    return [
        unit.finding("FB007", call, "print call: use the logger or an injected stream")
        for call, name in _calls(unit)
        if name == "print"
    ]


RULES_A: tuple[Rule, ...] = (
    Rule("FB001", "src", fb001),
    Rule("FB002", "src", fb002),
    Rule("FB003", "src", fb003),
    Rule("FB007", "src", fb007),
)
