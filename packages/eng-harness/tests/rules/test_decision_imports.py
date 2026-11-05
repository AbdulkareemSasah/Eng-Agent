"""The block-safe types module imports nothing of the engine, journal, ports, network or database (spec 0005 AC42)."""

import ast
from pathlib import Path

import eng_harness.decisions._rules as rules_module
import eng_harness.decisions.types as types_module

SRC = Path(types_module.__file__).resolve().parents[1]
FORBIDDEN_OWN = {"engine", "journal", "ports"}
FORBIDDEN = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "sqlite3",
    "dbm",
    "asyncio",
    "anyio",
    "httpx",
    "requests",
    "mcp",
    "uvicorn",
}


def _file(module: str) -> Path | None:
    base = SRC.joinpath(*module.split(".")[1:])
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imports(path: Path) -> set[str]:
    """Names imported at run time (a TYPE_CHECKING block is skipped) by one source file."""
    found: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skipped = {
        id(inner)
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and ast.unparse(node.test) in {"TYPE_CHECKING", "typing.TYPE_CHECKING"}
        for inner in ast.walk(node)
    }
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names if _file(f"{node.module}.{alias.name}"))
    return found


def _closure(start: Path) -> set[str]:
    seen: set[str] = set()
    todo = [start]
    done: set[Path] = set()
    while todo:
        path = todo.pop()
        if path in done:
            continue
        done.add(path)
        for name in _imports(path):
            seen.add(name)
            target = _file(name) if name.split(".")[0] == "eng_harness" else None
            if target is not None:
                todo.append(target)
    return seen


def test_types_module_is_block_safe() -> None:
    assert Path(rules_module.__file__).parent == Path(types_module.__file__).parent  # the guarded package
    imported = _closure(Path(types_module.__file__))
    assert "eng_harness.decisions._rules" in imported  # the closure follows the types module into the rules
    assert {name.split(".")[0] for name in imported}.isdisjoint(FORBIDDEN)
    own = {name.split(".")[1] for name in imported if name.startswith("eng_harness.")}
    assert own.isdisjoint(FORBIDDEN_OWN)
