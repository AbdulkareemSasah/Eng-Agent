"""Content hash of a calc over its static import closure, and the calc lock file (spec 0003 4.5, AC2, AC6, AC7).

Purpose: `content_sha256` changes when the calc, any `eng_harness` module it imports (transitively), its metadata or
either schema changes. The closure is found with `ast` and the file system, never by importing (`find_spec` would run
`calcs/__init__.py` while the registry is being built). Units: none; CRLF and CR are normalized to LF.
Errors: `CalcRegistryError` rule `hash`: `importlib`, `__import__`, an import inside a function or class, a module
without source (bytecode only) or one that does not parse.
"""

import ast
import hashlib
import json
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import eng_contract
from eng_contract.canonical import payload_sha256
from eng_contract.kinds import KindRegistry
from pydantic import BaseModel

from eng_harness._calc import CalcRegistryError

if TYPE_CHECKING:
    from eng_harness.calc import CalcDef, CalcRegistry

HASH_VERSION = "harness.calc_hash/1"
LOCK_SCHEMA = 1
_PACKAGE = "eng_harness"
_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = _ROOT / "calcs" / "calcs.lock.json"
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _locate(name: str, root: Path, calc_id: str) -> Path | None:
    """Source file of an `eng_harness` module under `root`, or None for any other name (no import is run)."""
    if name != _PACKAGE and not name.startswith(_PACKAGE + "."):
        return None
    base = root.joinpath(*name.split(".")[1:])
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    if base.with_suffix(".pyc").is_file():
        raise CalcRegistryError("hash", calc_id, f"{name} has no source file (bytecode only)")
    return None


def _imports(node: ast.AST, package: str, calc_id: str, nested: bool = False) -> Iterator[tuple[str, list[str]]]:
    """Yield `(module, names)` for each import statement under `node`; refuse dynamic and nested imports."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.If) and ast.unparse(child.test) == "__name__ == '__main__'":  # body: not run on import
            for orelse in child.orelse:  # the else branch does run
                yield from _imports(ast.Module([orelse], []), package, calc_id, nested)
            continue
        if isinstance(child, ast.Name | ast.Attribute) and "__import__" in (
            getattr(child, "id", ""),
            getattr(child, "attr", ""),
        ):
            raise CalcRegistryError("hash", calc_id, "uses __import__")
        if isinstance(child, ast.Import | ast.ImportFrom):
            if nested:
                raise CalcRegistryError("hash", calc_id, "imports inside a function or class")
            found: list[tuple[str, list[str]]]
            if isinstance(child, ast.Import):
                found = [(a.name, []) for a in child.names]
            else:
                parts = package.split(".")[: len(package.split(".")) - (child.level - 1)] if child.level else []
                base = ".".join([*parts, *([child.module] if child.module else [])])
                found = [(base, [a.name for a in child.names])]
            for module, names in found:
                if module.split(".")[0] == "importlib":
                    raise CalcRegistryError("hash", calc_id, "imports importlib")
                yield module, names
        yield from _imports(child, package, calc_id, nested or isinstance(child, _SCOPES))


def module_hashes(definition: CalcDef, root: Path = _ROOT) -> dict[str, str]:
    """SHA-256 of the LF-normalized source of the calc's module and of every `eng_harness` module it imports.

    A package `__init__` is hashed only when it is named by an import and supplies an attribute, never as an implicit
    parent. `root` is the directory of the `eng_harness` sources.

    Raises:
        CalcRegistryError: rule `hash`, see the module docstring.
    """
    calc_id = definition.id
    name = definition.fn.__module__
    own = _locate(name, root, calc_id) or getattr(sys.modules.get(name), "__file__", None)
    if not own:
        raise CalcRegistryError("hash", calc_id, f"the source of {name} is not available")
    pending = [(name, Path(own))]
    hashes: dict[str, str] = {}
    while pending:
        name, path = pending.pop()
        if name in hashes:
            continue
        if path.suffix != ".py":
            raise CalcRegistryError("hash", calc_id, f"{name} has no source file ({path.name})")
        data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        hashes[name] = hashlib.sha256(data).hexdigest()
        try:
            tree = ast.parse(data)
        except (SyntaxError, ValueError) as exc:
            raise CalcRegistryError("hash", calc_id, f"{name} does not parse: {exc}") from exc
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        for module, names in _imports(tree, package, calc_id):
            subs = {f"{module}.{n}": _locate(f"{module}.{n}", root, calc_id) for n in names}
            wanted: dict[str, Path | None] = {n: p for n, p in subs.items() if p}
            if len(wanted) < max(len(names), 1):  # a name that is an attribute of the package, or a plain import
                wanted[module] = _locate(module, root, calc_id)
            pending.extend((n, p) for n, p in wanted.items() if p)
    return dict(sorted(hashes.items()))


def content_hash(definition: CalcDef, kinds: KindRegistry, *, root: Path = _ROOT) -> str:
    """The `content_sha256` of a calc: `payload_sha256` of the object of spec 0003 4.5.

    Raises:
        CalcRegistryError: rule `hash`, see the module docstring.
    """
    input_type = definition.input_type
    if not (isinstance(input_type, type) and issubclass(input_type, BaseModel)):
        raise CalcRegistryError("hash", definition.id, "the input type is not a model")
    return payload_sha256(
        {
            "hash_version": HASH_VERSION,
            "calc_id": definition.id,
            "version": definition.version,
            "title": definition.title,
            "method_source": definition.method_source,
            "verification": str(definition.verification),
            "output_kind": definition.output_kind,
            "input_schema": input_type.model_json_schema(),
            "output_schema": kinds[definition.output_kind].model_json_schema(),
            "modules": module_hashes(definition, root),
            "eng_contract_version": eng_contract.__version__,
        }
    )


def read_lock(path: Path = LOCK_PATH) -> dict[str, Any]:
    """Load the lock file: `{"schema": 1, "calcs": [{id, version, content_sha256} | {id, removed: true}]}`."""
    lock: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return lock


def render_lock(lock: dict[str, Any]) -> bytes:
    """The exact bytes of a lock file (UTF-8, LF, sorted keys)."""
    return (json.dumps(lock, indent=2, sort_keys=True) + "\n").encode()


def removed_ids(lock: dict[str, Any]) -> frozenset[str]:
    """Ids that the lock marks removed; a registry refuses to register them again (AC2)."""
    return frozenset(e["id"] for e in lock.get("calcs", []) if e.get("removed"))


def lock_problems(registry: CalcRegistry, lock: dict[str, Any]) -> list[str]:
    """Differences between `registry` and `lock`; empty when they agree (AC2)."""
    problems = [] if lock.get("schema") == LOCK_SCHEMA else ["unsupported lock schema"]
    entries: dict[str, dict[str, Any]] = {}
    for entry in lock.get("calcs", []):
        if entry["id"] in entries:
            problems.append(f"{entry['id']}: duplicate lock entry")
        entries[entry["id"]] = entry
    for calc_id in registry:
        entry = entries.get(calc_id, {"removed": True})
        if entry.get("removed"):
            problems.append(f"{calc_id}: registered but missing from the lock or marked removed")
        elif (entry.get("version"), entry.get("content_sha256")) != (
            registry[calc_id].version,
            registry.content_hash(calc_id),
        ):
            problems.append(f"{calc_id}: the lock entry differs from the registry (run the lock writer)")
    problems += [
        f"{i}: in the lock but not registered and not marked removed"
        for i, e in entries.items()
        if i not in registry and not e.get("removed")
    ]
    return problems


def build_lock(registry: CalcRegistry, previous: dict[str, Any]) -> dict[str, Any]:
    """The lock for `registry`; an id of `previous` that is no longer registered stays, marked removed."""
    entries: dict[str, dict[str, Any]] = {
        i: {"id": i, "version": registry[i].version, "content_sha256": registry.content_hash(i)} for i in registry
    }
    for entry in previous.get("calcs", []):
        entries.setdefault(entry["id"], {"id": entry["id"], "removed": True})
    return {"schema": LOCK_SCHEMA, "calcs": [entries[i] for i in sorted(entries)]}


def main(argv: Sequence[str], *, registry: CalcRegistry, lock_path: Path = LOCK_PATH) -> int:
    """Lock writer: `uv run python -m eng_harness._calc._hash --write-lock`."""
    if list(argv) != ["--write-lock"]:
        raise SystemExit("usage: python -m eng_harness._calc._hash --write-lock")
    lock_path.write_bytes(render_lock(build_lock(registry, read_lock(lock_path))))
    return 0


if __name__ == "__main__":
    from eng_harness.calcs import REGISTRY

    raise SystemExit(main(sys.argv[1:], registry=REGISTRY))
