"""Block-safe types of the decision layer (spec 0005 section 4.1 and 4.2).

Imports nothing from ``engine``, ``journal`` or ``ports`` (AC42); workflow blocks and rule modules may import it.
"""

from dataclasses import dataclass
from enum import StrEnum

from eng_harness.decisions._points import DecisionDefinitionError, DecisionPoint, Label, Refs, decision_point
from eng_harness.decisions._policy import DecisionPolicy
from eng_harness.decisions._rules import Rationale, Rule, RuleBasis, rule

__all__ = [
    "DecisionDefinitionError",
    "DecisionPoint",
    "DecisionPolicy",
    "Label",
    "Pick",
    "Rationale",
    "Refs",
    "Rule",
    "RuleBasis",
    "decision_point",
    "rule",
]


@dataclass(frozen=True, slots=True)
class Pick[T: StrEnum | int]:
    """A rule's choice: an enum member, or an index into reference options (never a number, P10)."""

    option: T
