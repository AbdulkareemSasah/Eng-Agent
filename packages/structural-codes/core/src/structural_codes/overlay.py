"""Overlays: a pack that inherits, overrides, adds and removes the checks of a base pack (spec 0001 section 4.11).

Purpose: an `Overlay` lists one entry per check of the base pack (`Inherited`, `Overridden` or `Removed`) and any
`Added` checks; `Overlay.resolve` validates it (completeness, AC17; clause map, AC19) and derives the inherited checks.
An inherited check runs the base body, inputs and preconditions under the overlay's code and clause, and its content
hash includes the base check's hash (AC18). R1 module: a mistake here lets a check run under the wrong code.
Units: none. Errors: `CheckDefinitionError` for every wrong overlay.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from structural_codes.check import Check
from structural_codes.errors import CheckDefinitionError
from structural_codes.meta import CheckMeta, clause_token

if TYPE_CHECKING:
    from structural_codes.pack import Pack

__all__ = ["Added", "Inherited", "InheritedCheck", "Overlay", "Overridden", "Removed"]


@dataclass(frozen=True, slots=True)
class Inherited:
    """The base check runs unchanged under the overlay's `clause`; `short_name` defaults to the base's."""

    base_check_id: str
    clause: str
    short_name: str | None = None


@dataclass(frozen=True, slots=True)
class Overridden:
    """The overlay's own `check` replaces the base check `base_check_id`."""

    base_check_id: str
    check: Check


@dataclass(frozen=True, slots=True)
class Added:
    """An overlay check with no base counterpart; its clause maps to null or is absent from the clause map."""

    check: Check


@dataclass(frozen=True, slots=True)
class Removed:
    """The base check is not available under the overlay; a lookup of its overlay id names the `reason`."""

    base_check_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class InheritedCheck(Check):
    """A check derived from `base` by an `Inherited` entry; the content hash includes the base's hash."""

    base: Check


Entry = Inherited | Overridden | Added | Removed


def _noting(check: Check, text: str) -> tuple[tuple[Any, ...], Any]:
    """Return the preconditions and body of `check` with the inheritance note added before anything else runs."""
    if check.preconditions:
        first, *rest = check.preconditions

        def noted(inp: Any, t: Any) -> bool:
            t.note(text)
            return first.test(inp, t)

        return (replace(first, test=noted), *rest), check.body

    def body(inp: Any, t: Any) -> None:
        t.note(text)
        check.body(inp, t)

    return (), body


@dataclass(frozen=True, slots=True)
class Overlay:
    """Entries over a base pack: `clause_map` maps an overlay clause to a base clause (None for an overlay-only one)."""

    base: str
    clause_map: Mapping[str, str | None]
    entries: tuple[Entry, ...]

    def __post_init__(self) -> None:
        """Freeze the clause map and check the entry types.

        Raises:
            CheckDefinitionError: an entry is not an `Inherited`, `Overridden`, `Added` or `Removed`.
        """
        if not all(isinstance(e, Inherited | Overridden | Added | Removed) for e in self.entries):
            raise CheckDefinitionError("overlay entries must be Inherited, Overridden, Added or Removed objects")
        object.__setattr__(self, "clause_map", MappingProxyType(dict(self.clause_map)))

    def _mapped(self, check_id: str, clause: str, base: Check | None) -> None:
        """Check an overlay clause against the map: the base check's first clause, or null for an added check."""
        expected = None if base is None else base.meta.clauses[0]
        if clause not in self.clause_map:
            if base is not None:
                raise CheckDefinitionError(f"{check_id}: overlay clause {clause!r} is not in the clause map")
        elif self.clause_map[clause] != expected:
            raise CheckDefinitionError(
                f"{check_id}: overlay clause {clause!r} maps to {self.clause_map[clause]!r}, expected {expected!r}"
            )

    def _derive(self, pack: Pack, base: Check, entry: Inherited) -> InheritedCheck:
        """Build the check an `Inherited` entry stands for."""
        short = entry.short_name or base.meta.check_id.rpartition(".")[2]
        check_id = f"{pack.name}.{clause_token(entry.clause)}.{short}"
        self._mapped(check_id, entry.clause, base)
        fields = base.meta.model_dump() | {
            "check_id": check_id,
            "pack": pack.name,
            "code": pack.code,
            "edition": pack.edition,
            "clauses": (entry.clause,),
        }
        note = (
            f"inherited from {base.meta.check_id}: {pack.code} {entry.clause} "
            f"mapped to {base.meta.code} {base.meta.clauses[0]}"
        )
        preconditions, body = _noting(base, note)
        return InheritedCheck(CheckMeta(**fields), base.inputs, preconditions, body, base.module, base)

    def resolve(self, pack: Pack, base: Pack) -> tuple[tuple[Check, ...], dict[str, str]]:
        """Validate the overlay of `pack` against its `base` pack.

        Returns the derived inherited checks and `{overlay check id: removal reason}` of the removed ones; the id of a
        removed check is the base id with the base pack name replaced by the overlay's.

        Raises:
            CheckDefinitionError: AC17 (an entry names an unknown base check, a base check has no entry or more than
                one), AC19 (clause map), or the pack's own checks are not exactly the Overridden and Added ones.
        """
        if self.base != base.name:
            raise CheckDefinitionError(f"{pack.name}: overlay base {self.base!r} is not the pack {base.name!r}")
        known = {c.meta.check_id: c for c in base.checks}
        seen: set[str] = set()
        derived: list[Check] = []
        removed: dict[str, str] = {}
        own: list[Check] = []
        for entry in self.entries:
            if isinstance(entry, Added):
                self._mapped(entry.check.meta.check_id, entry.check.meta.clauses[0], None)
                own.append(entry.check)
                continue
            if entry.base_check_id not in known:
                raise CheckDefinitionError(f"{pack.name}: overlay entry names unknown base check {entry.base_check_id}")
            if entry.base_check_id in seen:
                raise CheckDefinitionError(f"{pack.name}: base check {entry.base_check_id} has more than one entry")
            seen.add(entry.base_check_id)
            target = known[entry.base_check_id]
            if isinstance(entry, Inherited):
                derived.append(self._derive(pack, target, entry))
            elif isinstance(entry, Overridden):
                self._mapped(entry.check.meta.check_id, entry.check.meta.clauses[0], target)
                own.append(entry.check)
            else:
                removed[f"{pack.name}.{entry.base_check_id.partition('.')[2]}"] = entry.reason
        if missing := sorted(set(known) - seen):
            raise CheckDefinitionError(f"{pack.name}: base checks without an overlay entry: {', '.join(missing)}")
        if sorted(c.meta.check_id for c in own) != sorted(c.meta.check_id for c in pack.checks):
            raise CheckDefinitionError(f"{pack.name}: own checks must be exactly the Overridden and Added checks")
        return tuple(derived), removed
