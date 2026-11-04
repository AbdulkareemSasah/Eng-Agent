"""Calc-module rules (plan 0003 T6; spec 0003 AC3, 4.3): imports, purity, no module state, FB005 literal forms."""

import ast
import itertools
from pathlib import Path

import pytest

import eng_harness.calcs as calcs_package

CALCS = Path(calcs_package.__file__).resolve().parent
MODULES = sorted(CALCS.glob("*.py"))


ALLOWED_MODULES = (
    "eng_harness.calc",
    "eng_harness.kinds.calcs",
    "eng_harness.calcs",
    "eng_contract.quantity",
    "eng_contract.cited",
    "eng_contract.trace",
    "eng_contract.canonical",
    "eng_contract.kinds",
    "eng_contract.verdicts",
    "pydantic",
    "fractions",
    "math",
    "hashlib",
    "enum",
    "typing",
    "collections.abc",
    "itertools",
    "functools",
    "operator",
    "__future__",
)
ALLOWED_NAMES = {
    "eng_contract.units": {"kind_for_field", "unit"},
    "eng_contract.refs": {"RefString", "JsonPointer"},
    "eng_contract.errors": {"ContractError", "ErrorCode"},
}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__"}
MUTABLE_CALLS = {"list", "dict", "set", "bytearray", "defaultdict", "deque", "Counter"}


def _module_ok(name: str) -> bool:
    return name in ALLOWED_NAMES or any(name == m or name.startswith(m + ".") for m in ALLOWED_MODULES)


def _numeric(node: ast.AST) -> ast.Constant | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        node = node.operand
    if isinstance(node, ast.Constant) and type(node.value) in (int, float, complex):
        return node
    return None


def _allowed_literals(tree: ast.Module) -> set[int]:
    """Constants in the FB005 forms A1 (cited value with a source), A2 (index or bound) and A3 (against len)."""
    ok: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "Cited":
            if len(node.args) > 1 and (c := _numeric(node.args[0])):
                source = node.args[1]
                if isinstance(source, ast.Constant) and source.value:
                    ok.add(id(c))
        elif isinstance(node, ast.Subscript):
            sl = node.slice
            for part in [sl.lower, sl.upper] if isinstance(sl, ast.Slice) else [sl]:
                if part and (c := _numeric(part)) and type(c.value) is int:
                    ok.add(id(c))
        elif isinstance(node, ast.Compare):
            ops = [node.left, *node.comparators]
            for left, right in itertools.pairwise(ops):
                for num, other in ((left, right), (right, left)):
                    is_len = isinstance(other, ast.Call) and getattr(other.func, "id", "") == "len"
                    if (c := _numeric(num)) and type(c.value) is int and is_len:
                        ok.add(id(c))
    return ok


def _annotation_nodes(tree: ast.Module) -> set[int]:
    skipped: set[int] = set()
    for node in ast.walk(tree):
        roots: list[ast.AST | None] = []
        if isinstance(node, ast.arg | ast.AnnAssign):
            roots = [node.annotation]
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            roots = [node.returns]
        skipped.update(id(n) for r in roots if r for n in ast.walk(r))
    return skipped


def _mutable(value: ast.expr | None) -> bool:
    if isinstance(value, ast.List | ast.Dict | ast.Set | ast.ListComp | ast.DictComp | ast.SetComp):
        return True
    return isinstance(value, ast.Call) and getattr(value.func, "id", "") in MUTABLE_CALLS


def _is_all(stmt: ast.Assign | ast.AnnAssign) -> bool:
    """`__all__` is a list of names, not state."""
    targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
    return all(getattr(t, "id", "") == "__all__" for t in targets)


def _import_problems(node: ast.Import | ast.ImportFrom, top: set[int]) -> list[str]:
    found = [] if id(node) in top else [f"{node.lineno}: import inside a function or block"]
    if isinstance(node, ast.Import):
        return found + [f"{node.lineno}: import of {a.name}" for a in node.names if not _module_ok(a.name)]
    mod = node.module or ""
    if node.level or not _module_ok(mod):
        found.append(f"{node.lineno}: import of {'.' * node.level}{mod} is not allowed")
    elif mod in ALLOWED_NAMES and any(a.name not in ALLOWED_NAMES[mod] for a in node.names):
        found.append(f"{node.lineno}: import of a name from {mod} that is not allowed")
    return found


def check_source(source: str) -> list[str]:
    """Return the rule violations of one calc module's source (spec 0003 AC3 and 4.3; FB005 forms A1 to A3)."""
    tree = ast.parse(source)
    top = {id(n) for n in tree.body}
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            found += _import_problems(node, top)
        elif isinstance(node, ast.Global):
            found.append(f"{node.lineno}: global statement")
        elif isinstance(node, ast.Call) and (name := getattr(node.func, "id", "")) in FORBIDDEN_CALLS:
            found.append(f"{node.lineno}: call of {name} (open, clock, environment and random reads are refused)")
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign | ast.AnnAssign) and _mutable(stmt.value) and not _is_all(stmt):
            found.append(f"{stmt.lineno}: mutable module-level state")
    skip = _annotation_nodes(tree) | _allowed_literals(tree)
    found += [
        f"{n.lineno}: FB005 numeric literal {n.value!r}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and type(n.value) in (int, float, complex) and id(n) not in skip
    ]
    return found


VIOLATIONS = {
    "import os": "import",
    "import eng_harness.servers": "import",
    "from eng_contract.units import convert": "import",
    "from . import _state": "import",
    "def f():\n    import math\n": "inside",
    "def f():\n    return open('x')\n": "open",
    "def f():\n    global X\n": "global",
    "CACHE = {}": "mutable",
    "ITEMS: list[int] = []": "mutable",
    "X = 0.5": "FB005",
    "def f(a):\n    return a * 2": "FB005",
    "from eng_contract.cited import Cited\nX = Cited(3, '')": "FB005",
}
ALLOWED = [
    "import math\nfrom fractions import Fraction\nfrom pydantic import BaseModel",
    "from eng_contract.units import kind_for_field, unit",
    "from eng_contract.kinds.neutral import X",
    "from eng_harness.calcs import _state\nfrom eng_harness.calc import calc",
    "from eng_contract.cited import Cited\nX = Cited(3, 'spec')\nY = X[0]",
    "def f(a: list[int]) -> bool:\n    return len(a) == 2 and a[-1] > a[0]",
    "REGISTRY = Registry(kinds)",
]


def test_calc_module_rules() -> None:
    assert MODULES, "the calcs package holds at least its __init__"
    found = [f"{m.name}: {v}" for m in MODULES for v in check_source(m.read_text(encoding="utf-8"))]
    assert found == []


@pytest.mark.parametrize(("source", "word"), VIOLATIONS.items())
def test_rules_detect(source: str, word: str) -> None:
    ast.parse(source)
    assert any(word in v for v in check_source(source))


@pytest.mark.parametrize("source", ALLOWED)
def test_rules_allow(source: str) -> None:
    assert check_source(source) == []
