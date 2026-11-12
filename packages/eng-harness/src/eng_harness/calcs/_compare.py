"""Tolerance comparison for model diffs (spec 0003 4.7 rules D3 and D4).

Purpose: decide whether two numeric leaves are equal within a basis tolerance (D3) using exact `Fraction` arithmetic.
D4 (exact compare) is equality in the diff walker. Units: tolerance is in the leaf field's canonical unit.
Errors: none.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

__all__ = ["as_fraction", "within_tolerance"]


def as_fraction(value: Any) -> Fraction | None:
    """Take the exact binary value of a JSON number; booleans and non-numbers give `None`."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        return Fraction(value)
    return None


def within_tolerance(before: Any, after: Any, tolerance: Fraction) -> bool:
    """D3: equal when |after - before| <= tolerance, exactly; a tolerance of zero requires exact equality."""
    left, right = as_fraction(before), as_fraction(after)
    if left is None or right is None:
        return False
    return abs(right - left) <= tolerance
