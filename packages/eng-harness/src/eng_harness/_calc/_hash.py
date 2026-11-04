"""Content hash of a calc over its static import closure, and the calc lock file (spec 0003 4.5).

Purpose: an approval binds to a content hash, so the hash must change with anything that can change a result: the
calc module and every `eng_harness` module it imports (transitively, found with `ast`, nothing imported or run), its
metadata, and its input and output schemas. Line endings are normalized, so CRLF and LF checkouts agree.
Units: none. Errors: `CalcRegistryError` with rule `hash` (source unavailable, dynamic or non-top-level import in a
calc module) or `removed` (a lock entry marked removed is registered again).
"""

import argparse
import ast
import hashlib
import importlib
import importlib.util
import json
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

import eng_contract
from eng_contract.canonical import payload_sha256
from eng_contract.kinds import KindRegistry
from pydantic import BaseModel, ConfigDict, Field, model_validator

from eng_harness.calc import CalcDef, CalcRegistry, CalcRegistryError

__all__ = [
    "LOCK_PATH",
    "CalcLock",
    "LockEntry",
    "content_hash",
    "dump_lock",
    "lock_for",
    "main",
    "module_hashes",
    "read_lock",
    "write_lock",
]

HASH_VERSION = "harness.calc_hash/1"
LOCK_PATH = Path(__file__).resolve().parents[1] / "calcs" / "calcs.lock.json"
_DYNAMIC = frozenset({"__import__", "importlib"})


def _fail(calc_id: str, why: str) -> CalcRegistryError:
    return CalcRegistryError("hash", calc_id, why)


def _source_path(name: str, package: str, root: Path) -> Path | None:
    """The `.py` file of module `name`, or None; a module inside `package` is located without importing it."""
    if name == package or name.startswith(package + "."):
        base = root.joinpath(*name.split(".")[1:])
        candidates = [base / "__init__.py"] if name == package else [base.with_suffix(".py"), base / "__init__.py"]
        return next((c for c in candidates if c.is_file()), None)
    spec = getattr(sys.modules.get(name), "__spec__", None)
    origin = getattr(spec, "origin", None)
    path = Path(origin) if isinstance(origin, str) and origin.endswith(".py") else None
    return path if path is not None and path.is_file() else None


def _type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _top_level(body: Sequence[ast.stmt]) -> Iterator[ast.stmt]:
    """Imports at module level, including those inside an `if TYPE_CHECKING:` block."""
    for node in body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            yield node
        elif isinstance(node, ast.If) and _type_checking(node.test):
            yield from _top_level([*node.body, *node.orelse])


def _dynamic(tree: ast.Module) -> str | None:
    """Why a calc module cannot be hashed statically, or None."""
    top = {id(node) for node in _top_level(tree.body)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            if id(node) not in top:
                return "an import that is not at module level"
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if any(n.split(".")[0] in _DYNAMIC for n in names):
                return "an import of importlib"
        elif isinstance(node, ast.Name) and node.id in _DYNAMIC:
            return f"a use of {node.id}"
    return None


def _imports(tree: ast.Module, name: str, is_package: bool) -> Iterator[tuple[str, bool]]:
    """Dotted names a module imports, with True when the name must be a module (not a possible attribute)."""
    package_parts = (name if is_package else name.rpartition(".")[0]).split(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, True
        elif isinstance(node, ast.ImportFrom):
            parts = package_parts[: len(package_parts) - node.level + 1] if node.level else []
            base = ".".join([*parts, *([node.module] if node.module else [])])
            yield base, True
            for alias in node.names:
                yield f"{base}.{alias.name}", False


def module_hashes(module: str, *, package: str = "eng_harness", calc_id: str | None = None) -> dict[str, str]:
    """SHA-256 of the LF-normalized UTF-8 source of `module` and of every `package` module it imports, transitively.

    The closure follows imports at any depth, `if TYPE_CHECKING` blocks included. A calc module (one under
    `<package>.calcs`, or `module` itself when it lies outside `package`) must import only at module level and never
    through `importlib` or `__import__`.

    Raises:
        CalcRegistryError: rule `hash`, when a source is not available or a calc module imports dynamically.
    """
    owner = calc_id or module
    spec = importlib.util.find_spec(package)
    if spec is None or not spec.submodule_search_locations:
        raise _fail(owner, f"package {package!r} cannot be found")
    root = Path(next(iter(spec.submodule_search_locations)))
    calcs_package = f"{package}.calcs"
    hashes: dict[str, str] = {}
    todo: list[tuple[str, bool]] = [(module, True)]
    while todo:
        name, required = todo.pop()
        if name in hashes:
            continue
        path = _source_path(name, package, root)
        if path is None:
            if required or name in sys.modules:
                raise _fail(owner, f"the source of {name} is not available")
            continue
        try:
            text = path.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
            tree = ast.parse(text)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            raise _fail(owner, f"the source of {name} cannot be read: {exc}") from exc
        if name.startswith(calcs_package + ".") or (name == module and not name.startswith(package + ".")):
            reason = _dynamic(tree)
            if reason:
                raise _fail(owner, f"{name} has {reason}")
        hashes[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        todo.extend(
            (dep, must)
            for dep, must in _imports(tree, name, path.name == "__init__.py")
            if dep.split(".")[0] == package
        )
    return hashes


def content_hash(definition: CalcDef, kinds: KindRegistry, *, package: str = "eng_harness") -> str:
    """The content hash of `definition` (spec 0003 4.5): `payload_sha256` of metadata, schemas and module hashes.

    Raises:
        CalcRegistryError: rule `hash` (see `module_hashes`) or `input_type` (not a model class).
    """
    d = definition
    if not (isinstance(d.input_type, type) and issubclass(d.input_type, BaseModel)):
        raise CalcRegistryError("input_type", d.id, "the input type must be a model class")
    payload = {
        "hash_version": HASH_VERSION,
        "calc_id": d.id,
        "version": d.version,
        "title": d.title,
        "method_source": d.method_source,
        "verification": str(d.verification),
        "output_kind": d.output_kind,
        "input_schema": d.input_type.model_json_schema(),
        "output_schema": kinds[d.output_kind].model_json_schema(),
        "modules": module_hashes(d.fn.__module__, package=package, calc_id=d.id),
        "eng_contract_version": eng_contract.__version__,
    }
    return payload_sha256(payload)


class LockEntry(BaseModel):
    """One calc in the lock file; a removed calc keeps its id so it is never registered again."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    version: int = Field(ge=1, le=9999)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    removed: bool = False


class CalcLock(BaseModel):
    """The lock file: entries sorted by id, ids unique."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lock_version: int = 1
    calcs: list[LockEntry]

    @model_validator(mode="after")
    def _sorted_unique(self) -> CalcLock:
        ids = [entry.id for entry in self.calcs]
        if ids != sorted(set(ids)):
            raise ValueError("lock entries must be sorted by id and unique")
        return self

    @property
    def removed_ids(self) -> frozenset[str]:
        """Ids that were removed and cannot be registered again."""
        return frozenset(entry.id for entry in self.calcs if entry.removed)


def read_lock(path: Path = LOCK_PATH) -> CalcLock:
    """Read and validate the lock file."""
    return CalcLock.model_validate_json(path.read_text(encoding="utf-8"))


def dump_lock(lock: CalcLock) -> str:
    """The canonical text of a lock file (sorted keys, two-space indent, trailing newline)."""
    return json.dumps(lock.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def lock_for(registry: CalcRegistry, previous: CalcLock) -> CalcLock:
    """The lock for `registry`: registered calcs with their hash, calcs gone from the registry marked removed.

    Raises:
        CalcRegistryError: rule `removed`, when a registered calc has a removed entry in `previous`.
    """
    old = {entry.id: entry for entry in previous.calcs}
    entries: dict[str, LockEntry] = {}
    for calc_id in registry:
        if calc_id in previous.removed_ids:
            raise CalcRegistryError("removed", calc_id, "the id was removed and cannot be registered again")
        entries[calc_id] = LockEntry(
            id=calc_id, version=registry[calc_id].version, content_sha256=registry.content_hash(calc_id)
        )
    for calc_id, entry in old.items():
        entries.setdefault(calc_id, entry.model_copy(update={"removed": True}))
    return CalcLock(calcs=sorted(entries.values(), key=lambda entry: entry.id))


def write_lock(registry: CalcRegistry, path: Path = LOCK_PATH, *, previous: CalcLock | None = None) -> CalcLock:
    """Write the lock of `registry` to `path` (the previous lock is read from `path` unless given)."""
    if previous is None:
        previous = read_lock(path) if path.exists() else CalcLock(calcs=[])
    lock = lock_for(registry, previous)
    path.write_text(dump_lock(lock), encoding="utf-8", newline="\n")
    return lock


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point `python -m eng_harness._calc._hash --write-lock`: rewrite the committed lock file."""
    parser = argparse.ArgumentParser(prog="eng_harness._calc._hash", description=__doc__)
    parser.add_argument("--write-lock", action="store_true", required=True)
    parser.parse_args(argv)
    write_lock(importlib.import_module("eng_harness.calcs").REGISTRY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
