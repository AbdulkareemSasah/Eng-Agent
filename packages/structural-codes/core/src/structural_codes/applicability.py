"""Declared preconditions of a check (spec 0001 section 4.4).

Purpose: `Precondition` is one reviewed applicability test; the first failing one ends an evaluation with its outcome.
Errors: `CheckDefinitionError` for a malformed precondition.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from structural_codes.errors import CheckDefinitionError

__all__ = ["Outcome", "Precondition"]

_ID = re.compile(r"[A-Z][A-Z0-9_]*")


class Outcome(StrEnum):
    """The verdict status a failed precondition gives."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    NEEDS_ENGINEER = "NEEDS_ENGINEER"


@dataclass(frozen=True, slots=True)
class Precondition:
    """One applicability test: an id `^[A-Z][A-Z0-9_]*$`, its outcome, the clause (1 to 40 characters) and a text.

    `test(inputs, trace)` returns `False` when the precondition fails; both arguments are typed `Any` here because
    the trace recorder is a later module (it receives the check's inputs and its `TraceRecorder`).
    """

    id: str
    outcome: Outcome
    clause: str
    description: str
    test: Callable[[Any, Any], bool]

    def __post_init__(self) -> None:
        """Validate the fields.

        Raises:
            CheckDefinitionError: malformed id, clause or description, or an outcome that is not an `Outcome`.
        """
        if not _ID.fullmatch(self.id):
            raise CheckDefinitionError(f"precondition id {self.id!r} must match {_ID.pattern}")
        if not isinstance(self.outcome, Outcome):
            raise CheckDefinitionError(f"precondition {self.id}: outcome must be an Outcome")
        if not 1 <= len(self.clause) <= 40:
            raise CheckDefinitionError(f"precondition {self.id}: clause must have 1 to 40 characters")
        if not self.description.strip():
            raise CheckDefinitionError(f"precondition {self.id}: description must not be blank")
