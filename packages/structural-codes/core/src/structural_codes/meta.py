"""Check metadata and the check_id rule (spec 0001 section 4.2).

Purpose: `CheckMeta` describes a check; invalid metadata raises `CheckDefinitionError`, never a pydantic error.
"""

import re
from typing import Annotated, Any, Self

from eng_contract.verdicts import CODE_PACK_CHECK_ID, SubjectKind
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

from structural_codes.errors import CheckDefinitionError

__all__ = ["CheckMeta", "GapDecl", "clause_token"]

_Clause = Annotated[str, StringConstraints(min_length=1, max_length=40)]
_SPEC_PATH = re.compile(r"(?:[A-Za-z0-9_-][A-Za-z0-9_.-]*/)*[A-Za-z0-9_.-]*[A-Za-z0-9_-]\.md")


def clause_token(clause: str) -> str:
    """Return the check_id segment of a clause number as printed in the code.

    Lower-cases, replaces each run of characters outside `[0-9a-z]` with `_` and strips leading and trailing `_`;
    `"21.2.1(b)"` gives `"21_2_1_b"`. Pure; no errors.
    """
    return re.sub(r"[^0-9a-z]+", "_", clause.lower()).strip("_")


class _Frozen(BaseModel):
    """Base: frozen, no extra fields, and validation errors surface as `CheckDefinitionError`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, **data: Any) -> None:
        """Validate.

        Raises:
            CheckDefinitionError: any field is missing, malformed or out of bounds.
        """
        try:
            super().__init__(**data)
        except ValidationError as exc:
            fields = ", ".join(sorted({".".join(str(p) for p in e["loc"]) or "model" for e in exc.errors()}))
            raise CheckDefinitionError(f"invalid {type(self).__name__}: {fields}: {exc}") from exc


class GapDecl(_Frozen):
    """A declared gap of a check: an id `G-<n>`, the clause concerned and the reason (own words)."""

    id: Annotated[str, StringConstraints(pattern=r"^G-[0-9]+$")]
    clause: _Clause
    reason: Annotated[str, StringConstraints(min_length=1)]


class CheckMeta(_Frozen):
    """Metadata of a check (spec 4.2); `check_id` is `<pack>.<clause_token(clauses[0])>.<short_name>`.

    `version` is the check's own integer version (>= 1), carried by a calc route as `CalcInfo.version`.
    """

    check_id: Annotated[str, StringConstraints(max_length=200)]
    pack: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
    code: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    edition: Annotated[str, StringConstraints(min_length=1, max_length=20)]
    clauses: tuple[_Clause, ...] = ()
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    title_ar: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    members: frozenset[SubjectKind]
    spec: str
    gaps: tuple[GapDecl, ...] = ()
    assumptions: tuple[Annotated[str, StringConstraints(max_length=500)], ...] = ()
    unconditional: Annotated[str, StringConstraints(min_length=1, max_length=500)] | None = None
    version: Annotated[int, Field(strict=True, ge=1)] = 1

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if not self.clauses:
            raise ValueError("clauses must not be empty")
        if not self.members:
            raise ValueError("members must not be empty")
        if not _SPEC_PATH.fullmatch(self.spec) or ".." in self.spec.split("/"):
            raise ValueError("spec must be a relative POSIX path ending in .md")
        if not re.fullmatch(CODE_PACK_CHECK_ID, self.check_id):
            raise ValueError("check_id does not match the contract pattern")
        pack, clause, _short = self.check_id.split(".")
        if pack != self.pack:
            raise ValueError(f"check_id must start with the pack {self.pack!r}")
        if clause != clause_token(self.clauses[0]):
            raise ValueError(f"check_id clause segment must be {clause_token(self.clauses[0])!r}")
        ids = [g.id for g in self.gaps]
        for gap_id in sorted(set(ids)):
            if ids.count(gap_id) > 1:
                raise ValueError(f"gap {gap_id} is declared twice")
        return self
