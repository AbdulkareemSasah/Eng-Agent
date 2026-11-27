"""First helper: a relative import of a sub-package module."""

from .sub import deep


def double(value: float) -> float:
    """Return twice the value through the deeper helper."""
    return deep.scale(value)
