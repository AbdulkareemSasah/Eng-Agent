"""CSI product profiles and the product of a model file (spec 0002 section 4.6.5, spec 0008 section 4.1).

A profile is the only product-specific code; a shared module asks it and never branches on a product name. Resolving
the product of a model by its file extension fails with `INVALID_ARGUMENT` (`field: model`) before any call.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PureWindowsPath

from eng_contract.errors import ContractError, ErrorCode

from eng_harness.adapters.csi.products import _etabs, _safe, _sap2000

__all__ = ["ProductProfile", "product_of_model", "profile"]


@dataclass(frozen=True, slots=True)
class ProductProfile:
    """Per-product tables, model file extensions, companion files and gap registries."""

    name: str
    model_extensions: tuple[str, ...]  # upper case, with the dot
    tables: Mapping[str, str]
    readback: Mapping[str, tuple[str, str, str]]  # read-back tables: (table, key column, value column)
    companion_globs: tuple[str, ...] = ()  # files next to the model file that belong to it; empty until local test L2
    gaps: Mapping[str, str] = field(default_factory=dict)  # gap id → message; empty until the product lists gaps
    step_gaps: Mapping[str, str] = field(default_factory=dict)  # step name → gap id wired for that product
    # Kind list keys the state reader skips (spec 0012 AC8); empty when the product has none.
    declared_absences: tuple[str, ...] = ()


_ETABS = ProductProfile("ETABS", _etabs.MODEL_EXTENSIONS, _etabs.TABLES, _etabs.READBACK)
# Companion globs stay empty until each product's local test L2 (spec 0008 4.1, spec 0012 4.3).
_SAFE = ProductProfile(
    "SAFE",
    _safe.MODEL_EXTENSIONS,
    _safe.TABLES,
    _safe.READBACK,
    _safe.COMPANION_GLOBS,
    _safe.GAPS,
    _safe.STEP_GAPS,
)
_SAP2000 = ProductProfile(
    "SAP2000",
    _sap2000.MODEL_EXTENSIONS,
    _sap2000.TABLES,
    _sap2000.READBACK,
    _sap2000.COMPANION_GLOBS,
    _sap2000.GAPS,
    _sap2000.STEP_GAPS,
    _sap2000.DECLARED_ABSENCES,
)
_PROFILES = {item.name: item for item in (_ETABS, _SAFE, _SAP2000)}


def profile(name: str) -> ProductProfile:
    """Return the profile; `KeyError` when the product has none."""
    return _PROFILES[name]


def product_of_model(model: str, server_product: str | None = None) -> ProductProfile:
    """The profile of the product that owns the model file, by its extension (spec 0008 AC2).

    Args:
        model: The model file name or path; either path separator and any letter case of the extension.
        server_product: The product of the server the step addresses, when known.

    Raises:
        ContractError: `INVALID_ARGUMENT` (`field: model`) for an unknown extension, or for a product other than
            `server_product`.
    """
    path = PureWindowsPath(model)
    found = next((item for item in _PROFILES.values() if path.suffix.upper() in item.model_extensions), None)
    name = path.name or model
    if found is None:
        known = ", ".join(sorted(ext for item in _PROFILES.values() for ext in item.model_extensions))
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT, f"model: {name} has no known model extension ({known})", field="model"
        )
    if server_product is not None and found.name != server_product:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            f"model: {name} is a {found.name} model, the server serves {server_product}",
            field="model",
        )
    return found
