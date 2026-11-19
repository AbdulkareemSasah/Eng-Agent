"""The edit-cycle workflow modules obey the rules of block code (plan 0007 T8; spec 0007 AC2; spec 0001 4.1.2).

Imports, no `.value` read, no arithmetic, no `while`, no bare `except` (the scan of `test_block_modules.py`), no I/O
call, and no numeric literal except an integer index, a `len` comparison and the integer `version=` of a declaration.
"""

import ast
import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import eng_harness.workflows.model_edit_cycle as package

FOLDER = Path(package.__file__).resolve().parent
IO_CALLS = {"open", "input", "print"}


def _scan() -> Callable[[str], list[str]]:
    """`check_source` of `test_block_modules.py`, loaded by path (importing it by name would make mypy see it twice)."""
    spec = importlib.util.spec_from_file_location("block_rules_scan", Path(__file__).with_name("test_block_modules.py"))
    assert spec is not None
    assert spec.loader is not None
    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    found: Callable[[str], list[str]] = module.check_source
    return found


def _literals(tree: ast.AST) -> list[int]:
    """Lines of numeric literals that are neither an index, a `len` comparison nor a `version=` keyword."""
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            allowed |= {id(n) for n in ast.walk(node.slice)}
        if isinstance(node, ast.Compare) and any(
            isinstance(side, ast.Call) and ast.unparse(side.func) == "len" for side in (node.left, *node.comparators)
        ):
            allowed |= {id(n) for n in ast.walk(node)}
        if isinstance(node, ast.keyword) and node.arg == "version":
            allowed.add(id(node.value))
        if isinstance(node, ast.AnnAssign):
            allowed |= {id(n) for n in ast.walk(node.annotation)}
    return [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and type(n.value) in (int, float) and id(n) not in allowed
    ]


def test_modules_follow_block_rules() -> None:
    scan = _scan()
    names = {p.name for p in FOLDER.glob("*.py")}
    assert {"__init__.py", "_cycle.py", "_change_set.py", "_points.py"} <= names
    for path in sorted(FOLDER.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        found = scan(source)
        assert found == [], (path.name, found)
        tree = ast.parse(source)
        assert _literals(tree) == [], path.name
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert calls & IO_CALLS == set(), path.name
