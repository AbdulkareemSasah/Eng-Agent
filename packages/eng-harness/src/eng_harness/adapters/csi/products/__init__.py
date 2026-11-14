"""CSI product profiles (spec 0002 section 4.6.5)."""

from collections.abc import Mapping
from dataclasses import dataclass

from eng_harness.adapters.csi.products import _etabs

__all__ = ["ProductProfile", "profile"]


@dataclass(frozen=True, slots=True)
class ProductProfile:
    """Per-product tables and model file extensions."""

    name: str
    model_extensions: tuple[str, ...]
    tables: Mapping[str, str]
    readback: Mapping[str, tuple[str, str, str]]  # read-back tables: (table, key column, value column)


_ETABS = ProductProfile("ETABS", _etabs.MODEL_EXTENSIONS, _etabs.TABLES, _etabs.READBACK)


def profile(name: str) -> ProductProfile:
    """Return the profile; `KeyError` when the product has none."""
    if name == "ETABS":
        return _ETABS
    raise KeyError(name)
