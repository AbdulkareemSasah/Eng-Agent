"""Packs and the registry (spec 0001 section 4.6).

Purpose: a `Pack` groups the checks of one code edition; `Registry` finds packs through the entry-point group
`structural_codes.packs` (the core never imports a pack by name) and looks checks up by id, in sorted order.
An overlay pack (`base` and `overlay` set, spec 4.11) is resolved by `Registry.of`: its inherited checks are derived
and its removed checks answer a lookup with `NOT_FOUND` and the removal reason.
Errors: `CheckDefinitionError` for a wrong pack, overlay or duplicate; `ContractError(NOT_FOUND)` for an unknown or
removed check id.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.metadata import entry_points

from eng_contract.errors import ContractError, ErrorCode

from structural_codes.check import Check
from structural_codes.errors import CheckDefinitionError
from structural_codes.overlay import Overlay

__all__ = ["ENTRY_POINT_GROUP", "Pack", "Registry"]

ENTRY_POINT_GROUP = "structural_codes.packs"
_NAME = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True, slots=True)
class Pack:
    """A code-edition pack; `approvals` is the package resource path of its `approvals.yaml`."""

    name: str
    code: str
    edition: str
    version: str
    checks: tuple[Check, ...]
    approvals: str
    base: str | None = None
    overlay: Overlay | None = None

    def __post_init__(self) -> None:
        """Validate the name and that every check belongs to this pack.

        Raises:
            CheckDefinitionError: malformed name, `base` without `overlay` (or the reverse, or an overlay for another
                base), or a check whose metadata names another pack.
        """
        if not _NAME.fullmatch(self.name):
            raise CheckDefinitionError(f"pack name {self.name!r} must match {_NAME.pattern}")
        if (self.base is None) != (self.overlay is None) or (self.overlay and self.overlay.base != self.base):
            raise CheckDefinitionError(f"pack {self.name}: base and overlay must be given together and name one pack")
        for c in self.checks:
            if c.meta.pack != self.name:
                raise CheckDefinitionError(
                    f"check {c.meta.check_id} belongs to pack {c.meta.pack!r}, not {self.name!r}"
                )


class Registry:
    """Packs and checks in sorted order (packs by name, checks by id)."""

    def __init__(
        self, packs: tuple[Pack, ...], checks: dict[str, Check], removed: Mapping[str, str] | None = None
    ) -> None:
        """Keep the sorted packs, the id index and the removal reasons by overlay id; build with `of` or `discover`."""
        self._packs = packs
        self._checks = checks
        self._removed = removed or {}

    @classmethod
    def of(cls, packs: Iterable[Pack]) -> Registry:
        """Build a registry from explicit packs.

        Raises:
            CheckDefinitionError: duplicate pack name or duplicate check_id, an overlay whose base pack is missing
                or is itself an overlay, or an invalid overlay (`Overlay.resolve`).
        """
        ordered = tuple(sorted(packs, key=lambda p: p.name))
        names = [p.name for p in ordered]
        if len(set(names)) != len(names):
            raise CheckDefinitionError("duplicate pack name")
        derived: list[Check] = []
        removed: dict[str, str] = {}
        for p in ordered:
            if p.overlay is None:
                continue
            base = next((b for b in ordered if b.name == p.base), None)
            if base is None or base.overlay is not None:
                raise CheckDefinitionError(f"pack {p.name}: base pack {p.base!r} is missing or is itself an overlay")
            more, gone = p.overlay.resolve(p, base)
            derived.extend(more)
            removed.update(gone)
        checks: dict[str, Check] = {}
        for c in sorted([*(c for p in ordered for c in p.checks), *derived], key=lambda c: c.meta.check_id):
            if c.meta.check_id in checks or c.meta.check_id in removed:
                raise CheckDefinitionError(f"duplicate check_id {c.meta.check_id}")
            checks[c.meta.check_id] = c
        return cls(ordered, checks, removed)

    @classmethod
    def discover(cls) -> Registry:
        """Load every pack registered under `ENTRY_POINT_GROUP` (sorted by entry-point name).

        Raises:
            CheckDefinitionError: an entry point is not a `Pack`, or `of` rejects the packs.
        """
        loaded: list[Pack] = []
        for ep in sorted(entry_points(group=ENTRY_POINT_GROUP), key=lambda e: e.name):
            value = ep.load()
            if not isinstance(value, Pack):
                raise CheckDefinitionError(f"entry point {ep.name!r} is not a Pack")
            loaded.append(value)
        return cls.of(loaded)

    @property
    def packs(self) -> tuple[Pack, ...]:
        """The packs, sorted by name."""
        return self._packs

    @property
    def checks(self) -> tuple[Check, ...]:
        """All checks, sorted by check_id."""
        return tuple(self._checks.values())

    def get(self, check_id: str) -> Check:
        """Return the check with this id.

        Raises:
            ContractError: code `NOT_FOUND`, field `check_id`, for an unknown id; the `hint` names the reason when the
                overlay removed the check (AC20).
        """
        found = self._checks.get(check_id)
        if found is None:
            reason = self._removed.get(check_id)
            hint = None if reason is None else f"removed by the overlay: {reason}"
            raise ContractError(ErrorCode.NOT_FOUND, f"no check {check_id!r}", field="check_id", hint=hint)
        return found
