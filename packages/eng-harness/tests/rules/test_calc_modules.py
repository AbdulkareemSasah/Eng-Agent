"""Calc-module rules (plan 0003 T6, T7; spec 0003 AC3, 4.3): imports, purity, no module state, FB005."""

import ast
import itertools
from pathlib import Path

import pytest

import eng_harness.calcs as calcs_package

CALCS = Path(calcs_package.__file__).resolve().parent
# Form A4 (amendment B-438): the same callables as `.gate/forbidden.yml` `versioned`.
_VERSIONED = frozenset({"CheckMeta", "calc"})


def calc_modules(root: Path) -> list[Path]:
    """Every Python module under `root`, subpackages included (spec 0003 4.3)."""
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _may_read_lock(path: str) -> bool:
    """`read_lock` is the one file read, and only `calcs/__init__.py` may call it (spec 4.3)."""
    file = Path(path)
    return file.name == "__init__.py" and file.parent.name == "calcs"


def _callee(func: ast.expr) -> str:
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


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
    "eng_harness.kinds.footing",
)
ALLOWED_NAMES = {
    "eng_contract.units": {"kind_for_field", "unit"},
    "eng_contract.refs": {"RefString", "JsonPointer"},
    "eng_contract.errors": {"ContractError", "ErrorCode"},
    "eng_contract.params": {"eng_param"},
}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "globals", "vars", "setattr", "breakpoint"}
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
    """Constants in FB005 forms A1 (cited), A2 (index or bound), A3 (against len) and A4 (version)."""
    ok: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _callee(node.func) == "Cited":
            keywords = {k.arg: k.value for k in node.keywords}
            value = node.args[0] if node.args else keywords.get("value")
            source = node.args[1] if len(node.args) > 1 else keywords.get("source")
            if value is not None and (c := _numeric(value)) and isinstance(source, ast.Constant) and source.value:
                ok.add(id(c))
        elif isinstance(node, ast.Call) and _callee(node.func) in _VERSIONED:
            for keyword in node.keywords:
                if keyword.arg == "version" and (c := _numeric(keyword.value)) and type(c.value) is int:
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


def _state_statements(body: list[ast.stmt]) -> list[ast.Assign | ast.AnnAssign]:
    """Assignments at module level, including those nested in module-level blocks and class bodies."""
    found: list[ast.Assign | ast.AnnAssign] = []
    for stmt in body:
        if isinstance(stmt, ast.Assign | ast.AnnAssign):
            found.append(stmt)
        elif isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        else:
            for field in ("body", "orelse", "finalbody"):
                found += _state_statements(getattr(stmt, field, []))
            for handler in getattr(stmt, "handlers", []):
                found += _state_statements(handler.body)
    return found


def _is_all(stmt: ast.Assign | ast.AnnAssign) -> bool:
    """`__all__` is a list of names, not state."""
    targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
    return all(getattr(t, "id", "") == "__all__" for t in targets)


def _import_problems(node: ast.Import | ast.ImportFrom, top: set[int]) -> list[str]:
    found = [] if id(node) in top else [f"{node.lineno}: import inside a function or block"]
    if isinstance(node, ast.Import):
        return found + [
            f"{node.lineno}: import of {a.name} (only the from form with allowed names is accepted)"
            for a in node.names
            if not _module_ok(a.name) or a.name in ALLOWED_NAMES
        ]
    mod = node.module or ""
    if node.level or not _module_ok(mod):
        found.append(f"{node.lineno}: import of {'.' * node.level}{mod} is not allowed")
    elif mod in ALLOWED_NAMES and any(a.name not in ALLOWED_NAMES[mod] for a in node.names):
        found.append(f"{node.lineno}: import of a name from {mod} that is not allowed")
    return found


def check_source(source: str, *, path: str = "") -> list[str]:
    """Return the rule violations of one calc module's source (spec 0003 AC3 and 4.3; FB005 forms A1 to A4)."""
    tree = ast.parse(source)
    top = {id(n) for n in tree.body}
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            found += _import_problems(node, top)
        elif isinstance(node, ast.Global):
            found.append(f"{node.lineno}: global statement")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            found.append(
                f"{node.lineno}: call of {node.func.id} (open, clock, environment and random reads are refused)"
            )
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "read_lock"
            and not _may_read_lock(path)
        ):
            found.append(f"{node.lineno}: read_lock is only for calcs/__init__.py (spec 4.3)")
    for stmt in _state_statements(tree.body):
        if _mutable(stmt.value) and not _is_all(stmt):
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
    "import eng_contract.units": "import",
    "import eng_contract.errors as e": "import",
    "if True:\n    Y = {}": "mutable",
    "class A:\n    items = []": "mutable",
    "def f():\n    return globals()": "globals",
    "CACHE = {}": "mutable",
    "ITEMS: list[int] = []": "mutable",
    "X = 0.5": "FB005",
    "def f(a):\n    return a * 2": "FB005",
    "from eng_contract.cited import Cited\nX = Cited(3, '')": "FB005",
    "from eng_contract.params import ParamModel": "import",
    "@calc(version=1.5)\ndef f():\n    return None\n": "FB005",
    "read_lock()\n": "read_lock",
}
ALLOWED = [
    "import math\nfrom fractions import Fraction\nfrom pydantic import BaseModel",
    "from eng_contract.units import kind_for_field, unit",
    "from eng_contract.kinds.neutral import X",
    "from eng_harness.calcs import _state\nfrom eng_harness.calc import calc",
    "from eng_contract.cited import Cited\nX = Cited(3, 'spec')\nY = X[0]",
    "from eng_contract.cited import Cited\nX = Cited(value=3, source='spec')",
    "def f(a: list[int]) -> bool:\n    return len(a) == 2 and a[-1] > a[0]",
    "REGISTRY = Registry(kinds)",
    "from eng_contract.params import eng_param",
    "from eng_harness.kinds.footing import X",
    "from eng_harness.calc import calc\n@calc(version=1)\ndef f():\n    return None\n",
]


def test_calc_module_rules() -> None:
    modules = calc_modules(CALCS)
    assert modules, "the calcs package holds at least its __init__"
    found = [
        f"{m.relative_to(CALCS).as_posix()}: {v}"
        for m in modules
        for v in check_source(m.read_text(encoding="utf-8"), path=m.as_posix())
    ]
    assert found == []


def test_module_scan_includes_subpackages(tmp_path: Path) -> None:
    nested = tmp_path / "footing"
    nested.mkdir()
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    (nested / "check.py").write_text("import math\n", encoding="utf-8")
    found = [path.relative_to(tmp_path).as_posix() for path in calc_modules(tmp_path)]
    assert found == ["__init__.py", "footing/check.py"]


def test_only_the_package_init_reads_the_lock() -> None:
    source = "from eng_harness.calc import read_lock, removed_ids\nremoved_ids(read_lock())\n"
    assert check_source(source, path="src/eng_harness/calcs/__init__.py") == []
    refused = check_source(source, path="src/eng_harness/calcs/model_fingerprint.py")
    assert any("read_lock" in item for item in refused)


@pytest.mark.parametrize(("source", "word"), VIOLATIONS.items())
def test_rules_detect(source: str, word: str) -> None:
    ast.parse(source)
    assert any(word in v for v in check_source(source))


@pytest.mark.parametrize("source", ALLOWED)
def test_rules_allow(source: str) -> None:
    assert check_source(source) == []
