"""Decision points, state field rules, the point registry and the lock (spec 0005 section 4.2; AC1 to AC4).

Units: ``max_state_bytes`` counts bytes of canonical JSON. Errors: ``DecisionDefinitionError`` for an invalid
definition or lock file (raised at import or registration), ``BlockRuleViolation`` for an oversize state.
"""

import argparse
import hashlib
import importlib
import importlib.util
import json
import pkgutil
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Any, NoReturn, get_args, get_origin

from eng_contract.canonical import canonical_json
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref
from pydantic import BaseModel, StringConstraints, TypeAdapter, ValidationError

from eng_harness.block import LockFinding
from eng_harness.decisions._policy import DecisionSettings
from eng_harness.errors import BlockRuleViolation

__all__ = [
    "LOCK_PATH",
    "DecisionDefinitionError",
    "DecisionPoint",
    "Label",
    "PointRegistry",
    "Refs",
    "check_lock",
    "check_state_size",
    "decision_point",
    "discover",
    "load_lock",
    "main",
    "write_lock",
]

LOCK_PATH = Path(__file__).resolve().parent.parent / "decisions.lock.json"

# AC2: 1 to 80 characters, no control character, none of / \ @ : (a path, URL or address cannot be a label).
_LABEL = StringConstraints(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f-\x9f/\\@:]+$")
Label = Annotated[str, _LABEL]

_NAME = re.compile(r"^[a-z][a-z0-9_]{2,63}$")  # AC1
_OPTION = re.compile(r"^[a-z][a-z0-9_]*$")  # AC1


class DecisionDefinitionError(ValueError):
    """An invalid point, rule or policy definition, raised at import or registration (spec 6)."""


@dataclass(frozen=True, slots=True)
class Refs:
    """Options that are references: the state field ``labels_field`` (a tuple of ``Label``) names them."""

    labels_field: str


@dataclass(frozen=True, slots=True)
class DecisionPoint:
    """One immutable decision point; ``schema_sha256`` hashes the option values and the state JSON schema."""

    name: str
    version: int
    title: str
    options: type[StrEnum] | Refs
    state: type[BaseModel]
    yes_no: tuple[str, str] | None
    schema_sha256: str


def _refuse(rule: str, detail: str) -> NoReturn:
    raise DecisionDefinitionError(f"{rule}: {detail}")


def _finite(meta: Sequence[object], config: Mapping[str, Any]) -> bool:
    return config.get("allow_inf_nan") is False or any(getattr(m, "allow_inf_nan", None) is False for m in meta)


def _check_field(annotation: Any, meta: Sequence[object], config: Mapping[str, Any], path: str) -> None:
    """Accept one AC2 field type or raise ``DecisionDefinitionError`` naming ``path``."""
    origin = get_origin(annotation)
    if origin is Annotated:
        head, *extra = get_args(annotation)
        _check_field(head, [*meta, *extra], config, path)
    elif origin is tuple:
        args = get_args(annotation)
        if not args:
            _refuse("state field", f"{path} is an untyped tuple")
        for item in args[:1] if args[-1] is Ellipsis else args:
            _check_field(item, [], config, path)
    elif annotation in (bool, int, Quantity, Ref):
        return
    elif annotation is float:
        if not _finite(meta, config):
            _refuse("state field", f"{path} is a float that may be infinite or NaN (set allow_inf_nan=False)")
    elif (annotation is str and _LABEL in meta) or (isinstance(annotation, type) and issubclass(annotation, StrEnum)):
        return
    elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
        _check_model(annotation, f"nested model at {path}")
    else:
        _refuse("state field", f"{path} has type {annotation!r}, which is not allowed")


def _check_model(model: object, what: str) -> None:
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        _refuse("state", f"{what} must be a Pydantic model")
    if model.model_config.get("frozen") is not True or model.model_config.get("extra") != "forbid":
        _refuse("state", f"{what} must be frozen with extra='forbid'")
    for field_name, info in model.model_fields.items():
        _check_field(info.annotation, info.metadata, model.model_config, f"{model.__name__}.{field_name}")


def _is_label_tuple(annotation: Any) -> bool:
    if get_origin(annotation) is not tuple:
        return False
    args = get_args(annotation)
    item = args[0] if len(args) == 2 and args[1] is Ellipsis else None
    return get_origin(item) is Annotated and _LABEL in get_args(item)[1:]


def _check_options(options: object, state: type[BaseModel], yes_no: tuple[str, str] | None, limit: int) -> object:
    """Validate ``options`` and ``yes_no`` (AC1); return the JSON form that enters the schema hash."""
    if isinstance(options, Refs):
        info = state.model_fields.get(options.labels_field)
        if info is None or not _is_label_tuple(info.annotation):
            _refuse("labels_field", f"{options.labels_field!r} must be a tuple[Label, ...] field of the state")
        if yes_no is not None:
            _refuse("yes_no", "only allowed for two-member enums")
        return {"refs": options.labels_field}
    if not (isinstance(options, type) and issubclass(options, StrEnum)):
        _refuse("options", "must be a StrEnum or Refs")
    values = [str(m.value) for m in options]
    if not 1 <= len(values) <= limit:
        _refuse("options", f"needs 1 to {limit} members, has {len(values)}")
    if not all(_OPTION.match(v) for v in values):
        _refuse("options", "values must match ^[a-z][a-z0-9_]*$")
    if yes_no is not None and (len(values) != 2 or sorted(yes_no) != sorted(values)):
        _refuse("yes_no", "must name the two option values of a two-member enum")
    return values


def decision_point(
    *,
    name: str,
    version: int,
    title: str,
    options: type[StrEnum] | Refs,
    state: type[BaseModel],
    yes_no: tuple[str, str] | None = None,
    settings: DecisionSettings | None = None,
) -> Callable[[type], DecisionPoint]:
    """Return a decorator that builds the immutable ``DecisionPoint`` (no global registration).

    Errors: ``DecisionDefinitionError`` naming the broken rule of AC1 or AC2.
    """
    limit = (settings or DecisionSettings()).max_options

    def build(_marker: type) -> DecisionPoint:
        if not _NAME.match(name):
            _refuse("name", f"{name!r} must match ^[a-z][a-z0-9_]{{2,63}}$")
        if type(version) is not int or not 1 <= version <= 9999:
            _refuse("version", f"{version!r} must be an integer from 1 to 9999")
        try:
            TypeAdapter(Label).validate_python(title)
        except ValidationError as exc:
            raise DecisionDefinitionError(f"title: {title!r} is not a valid Label") from exc
        _check_model(state, "state")
        shape = _check_options(options, state, yes_no, limit)
        digest = hashlib.sha256(canonical_json({"options": shape, "state": state.model_json_schema()})).hexdigest()
        return DecisionPoint(name, version, title, options, state, yes_no, digest)

    return build


@dataclass(frozen=True, slots=True)
class PointRegistry:
    """An immutable set of points, unique by name and held sorted by name."""

    points: Sequence[DecisionPoint]

    def __post_init__(self) -> None:
        """Sort by name; a second point with one name is ``DecisionDefinitionError`` (AC1)."""
        found = tuple(sorted(self.points, key=lambda p: p.name))
        for first, second in pairwise(found):
            if first.name == second.name:
                _refuse("duplicate", f"decision point name {first.name!r}")
        object.__setattr__(self, "points", found)

    def get(self, name: str) -> DecisionPoint | None:
        """Return the point called ``name``, or ``None`` when none is registered (a lookup, not a failure)."""
        return next((p for p in self.points if p.name == name), None)

    def with_(self, *more: DecisionPoint) -> PointRegistry:
        """Return a new registry that also holds ``more``."""
        return PointRegistry([*self.points, *more])


def _import_failed(name: str) -> NoReturn:
    raise  # re-raise the import error inside the walk_packages callback


def discover() -> PointRegistry:
    """Import every module under ``eng_harness.workflows`` and collect its module-level points (spec 4.2).

    Empty when the package is absent. Nothing is registered by importing; errors of those imports propagate.
    """
    if importlib.util.find_spec("eng_harness.workflows") is None:
        return PointRegistry([])
    package = importlib.import_module("eng_harness.workflows")
    modules = [package]
    for info in pkgutil.walk_packages(package.__path__, "eng_harness.workflows.", onerror=_import_failed):
        modules.append(importlib.import_module(info.name))
    found: dict[int, DecisionPoint] = {}
    for module in modules:
        for value in vars(module).values():
            if isinstance(value, DecisionPoint):
                found[id(value)] = value
    return PointRegistry(list(found.values()))


def check_state_size(point_name: str, state: BaseModel, max_state_bytes: int) -> None:
    """Raise ``BlockRuleViolation`` when the canonical JSON of ``state`` exceeds ``max_state_bytes`` (AC3)."""
    size = len(canonical_json(state.model_dump(mode="json")))
    if size > max_state_bytes:
        raise BlockRuleViolation(f"{point_name}: state is {size} bytes, above max_state_bytes {max_state_bytes}")


def load_lock(path: Path) -> list[dict[str, object]]:
    """Read ``[{name, version, schema_sha256}]``. Errors: ``DecisionDefinitionError`` for a malformed file."""
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(
        isinstance(e, dict) and {"name", "version", "schema_sha256"} <= e.keys() for e in data
    ):
        _refuse("lock", f"{path.name} must hold a list of {{name, version, schema_sha256}} entries")
    return data


def check_lock(registry: PointRegistry, lock: Sequence[Mapping[str, object]]) -> tuple[LockFinding, ...]:
    """Compare the registry with a lock (AC4).

    A changed hash under the same version is ``VERSION_BUMP_REQUIRED``; any other difference is ``LOCK_STALE``.
    """
    entries = {str(e["name"]): e for e in lock}
    findings: list[LockFinding] = []
    for point in registry.points:
        entry = entries.pop(point.name, None)
        if entry is None or entry["version"] != point.version:
            findings.append(LockFinding(point.name, "LOCK_STALE"))
        elif entry["schema_sha256"] != point.schema_sha256:
            findings.append(LockFinding(point.name, "VERSION_BUMP_REQUIRED"))
    findings.extend(LockFinding(name, "LOCK_STALE") for name in entries)
    return tuple(sorted(findings, key=lambda f: f.name))


def write_lock(registry: PointRegistry, path: Path) -> None:
    """Write the lock sorted by name; refuse a changed hash under an unchanged version."""
    old = load_lock(path) if path.exists() else []
    if any(f.code == "VERSION_BUMP_REQUIRED" for f in check_lock(registry, old)):
        _refuse("VERSION_BUMP_REQUIRED", "a decision point changed without a version bump")
    entries = [{"name": p.name, "version": p.version, "schema_sha256": p.schema_sha256} for p in registry.points]
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of ``python -m eng_harness.decisions --write-lock``; returns the exit code."""
    parser = argparse.ArgumentParser(prog="eng_harness.decisions")
    parser.add_argument("--write-lock", action="store_true", required=True)
    parser.parse_args(argv)
    write_lock(discover(), LOCK_PATH)
    return 0
