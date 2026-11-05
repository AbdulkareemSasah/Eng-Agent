"""Rules, the restricted basis view, the rule registry, its lock and the review table (spec 0005 section 4.4).

Purpose: a rule is a pure function ``(state, basis) -> Pick | None`` with an id, a rationale and the basis paths it may
read; the registry checks and orders rules, ``rules.lock.json`` forces a version bump when a rule's code changes.
Units: none; quantities keep the unit of the design basis.
Errors: ``DecisionDefinitionError`` for an invalid rule, registry or lock file; ``BlockRuleViolation`` for a basis path
outside a rule's ``thresholds``.
"""

import ast
import importlib
import importlib.util
import inspect
import json
import pkgutil
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Any, Literal

from eng_contract.kinds.basis import BasisPath
from eng_contract.quantity import Quantity
from pydantic import BaseModel, StringConstraints, TypeAdapter, ValidationError

from eng_harness.block import LockFinding, RegistryError, _annotation, _code_hash
from eng_harness.ctx import BasisCount, BasisView
from eng_harness.decisions._points import DecisionDefinitionError, PointRegistry, _import_failed, _refuse
from eng_harness.errors import BlockRuleViolation

__all__ = [
    "RULES_LOCK_PATH",
    "Rationale",
    "ReviewRow",
    "Rule",
    "RuleBasis",
    "RuleRegistry",
    "RuleTestFinding",
    "check_rule_lock",
    "discover",
    "load_rule_lock",
    "missing_rule_tests",
    "rule",
    "write_rule_lock",
]

RULES_LOCK_PATH = Path(__file__).resolve().parent.parent / "rules.lock.json"

# AC2: 1 to 300 characters, no digit in any script (the form gate rule FB006 probes).
Rationale = Annotated[str, StringConstraints(min_length=1, max_length=300, pattern=r"^\D+$")]

_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}\.[a-z][a-z0-9_]*$")  # AC9
_PATH = TypeAdapter(BasisPath)
_RATIONALE = TypeAdapter(Rationale)
_NOT_PLAIN = inspect.CO_COROUTINE | inspect.CO_GENERATOR | inspect.CO_ASYNC_GENERATOR | inspect.CO_ITERABLE_COROUTINE


class RuleBasis:
    """The design basis as a rule sees it: only the paths in the rule's ``thresholds`` can be read (AC11)."""

    def __init__(self, view: BasisView, thresholds: Iterable[str]) -> None:
        """Wrap the call's ``view``; ``thresholds`` are the permitted basis paths."""
        self._view = view
        self._allowed = frozenset(thresholds)

    def _permit(self, path: str) -> None:
        if path not in self._allowed:
            raise BlockRuleViolation(f"basis path {path!r} is not in the rule's thresholds")

    def quantity(self, path: str) -> Quantity:
        """The field as a ``Quantity`` in its declared unit."""
        self._permit(path)
        return self._view.quantity(path)

    def count(self, path: str) -> BasisCount:
        """The field as a ``BasisCount``."""
        self._permit(path)
        return self._view.count(path)

    def choice[E: StrEnum](self, path: str, enum: type[E]) -> E:
        """The field as a member of ``enum``."""
        self._permit(path)
        return self._view.choice(path, enum)


@dataclass(frozen=True, slots=True)
class Rule:
    """One immutable rule; ``code_sha256`` hashes its module source with LF line endings (AC10)."""

    id: str
    version: int
    point: str
    rationale: Rationale
    thresholds: tuple[str, ...]
    fn: Callable[[Any, RuleBasis], object]
    state: type[BaseModel]
    module: str
    code_sha256: str


def rule(
    *, id: str, version: int, point: str, rationale: Rationale, thresholds: Sequence[str] = ()
) -> Callable[[Callable[..., object]], Rule]:
    """Return a decorator that builds a ``Rule`` (no global registration). Errors: ``DecisionDefinitionError`` (AC9)."""

    def build(fn: Callable[..., object]) -> Rule:
        if not _ID.match(id) or id.split(".")[0] != point:
            _refuse("rule id", f"{id!r} must match <point>.<name> with the point {point!r}")
        if type(version) is not int or not 1 <= version <= 9999:
            _refuse("version", f"{version!r} must be an integer from 1 to 9999")
        try:
            _RATIONALE.validate_python(rationale)
            for path in thresholds:
                _PATH.validate_python(path)
        except ValidationError as exc:
            raise DecisionDefinitionError(f"{id}: invalid rationale or threshold path") from exc
        if not inspect.isfunction(fn) or fn.__code__.co_flags & _NOT_PLAIN:
            _refuse("rule function", f"{id} must be a plain synchronous function")
        params = list(inspect.signature(fn).parameters)
        if len(params) != 2:
            _refuse("rule function", f"{id} takes (state, basis)")
        try:
            state = _annotation(id, fn, params[0])
            digest = _code_hash(fn)
        except RegistryError as exc:
            raise DecisionDefinitionError(f"{id}: {exc}") from exc
        if not (isinstance(state, type) and issubclass(state, BaseModel)):
            _refuse("rule function", f"{id}: the first parameter must be annotated with the point's state model")
        return Rule(id, version, point, rationale, tuple(thresholds), fn, state, fn.__module__, digest)

    return build


@dataclass(frozen=True, slots=True)
class ReviewRow:
    """One row of the owner's review table (AC13); ``approval`` is ``draft`` unless an approval matches the hash."""

    id: str
    point: str
    version: int
    rationale: Rationale
    thresholds: tuple[str, ...]
    code_sha256: str
    approval: Literal["draft", "approved"]


@dataclass(frozen=True, slots=True)
class RuleRegistry:
    """An immutable set of rules, unique by id and held sorted by id.

    With ``points``, every rule must name a registered point whose state model is the rule's first parameter type.
    """

    rules: Sequence[Rule]
    points: PointRegistry | None = None

    def __post_init__(self) -> None:
        """Sort by id and check AC9; errors: ``DecisionDefinitionError``."""
        found = tuple(sorted(self.rules, key=lambda r: r.id))
        for first, second in pairwise(found):
            if first.id == second.id:
                _refuse("duplicate", f"rule id {first.id!r}")
        for item in found if self.points is not None else ():
            point = self.points.get(item.point) if self.points is not None else None
            if point is None:
                _refuse("rule", f"{item.id}: no decision point {item.point!r}")
            if point.state is not item.state:
                _refuse("rule", f"{item.id}: the first parameter is not the state model of {item.point!r}")
        object.__setattr__(self, "rules", found)

    def get(self, rule_id: str) -> Rule | None:
        """Return the rule with ``rule_id``, or ``None`` when none is registered (a lookup, not a failure)."""
        return next((r for r in self.rules if r.id == rule_id), None)

    def with_(self, *more: Rule) -> RuleRegistry:
        """Return a new registry that also holds ``more``."""
        return RuleRegistry([*self.rules, *more], self.points)

    def review_table(self, approvals: Mapping[str, str]) -> tuple[ReviewRow, ...]:
        """One row per rule; ``approvals`` maps a rule id to the ``code_sha256`` the owner approved (no file I/O)."""
        return tuple(
            ReviewRow(
                r.id,
                r.point,
                r.version,
                r.rationale,
                r.thresholds,
                r.code_sha256,
                "approved" if approvals.get(r.id) == r.code_sha256 else "draft",
            )
            for r in self.rules
        )


def discover() -> RuleRegistry:
    """Import every module under ``eng_harness.rules`` and collect its module-level rules (spec 4.4).

    Empty when the package is absent. Nothing is registered by importing; errors of those imports propagate.
    """
    if importlib.util.find_spec("eng_harness.rules") is None:
        return RuleRegistry([])
    package = importlib.import_module("eng_harness.rules")
    modules = [package]
    for info in pkgutil.walk_packages(package.__path__, "eng_harness.rules.", onerror=_import_failed):
        modules.append(importlib.import_module(info.name))
    found: dict[int, Rule] = {}
    for module in modules:
        for value in vars(module).values():
            if isinstance(value, Rule):
                found[id(value)] = value
    return RuleRegistry(list(found.values()))


def load_rule_lock(path: Path) -> list[dict[str, object]]:
    """Read ``[{id, version, code_sha256}]``. Errors: ``DecisionDefinitionError`` for a malformed file."""
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(
        isinstance(e, dict) and {"id", "version", "code_sha256"} <= e.keys() for e in data
    ):
        _refuse("lock", f"{path.name} must hold a list of {{id, version, code_sha256}} entries")
    return data


def check_rule_lock(registry: RuleRegistry, lock: Sequence[Mapping[str, object]]) -> tuple[LockFinding, ...]:
    """A changed hash under the same version is ``VERSION_BUMP_REQUIRED``; any other difference is ``LOCK_STALE``."""
    entries = {str(e["id"]): e for e in lock}
    findings: list[LockFinding] = []
    for item in registry.rules:
        entry = entries.pop(item.id, None)
        if entry is None or entry["version"] != item.version:
            findings.append(LockFinding(item.id, "LOCK_STALE"))
        elif entry["code_sha256"] != item.code_sha256:
            findings.append(LockFinding(item.id, "VERSION_BUMP_REQUIRED"))
    findings.extend(LockFinding(name, "LOCK_STALE") for name in entries)
    return tuple(sorted(findings, key=lambda f: f.name))


def write_rule_lock(registry: RuleRegistry, path: Path) -> None:
    """Write the lock sorted by id; refuse a changed hash under an unchanged version."""
    old = load_rule_lock(path) if path.exists() else []
    if any(f.code == "VERSION_BUMP_REQUIRED" for f in check_rule_lock(registry, old)):
        _refuse("VERSION_BUMP_REQUIRED", "a rule changed without a version bump")
    entries = [{"id": r.id, "version": r.version, "code_sha256": r.code_sha256} for r in registry.rules]
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True, slots=True)
class RuleTestFinding:
    """A missing rule test: the rule, the file ``tests_dir`` should hold and the test function missing in it."""

    rule_id: str
    expected_file: str
    expected_test: str


def missing_rule_tests(registry: RuleRegistry, tests_dir: Path) -> tuple[RuleTestFinding, ...]:
    """Return one finding per missing ``test_<name>_typical`` or ``test_<name>_boundary`` (AC12).

    The file is ``test_<module>.py``, ``<module>`` the last component of the rule's module name. Pure: only reads.
    """
    findings: list[RuleTestFinding] = []
    for item in registry.rules:
        file = f"test_{item.module.rsplit('.', 1)[-1]}.py"
        path = tests_dir / file
        tree = ast.parse(path.read_text(encoding="utf-8")) if path.is_file() else ast.Module([], [])
        defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
        name = item.id.split(".", 1)[1]
        findings.extend(
            RuleTestFinding(item.id, file, test)
            for test in (f"test_{name}_typical", f"test_{name}_boundary")
            if test not in defined
        )
    return tuple(findings)
