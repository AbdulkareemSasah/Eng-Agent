"""CSI adapter gap registries (plan 0008 T3 / plan 0012 T3; spec 0008 §4.8, spec 0012 §4.5).

Purpose: hold the SAFE (`SG-1` to `SG-9`) and SAP2000 (`SP-1` to `SP-8`) gap identifiers and messages
(`NotImplementedGap`). SAFE T3 wires only SG-1 (new model); SAP2000 T3 wires only SP-1 (new model). Later tasks wire
the remaining ids to their steps. No units are involved. Product-specific registries and step wiring live on each
`ProductProfile` (spec 0008 AC2); this module re-exports them and asks the profile for a product's step gap.
"""

from collections.abc import Mapping
from typing import NoReturn

from eng_harness.adapters.csi.products import _safe, _sap2000, profile
from eng_harness.errors import NotImplementedGap

__all__ = [
    "SAFE_GAPS",
    "SAP2000_GAPS",
    "SAP2000_STEP_GAPS",
    "STEP_GAPS",
    "new_model",
    "raise_gap",
    "refuse_step",
]

SAFE_GAPS: Mapping[str, str] = _safe.GAPS
SAP2000_GAPS: Mapping[str, str] = _sap2000.GAPS
STEP_GAPS: Mapping[str, str] = _safe.STEP_GAPS
SAP2000_STEP_GAPS: Mapping[str, str] = _sap2000.STEP_GAPS

_GAPS: Mapping[str, str] = {**SAFE_GAPS, **SAP2000_GAPS}


def raise_gap(gap_id: str) -> NoReturn:
    """Raise `NotImplementedGap` for `gap_id`; `KeyError` for an unknown gap identifier."""
    raise NotImplementedGap(_GAPS[gap_id], evidence=(gap_id,))


def refuse_step(step: str, *, product: str | None = None) -> NoReturn:
    """Raise the `NotImplementedGap` wired to `step` for `product`; `KeyError` when none is wired.

    When `product` is omitted, the historical SAFE step wiring (`STEP_GAPS`) applies. When given, the product's
    profile supplies `step_gaps` (spec 0008 AC2: shared code asks the profile, never branches on a product name).
    """
    step_gaps = STEP_GAPS if product is None else profile(product).step_gaps
    raise_gap(step_gaps[step])


def new_model(*, product: str | None = None) -> NoReturn:
    """Refuse creating a new model (SG-1 or SP-1); nothing is sent to the host."""
    refuse_step("new_model", product=product)
