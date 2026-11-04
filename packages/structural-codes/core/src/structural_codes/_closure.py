"""Static import closure of a module (spec 0001 section 4.7).

Purpose: find every module a check can reach through `import` statements, from the source text alone. Nothing is
imported or executed: modules are located with `importlib` finders and read as text, then parsed with `ast`.
Errors: `CheckDefinitionError` for a dynamic import (`importlib`, `__import__`) in a module of a checked top-level
package, an import that cannot be resolved, a source that cannot be read or parsed, or a relative import above the
top-level package.
"""

import ast
import importlib.util
import sys
from importlib.machinery import ModuleSpec, PathFinder
from pathlib import Path

from structural_codes.errors import CheckDefinitionError

__all__ = ["import_closure", "is_package"]


def _spec(name: str) -> ModuleSpec | None:
    """Locate a module without importing it (a loaded module answers with its own spec)."""
    loaded = sys.modules.get(name)
    if loaded is not None:
        return getattr(loaded, "__spec__", None)
    parent, _, _ = name.rpartition(".")
    if not parent:
        return importlib.util.find_spec(name)
    parent_spec = _spec(parent)
    if parent_spec is None or parent_spec.submodule_search_locations is None:
        return None
    return PathFinder.find_spec(name, list(parent_spec.submodule_search_locations))


def is_package(name: str) -> bool:
    """Whether the located module is a package (its source is an `__init__.py` or it is a namespace package)."""
    spec = _spec(name)
    return spec is not None and spec.submodule_search_locations is not None


def _source(name: str) -> str | None:
    """Return the LF-normalized source of a module, or `None` for a namespace package (it has no source).

    Raises:
        CheckDefinitionError: not found, not a `.py` source, not UTF-8.
    """
    spec = _spec(name)
    if spec is None:
        raise CheckDefinitionError(f"cannot resolve the import of {name!r}")
    if spec.origin is None and spec.submodule_search_locations is not None:
        return None
    if not spec.origin or not spec.origin.endswith(".py"):
        raise CheckDefinitionError(f"module {name!r} has no Python source (origin {spec.origin!r})")
    try:
        text = Path(spec.origin).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CheckDefinitionError(f"cannot read the source of {name!r}: {exc}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _imports(name: str, text: str, is_package: bool, checked: bool) -> tuple[list[str], list[str]]:
    """Return the modules a source must import and the dotted names that are submodules only if they exist.

    `checked` turns a dynamic import (`importlib`, `__import__`) in this source into an error.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise CheckDefinitionError(f"cannot parse the source of {name!r}: {exc}") from exc
    required: list[str] = []
    optional: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            required.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(name, is_package, node)
            required.append(base)
            optional.extend(f"{base}.{alias.name}" for alias in node.names)
        elif checked and isinstance(node, ast.Call) and "__import__" in (
            getattr(node.func, "id", None),
            getattr(node.func, "attr", None),
        ):
            raise CheckDefinitionError(f"module {name!r} calls __import__")
    for target in required if checked else ():
        if target.partition(".")[0] == "importlib":
            raise CheckDefinitionError(f"module {name!r} imports importlib ({target})")
    return required, optional


def _absolute(name: str, is_package: bool, node: ast.ImportFrom) -> str:
    """Resolve the module of a `from` import to its absolute dotted name."""
    if node.level == 0:
        return node.module or ""
    package = name.split(".") if is_package else name.split(".")[:-1]
    if node.level - 1 >= len(package):
        raise CheckDefinitionError(f"module {name!r} imports beyond its top-level package")
    package = package[: len(package) - (node.level - 1)]
    return ".".join([*package, node.module] if node.module else package)


def import_closure(start: str, tops: frozenset[str], checked: frozenset[str]) -> dict[str, str]:
    """Return `{dotted name: LF-normalized source}` of `start` and of every module it imports, sorted by name.

    Only modules whose top-level package is in `tops` are followed (`start` itself is always included); the parent
    packages of an included module are included too, because importing the module runs their `__init__`. Imports
    inside functions and under `TYPE_CHECKING` count as well (conservative). A dynamic import is an error only in a
    module whose top-level package is in `checked` (the check's pack); the other packages in `tops` are hashed but
    exempt, because their own gates govern them (spec 4.7).

    Raises:
        CheckDefinitionError: see the module docstring.
    """
    found: dict[str, str] = {}
    seen: set[str] = set()
    pending = [start]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        text = _source(name)
        if text is None:
            continue
        found[name] = text
        required, optional = _imports(name, text, is_package(name), name.partition(".")[0] in checked)
        parents = [".".join(name.split(".")[:n]) for n in range(1, name.count(".") + 1)]
        pending.extend(p for p in parents if p.partition(".")[0] in tops)
        pending.extend(t for t in required if t.partition(".")[0] in tops)
        pending.extend(o for o in optional if o.partition(".")[0] in tops and _spec(o) is not None)
    return dict(sorted(found.items()))
