"""Blocks, workflows, the registry, the code hash and the block lock file (spec 0001 4.2).

Purpose: decorators build immutable block definitions; a registry holds them; the lock file makes a version bump
mandatory when a block's code hash changes.
Units: none.
Errors: `RegistryError` (a registration or lock rule is broken; its message names the rule or lock code).
"""

import annotationlib
import argparse
import hashlib
import inspect
import json
import re
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.machinery import SourceFileLoader
from itertools import pairwise
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel

if TYPE_CHECKING:
    from eng_harness.basis._fields import FieldSpec

__all__ = [
    "LOCK_PATH",
    "BlockDef",
    "FieldSpec",
    "LockFinding",
    "ModelFile",
    "Registry",
    "RegistryError",
    "WorkflowDef",
    "block",
    "check_lock",
    "discover",
    "load_lock",
    "main",
    "workflow",
    "write_lock",
]

ModelFile = PurePath
"""The absolute path of a model file (passed to the host port under its base name); a pure path with no I/O method."""

LOCK_PATH = Path(__file__).resolve().parent / "blocks.lock.json"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_VERSION = re.compile(r"^[1-9][0-9]{0,3}$")
type _Fn[I: BaseModel, O: BaseModel] = Callable[[Any, I], Awaitable[O]]


class RegistryError(ValueError):
    """A registration rule or a lock rule is broken; the message names it."""


@dataclass(frozen=True)
class BlockDef[I: BaseModel, O: BaseModel]:
    """A registered block: identity, models, function and the SHA-256 of its module source (LF line endings)."""

    name: str
    version: int
    input_model: type[I]
    output_model: type[O]
    fn: _Fn[I, O]
    module: str
    code_sha256: str


@dataclass(frozen=True)
class WorkflowDef[I: BaseModel, O: BaseModel](BlockDef[I, O]):
    """A block that is also a workflow: description, required basis paths, server builds and always-ask tools.

    `basis_fields` are the basis fields it uses (`required_basis` derives from them); `copy_on_open` takes the working
    copy at the first open of a model, in every mode (engine spec 4.2, 4.7).
    """

    description: str = ""
    required_basis: tuple[str, ...] = ()
    min_server_builds: Mapping[str, str] = field(default_factory=dict)
    always_ask: tuple[str, ...] = ()
    options_model: type[BaseModel] | None = None
    basis_fields: tuple[FieldSpec, ...] = ()
    copy_on_open: bool = False


@dataclass(frozen=True)
class LockFinding:
    """One lock problem: `code` is `VERSION_BUMP_REQUIRED` or `LOCK_STALE`."""

    name: str
    code: str


def _code_hash(fn: Callable[..., object]) -> str:
    """Return the SHA-256 of the module source of `fn` (loader `get_source`, LF endings); `RegistryError` without it."""
    module = sys.modules.get(fn.__module__)
    loader = getattr(module, "__loader__", None)
    if not callable(getattr(loader, "get_source", None)):
        # Import hooks without get_source (for example a test assertion rewriter): read through the file loader.
        origin = getattr(module, "__file__", None)
        loader = SourceFileLoader(fn.__module__, origin) if origin else None
    try:
        source = loader.get_source(fn.__module__) if loader is not None else None
    except (ImportError, OSError) as exc:
        raise RegistryError(f"source of module {fn.__module__} is not available") from exc
    if source is None:
        raise RegistryError(f"source of module {fn.__module__} is not available")
    return hashlib.sha256(source.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def _annotation(name: str, fn: Callable[..., object], key: str) -> object:
    """Return the annotation `key` of `fn`, resolved; `RegistryError` when it names an unresolvable type."""
    value = annotationlib.get_annotations(fn, format=annotationlib.Format.FORWARDREF).get(key)
    if isinstance(value, str):
        value = annotationlib.ForwardRef(value, owner=fn)
    if isinstance(value, annotationlib.ForwardRef):
        try:
            return cast("object", value.evaluate(globals=getattr(fn, "__globals__", None)))
        except NameError as exc:
            role = "output" if key == "return" else "input"
            raise RegistryError(f"{name}: the {role} annotation {value.__forward_arg__!r} cannot be resolved") from exc
    return value


def _checked[I: BaseModel, O: BaseModel](name: str, version: int, fn: _Fn[I, O]) -> tuple[type[I], type[O], str]:
    """Apply the registration rules of AC2; return the input model, output model and code hash."""
    if not inspect.iscoroutinefunction(fn):
        raise RegistryError(f"{name}: the block function must be async def")
    params = list(inspect.signature(fn).parameters)
    if len(params) != 2:
        raise RegistryError(f"{name}: the block function takes (ctx, inp)")
    input_model, output_model = _annotation(name, fn, params[1]), _annotation(name, fn, "return")
    if not (isinstance(input_model, type) and issubclass(input_model, BaseModel)):
        raise RegistryError(f"{name}: the input type must be a Pydantic BaseModel subclass")
    if not (isinstance(output_model, type) and issubclass(output_model, BaseModel)):
        raise RegistryError(f"{name}: the output type must be a Pydantic BaseModel subclass")
    if not _NAME.fullmatch(name):
        raise RegistryError(f"block name {name!r} must match {_NAME.pattern}")
    if type(version) is not int or not _VERSION.fullmatch(str(version)):
        raise RegistryError(f"{name}: version {version!r} must match {_VERSION.pattern}")
    return cast("type[I]", input_model), cast("type[O]", output_model), _code_hash(fn)


def block[I: BaseModel, O: BaseModel](*, name: str, version: int) -> Callable[[_Fn[I, O]], BlockDef[I, O]]:
    """Build a `BlockDef` from an async function; never registers globally. Errors: `RegistryError`."""

    def decorate(fn: _Fn[I, O]) -> BlockDef[I, O]:
        input_model, output_model, digest = _checked(name, version, fn)
        return BlockDef(name, version, input_model, output_model, fn, fn.__module__, digest)

    return decorate


def workflow[I: BaseModel, O: BaseModel](
    *,
    name: str,
    version: int,
    description: str,
    required_basis: tuple[str, ...] | None = None,
    min_server_builds: Mapping[str, str] | None = None,
    always_ask: tuple[str, ...] = (),
    options_model: type[BaseModel] | None = None,
    basis_fields: tuple[FieldSpec, ...] = (),
    copy_on_open: bool = False,
) -> Callable[[_Fn[I, O]], WorkflowDef[I, O]]:
    """Build a `WorkflowDef` (a block with a 1 to 500 character description). Errors: `RegistryError`.

    With `basis_fields`, `required_basis` is the paths of the required fields, in order; one passed beside them must
    hold the same paths (`check_declaration`, spec 0004 AC21), else `RegistryError` carrying its reason.
    """
    if not 1 <= len(description) <= 500:
        raise RegistryError(f"{name}: description must be 1 to 500 characters")
    if basis_fields:
        from eng_harness.basis._fields import BasisInvalid, check_declaration  # a module-level import is a cycle

        derived = tuple(spec.path for spec in basis_fields if spec.required)
        try:
            check_declaration(basis_fields, derived if required_basis is None else required_basis)
        except BasisInvalid as exc:
            raise RegistryError(f"{name}: {exc.reason} at {exc.path}") from exc
        required_basis = derived

    def decorate(fn: _Fn[I, O]) -> WorkflowDef[I, O]:
        input_model, output_model, digest = _checked(name, version, fn)
        return WorkflowDef(
            name,
            version,
            input_model,
            output_model,
            fn,
            fn.__module__,
            digest,
            description,
            required_basis or (),
            min_server_builds or {},
            always_ask,
            options_model,
            basis_fields,
            copy_on_open,
        )

    return decorate


@dataclass(frozen=True, slots=True)
class Registry:
    """An immutable set of block definitions, unique by name and held sorted by name."""

    blocks: Sequence[BlockDef[Any, Any]]

    def __post_init__(self) -> None:
        """Sort by name and reject a second block with the same name (`RegistryError`)."""
        found = tuple(sorted(self.blocks, key=lambda b: b.name))
        for first, second in pairwise(found):
            if first.name == second.name:
                raise RegistryError(f"duplicate block name {first.name!r}")
        object.__setattr__(self, "blocks", found)

    def with_(self, *more: BlockDef[Any, Any]) -> Registry:
        """Return a new registry that also holds `more`."""
        return Registry([*self.blocks, *more])


def __getattr__(name: str) -> object:
    """`FieldSpec`, imported on first use: a module-level import is an import cycle (engine spec 4.1.2)."""
    if name == "FieldSpec":
        from eng_harness.basis._fields import FieldSpec

        return FieldSpec
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def discover() -> Registry:
    """Return the shipped registry; no blocks exist yet (the shipped blocks arrive with their plans)."""
    return Registry([])


def load_lock(path: Path) -> list[dict[str, object]]:
    """Read a lock file (`[{name, version, code_sha256}]`). Errors: `RegistryError` for a malformed file."""
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(
        isinstance(e, dict) and {"name", "version", "code_sha256"} <= e.keys() for e in data
    ):
        raise RegistryError(f"{path.name}: expected a list of {{name, version, code_sha256}} entries")
    return data


def check_lock(registry: Registry, lock: Sequence[Mapping[str, object]]) -> tuple[LockFinding, ...]:
    """Compare the registry with a lock: a changed hash under the same version is `VERSION_BUMP_REQUIRED`.

    Any other difference (new, removed, re-versioned block) is `LOCK_STALE`. Findings are sorted by name.
    """
    entries = {str(e["name"]): e for e in lock}
    findings: list[LockFinding] = []
    for item in registry.blocks:
        entry = entries.pop(item.name, None)
        if entry is None or entry["version"] != item.version:
            findings.append(LockFinding(item.name, "LOCK_STALE"))
        elif entry["code_sha256"] != item.code_sha256:
            findings.append(LockFinding(item.name, "VERSION_BUMP_REQUIRED"))
    findings.extend(LockFinding(name, "LOCK_STALE") for name in entries)
    return tuple(sorted(findings, key=lambda f: f.name))


def write_lock(registry: Registry, path: Path) -> None:
    """Write the lock sorted by name; refuse a changed hash under an unchanged version (`RegistryError`)."""
    old = load_lock(path) if path.exists() else []
    if any(f.code == "VERSION_BUMP_REQUIRED" for f in check_lock(registry, old)):
        raise RegistryError("VERSION_BUMP_REQUIRED: a block changed without a version bump")
    entries = [{"name": b.name, "version": b.version, "code_sha256": b.code_sha256} for b in registry.blocks]
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of `python -m eng_harness.block --write-lock`; return the exit code."""
    parser = argparse.ArgumentParser(prog="eng_harness.block")
    parser.add_argument("--write-lock", action="store_true", required=True)
    parser.parse_args(argv)
    write_lock(discover(), LOCK_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
