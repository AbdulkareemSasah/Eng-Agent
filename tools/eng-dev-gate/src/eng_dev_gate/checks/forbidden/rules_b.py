"""Rules FB004, FB005, FB006 and FB008 of the ``forbidden`` check (spec 4.8); the lists come from the policy file."""

from __future__ import annotations

import ast
import itertools
import re
from collections.abc import Iterator

from eng_dev_gate.checks.forbidden.engine import ForbiddenConfig, Rule, Unit
from eng_dev_gate.report import Finding

# FB006: a rationale pattern must reject every one of these decimal digits (spec 4.8: ASCII, Arabic-Indic U+0660 to
# U+0669 and extended Arabic-Indic U+06F0 to U+06F9) and accept plain letters.
DIGITS = "0123456789" + "".join(chr(c) for c in (*range(0x660, 0x66A), *range(0x6F0, 0x6FA)))
# FB008: defining one of these hooks, or assigning one of these names, deselects tests (process/05 section 3).
HOOKS = frozenset({"pytest_collection_modifyitems", "pytest_ignore_collect", "pytest_deselected"})
IGNORE_NAMES = frozenset({"collect_ignore", "collect_ignore_glob"})


def _last(name: str | None) -> str:
    return (name or "").rsplit(".", 1)[-1]


def fb004(unit: Unit, config: ForbiddenConfig) -> list[Finding]:
    """FB004: in block and rule modules, an import of an ``io_modules`` module or a call of ``open`` or ``input``."""
    if not unit.modules.covers(unit.local, "block", "rule"):
        return []
    io = set(config.io_modules)
    found: list[Finding] = []
    for node in ast.walk(unit.tree):
        if isinstance(node, ast.Call):
            if (name := unit.qualname(node.func)) in ("open", "input"):
                found.append(unit.finding("FB004", node, f"call of {name} in a block or rule module"))
            continue
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        else:
            modules = [node.module or ""] if isinstance(node, ast.ImportFrom) and not node.level else []
        if hit := io.intersection(module.split(".")[0] for module in modules):
            found.append(unit.finding("FB004", node, f"import of {sorted(hit)[0]!r} in a block or rule module"))
    return found


def _literal(node: ast.AST) -> ast.Constant | None:
    """Return the numeric constant of ``node``, which may carry a leading minus (``bool`` is not numeric)."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        node = node.operand
    if isinstance(node, ast.Constant) and type(node.value) in (int, float, complex):
        return node
    return None


def _is_len(unit: Unit, node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and unit.qualname(node.func) == "len"


def _version_literals(unit: Unit, versioned: set[str]) -> set[int]:
    """A4: ids of integer literals given directly as ``version=`` of a callable in ``versioned`` (spec 4.8)."""
    found: set[int] = set()
    for node in ast.walk(unit.tree):
        if not (isinstance(node, ast.Call) and _last(unit.qualname(node.func)) in versioned):
            continue
        for keyword in node.keywords:
            if keyword.arg == "version" and (const := _literal(keyword.value)) and type(const.value) is int:
                found.add(id(const))
    return found


def _allowed(unit: Unit, config: ForbiddenConfig) -> set[int]:
    """Return the ids of the constants in forms A1 (cited), A2 (index), A3 (against ``len``) and A4 (version)."""
    allowed: set[int] = set()
    cited = set(config.cited.callables)
    for node in ast.walk(unit.tree):
        if isinstance(node, ast.Call) and _last(unit.qualname(node.func)) in cited:
            value = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "value"), None)
            source = (
                node.args[1]
                if len(node.args) > 1
                else next((k.value for k in node.keywords if k.arg == "source"), None)
            )
            if (
                value is not None
                and (const := _literal(value))
                and isinstance(source, ast.Constant)
                and isinstance(source.value, str)
                and source.value
            ):
                allowed.add(id(const))
        elif isinstance(node, ast.Subscript):
            slots = [node.slice.lower, node.slice.upper] if isinstance(node.slice, ast.Slice) else [node.slice]
            allowed.update(id(c) for s in slots if s and (c := _literal(s)) and type(c.value) is int)
        elif isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            for left, right in itertools.pairwise(operands):
                for number, other in ((left, right), (right, left)):
                    if (c := _literal(number)) and type(c.value) is int and _is_len(unit, other):
                        allowed.add(id(c))
    return allowed | _version_literals(unit, set(config.versioned.callables))


def _annotations(tree: ast.Module) -> Iterator[ast.AST]:
    for node in ast.walk(tree):
        if isinstance(node, ast.arg | ast.AnnAssign):
            yield from filter(None, [node.annotation])
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield from filter(None, [node.returns])
        elif isinstance(node, ast.TypeAlias):
            yield node.value


def fb005(unit: Unit, config: ForbiddenConfig) -> list[Finding]:
    """FB005: a numeric literal in check, calc, block and rule modules, except the forms A1 to A4 and annotations."""
    if not unit.modules.covers(unit.local, "check", "calc", "block", "rule"):
        return []
    skipped = {id(n) for root in _annotations(unit.tree) for n in ast.walk(root)}
    allowed = _allowed(unit, config)
    negated = {id(n.operand) for n in ast.walk(unit.tree) if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub)}
    found: list[Finding] = []
    for node in ast.walk(unit.tree):
        if isinstance(node, ast.Constant) and _literal(node) and id(node) not in skipped | allowed:
            sign = "-" if id(node) in negated else ""
            found.append(
                unit.finding(
                    "FB005", node, f"numeric literal {sign}{node.value!r}: cite it or take it from the design basis"
                )
            )
    return found


def _digit_free(pattern: str) -> str | None:
    """Return why ``pattern`` does not forbid digits (None when it does): a digit it matches or a missing match."""
    try:
        regex = re.compile(pattern)
    except re.error as error:
        return f"pattern {pattern!r} is not a regular expression: {error}"
    if bad := next((d for d in DIGITS if regex.search(f"a{d}b")), None):
        return f"pattern {pattern!r} matches the digit U+{ord(bad):04X}"
    return None if regex.search("ab") else f"pattern {pattern!r} does not match plain letters"


def _problem(unit: Unit, config: ForbiddenConfig, annotation: ast.expr | None) -> str | None:
    """Return why ``annotation`` does not forbid digits, or None when it does."""
    if annotation is None:
        return "no annotation"
    types = set(config.rationale_policy.types)
    if isinstance(annotation, ast.Name | ast.Attribute):
        return None if _last(unit.qualname(annotation)) in types else "not a rationale type"
    match annotation:
        case ast.Subscript(value=base, slice=ast.Tuple(elts=[ast.Name(id="str"), *metadata])) if (
            _last(unit.qualname(base)) == "Annotated"
        ):
            patterns = [k.value for m in metadata if isinstance(m, ast.Call) for k in m.keywords if k.arg == "pattern"]
            if not patterns:
                return "Annotated[str, ...] without a pattern"
            for value in patterns:
                if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    return "the pattern is not a string literal"
                if reason := _digit_free(value.value):
                    return reason
            return None
    return "not a rationale type"


def fb006(unit: Unit, config: ForbiddenConfig) -> list[Finding]:
    """FB006: a class attribute ``rationale`` or ``*_rationale`` whose type does not forbid digits."""
    found: list[Finding] = []
    for cls in (n for n in ast.walk(unit.tree) if isinstance(n, ast.ClassDef)):
        for stmt in cls.body:
            if isinstance(stmt, ast.Assign):
                targets, annotation = stmt.targets, None
            elif isinstance(stmt, ast.AnnAssign):
                targets, annotation = [stmt.target], stmt.annotation
            else:
                continue
            for target in targets:
                reason = _problem(unit, config, annotation)
                if isinstance(target, ast.Name) and re.fullmatch(r"(?:\w+_)?rationale", target.id) and reason:
                    found.append(unit.finding("FB006", stmt, f"{target.id!r} must forbid digits: {reason}"))
    return found


def fb008(unit: Unit, _config: ForbiddenConfig) -> list[Finding]:
    """FB008: defining a deselecting hook, calling ``hook.pytest_deselected`` or assigning ``collect_ignore*``."""
    found: list[Finding] = []
    for node in ast.walk(unit.tree):
        names: list[str] = []
        match node:
            case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name) if name in HOOKS:
                names = [name]
            case ast.Call(func=ast.Attribute(attr="pytest_deselected", value=ast.Attribute(attr="hook"))):
                names = ["hook.pytest_deselected"]
            case ast.Assign() | ast.AnnAssign() | ast.AugAssign():
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = [
                    t.id if isinstance(t, ast.Name) else t.attr
                    for t in targets
                    if isinstance(t, ast.Name | ast.Attribute)
                ]
                names = [n for n in names if n in IGNORE_NAMES or n in HOOKS]
        if names:
            found.append(unit.finding("FB008", node, f"{names[0]} deselects tests"))
    return found


RULES_B: tuple[Rule, ...] = (
    Rule("FB004", "src", fb004),
    Rule("FB005", "src", fb005),
    Rule("FB006", "src", fb006),
    Rule("FB008", "tests", fb008),
)
