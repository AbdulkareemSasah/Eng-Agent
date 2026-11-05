"""Block-safe types of the decision layer (spec 0005 section 4.1 and 4.2).

Imports nothing from ``engine``, ``journal`` or ``ports`` (AC42); workflow blocks and rule modules may import it.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from pydantic import StringConstraints

from eng_harness.decisions._policy import DecisionPolicy

__all__ = ["DecisionDefinitionError", "DecisionPolicy", "Label", "Pick", "Rationale"]

# AC2: 1 to 80 characters, no control character, none of / \ @ : (a path, URL or address cannot be a label).
Label = Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f-\x9f/\\@:]+$")]

# AC2: 1 to 300 characters, no digit in any script (the form gate rule FB006 probes).
Rationale = Annotated[str, StringConstraints(min_length=1, max_length=300, pattern=r"^\D+$")]


class DecisionDefinitionError(ValueError):
    """An invalid point, rule or policy definition, raised at import or registration (spec 6)."""


@dataclass(frozen=True, slots=True)
class Pick[T: (StrEnum, int)]:
    """A rule's choice: an enum member, or an index into reference options (never a number, P10)."""

    option: T
