"""Deep helper: imports a sibling with `from . import` and a parent module with `from .. import`."""

from .. import consts
from . import leaf


def scale(value: float) -> float:
    """Return the value times the scale and the leaf offset."""
    return value * consts.SCALE + leaf.OFFSET
