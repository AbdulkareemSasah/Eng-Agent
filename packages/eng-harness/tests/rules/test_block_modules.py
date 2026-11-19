"""Block and rule module rules (plan 0001 T17; spec 0001 4.1.2, AC19): imports, `.value`, arithmetic, loops, excepts."""

import ast
import os
import tomllib
from pathlib import Path

import pytest

import eng_harness.errors as errors_module

PACKAGE = Path(errors_module.__file__).resolve().parents[2]  # packages/eng-harness
SRC = PACKAGE / "src" / "eng_harness"

# Spec 4.1.2: a module, or a module of its own subtree, that may be imported with any name.
ALLOWED_MODULES = (
    "eng_harness.block",
    "eng_harness.ctx",
    "eng_contract.quantity",
    "eng_contract.kinds",
    "eng_harness.kinds.edit_cycle",
    "eng_harness.decisions.types",
    "eng_harness.workflows",
    "eng_harness.blocks",
    "eng_harness.rules",
    "pydantic",
    "enum",
    "typing",
    "collections.abc",
    "__future__",
)
# Spec 4.1.2: modules of which only the listed names may be imported (the `from` form).
ALLOWED_NAMES = {
    "eng_contract.refs": {"Ref", "RefString"},
    "eng_contract.errors": {"ErrorCode"},
    "eng_contract.verdicts": {"VerdictStatus"},
    "eng_contract.units": {"QUANTITY_KINDS", "UNITS"},
    "eng_harness.errors": {
        name for name, member in vars(errors_module).items()
        if isinstance(member, type) and issubclass(member, errors_module.StepError)
    },
}  # fmt: skip
ARITHMETIC = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.MatMult)
_FORBIDDEN_ATTRS = frozenset({"value", "parser", "__dict__"})
_MODEL_DUMP_METHODS = frozenset({"model_dump", "model_dump_json"})


def _mutation_import(node: ast.Import | ast.ImportFrom) -> bool:
    """The import mutmut inserts so a rewritten module can select the active mutant (B-542); only under mutation."""
    if "MUTANT_UNDER_TEST" not in os.environ:
        return False
    if isinstance(node, ast.Import):
        return all(alias.name == "mutmut" or alias.name.startswith("mutmut.") for alias in node.names)
    module = node.module or ""
    return module == "mutmut" or module.startswith("mutmut.")


def _module_ok(name: str) -> bool:
    return any(name == allowed or name.startswith(allowed + ".") for allowed in ALLOWED_MODULES)


def _import_problems(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):  # only the `from` form can name what is imported
        return [f"{node.lineno}: import of {a.name}" for a in node.names if not _module_ok(a.name)]
    module = node.module or ""
    if node.level:
        return [f"{node.lineno}: relative import of {'.' * node.level}{module}"]
    if module in ALLOWED_NAMES:
        bad = sorted(a.name for a in node.names if a.name not in ALLOWED_NAMES[module])
        return [f"{node.lineno}: import of {name} from {module}" for name in bad]
    return [] if _module_ok(module) else [f"{node.lineno}: import from {module}"]


def _catches_everything(handler: ast.ExceptHandler) -> bool:
    """A bare `except` or one that names `BaseException`, alone or in a tuple, plain or as `builtins.BaseException`."""
    if handler.type is None:
        return True
    kinds = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(ast.unparse(kind) in {"BaseException", "builtins.BaseException"} for kind in kinds)


def _call_violation(node: ast.Call) -> str | None:
    """Detect `vars(...)` and `getattr(..., "value" | "parser" | "__dict__")` calls."""
    if not isinstance(node.func, ast.Name):
        return None
    if node.func.id == "vars":
        return f"{node.lineno}: call of vars"
    if (
        node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
        and node.args[1].value in _FORBIDDEN_ATTRS
    ):
        return f"{node.lineno}: getattr for {node.args[1].value}"
    return None


def _dump_value_subscript(node: ast.Subscript) -> str | None:
    """Detect `["value"]` applied directly to a `model_dump(...)` or `model_dump_json(...)` call."""
    if (
        isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr in _MODEL_DUMP_METHODS
        and isinstance(node.slice, ast.Constant)
        and node.slice.value == "value"
    ):
        return f'{node.lineno}: subscript ["value"] on {node.value.func.attr}'
    return None


def check_source(source: str) -> list[str]:
    """The rule violations of one block or rule module, as `<line>: <what>` in the order of the lines."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import | ast.ImportFrom):
            if _mutation_import(node):
                continue
            found += [(int(p.partition(":")[0]), p) for p in _import_problems(node)]
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRS and isinstance(node.ctx, ast.Load):
            found.append((node.lineno, f"{node.lineno}: read of the attribute {node.attr}"))
        elif isinstance(node, ast.Call) and (call_msg := _call_violation(node)) is not None:
            found.append((node.lineno, call_msg))
        elif isinstance(node, ast.Subscript) and (sub_msg := _dump_value_subscript(node)) is not None:
            found.append((node.lineno, sub_msg))
        elif isinstance(node, ast.BinOp | ast.AugAssign) and isinstance(node.op, ARITHMETIC):
            found.append((node.lineno, f"{node.lineno}: arithmetic operator {type(node.op).__name__}"))
        elif isinstance(node, ast.While):
            found.append((node.lineno, f"{node.lineno}: while loop"))
        elif isinstance(node, ast.ExceptHandler) and _catches_everything(node):
            found.append((node.lineno, f"{node.lineno}: bare except or except BaseException"))
    return [text for _, text in sorted(found)]


def _globs(*keys: str) -> list[str]:
    pyproject = PACKAGE / "pyproject.toml"
    table = tomllib.loads(pyproject.read_text(encoding="utf-8"))["tool"]["eng-gate"]
    return [pattern for key in keys for pattern in table[key]]


def modules(root: Path, globs: list[str]) -> list[Path]:
    """Every `.py` file under the directories that the `<dir>/**` globs name, relative to `root`."""
    found: set[Path] = set()
    for pattern in globs:
        assert pattern.endswith("/**"), pattern  # the form the package uses; others need this helper extended
        found.update(path for path in (root / pattern.removesuffix("/**")).rglob("*.py") if path.is_file())
    return sorted(found)


VIOLATIONS = """\
from __future__ import annotations
import asyncio
import eng_harness.ctx
from eng_contract.refs import Ref, resolve_ref
from eng_contract.units import UNITS, convert
from eng_harness.errors import HarnessCode, ToolFailed
from eng_harness.engine import rule_guard
from . import sibling


def run(ctx, quantity):
    total = quantity.value
    total += 1
    ratio = total / 2
    while ratio:
        ratio = 0
    try:
        pass
    except:
        pass
    try:
        pass
    except (ValueError, BaseException):
        pass
    _ = getattr(quantity, "value")
    _ = quantity.__dict__
    _ = vars(quantity)
    _ = quantity.model_dump()["value"]
    _ = quantity.model_dump_json()["value"]
    _ = quantity.parser
    return total - ratio, total % 2, total ** 2, total // 2, total * 2, total @ 2
"""
CLEAN = """\
from __future__ import annotations
from collections.abc import Sequence
from enum import StrEnum
from typing import Any
from eng_contract.kinds.basis import BasisPath
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref, RefString
from eng_contract.units import QUANTITY_KINDS, UNITS
from eng_contract.errors import ErrorCode
from eng_contract.verdicts import VerdictStatus
from eng_harness.block import block
from eng_harness.ctx import BasisCount
from eng_harness.errors import StepError, ToolFailed
from eng_harness.workflows.model_edit_cycle._change_set import BasisValue
from pydantic import BaseModel


def run(items: Sequence[Quantity] | None, mapping: dict[str, Any], item: Any) -> list[int]:
    _ = mapping["value"]
    _ = item.model_dump(mode="json")["section"]
    _ = item.model_dump_json(indent=2)["section"]
    _ = getattr(item, "section")
    try:
        return [index for index, _ in enumerate(items or [])]
    except ToolFailed:
        raise
    except Exception:
        return []
"""


def test_rules_detect_violations() -> None:
    assert check_source(VIOLATIONS) == [
        "2: import of asyncio",
        "4: import of resolve_ref from eng_contract.refs",
        "5: import of convert from eng_contract.units",
        "6: import of HarnessCode from eng_harness.errors",
        "7: import from eng_harness.engine",
        "8: relative import of .",
        "12: read of the attribute value",
        "13: arithmetic operator Add",
        "14: arithmetic operator Div",
        "15: while loop",
        "19: bare except or except BaseException",
        "23: bare except or except BaseException",
        "25: getattr for value",
        "26: read of the attribute __dict__",
        "27: call of vars",
        '28: subscript ["value"] on model_dump',
        '29: subscript ["value"] on model_dump_json',
        "30: read of the attribute parser",
        "31: arithmetic operator FloorDiv",
        "31: arithmetic operator MatMult",
        "31: arithmetic operator Mod",
        "31: arithmetic operator Mult",
        "31: arithmetic operator Pow",
        "31: arithmetic operator Sub",
    ]  # line 3 passes: `import eng_harness.ctx` is allowed; line 23 names BaseException in a tuple
    assert check_source(CLEAN) == []  # the `|` of a union is not arithmetic; allowed names and modules pass
    assert check_source('x = item.model_dump(mode="json")["value"]\n') == ['1: subscript ["value"] on model_dump']
    assert check_source('x = getattr(item, "value", None)\n') == ["1: getattr for value"]
    assert check_source("x = vars()\n") == ["1: call of vars"]


def test_mutation_runner_import_is_judged_only_under_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    source = "from mutmut.mutation.trampoline import wrap_in_trampoline\nimport mutmut\nimport os\n"
    monkeypatch.delenv("MUTANT_UNDER_TEST", raising=False)
    assert check_source(source) == [
        "1: import from mutmut.mutation.trampoline",
        "2: import of mutmut",
        "3: import of os",
    ]
    monkeypatch.setenv("MUTANT_UNDER_TEST", "x")
    assert check_source(source) == ["3: import of os"]  # only what mutmut inserts is tolerated


def test_module_discovery(tmp_path: Path) -> None:
    (tmp_path / "pkg" / "inner").mkdir(parents=True)
    for name in ("pkg/a.py", "pkg/inner/b.py", "pkg/notes.txt", "other.py"):
        (tmp_path / name).write_text("", encoding="utf-8")
    found = modules(tmp_path, ["pkg/**", "missing/**"])
    assert [path.relative_to(tmp_path).as_posix() for path in found] == ["pkg/a.py", "pkg/inner/b.py"]


def test_package_block_modules_pass() -> None:
    files = modules(PACKAGE, _globs("block_modules", "rule_modules"))
    names = {path.name for path in files}
    assert {"_change_set.py", "_requests.py"} <= names  # the merged workflow modules are scanned, not skipped
    problems = {path.name: found for path in files if (found := check_source(path.read_text(encoding="utf-8")))}
    assert problems == {}
