"""CSI adapter gap registries (plan 0008 T3 / plan 0012 T3; spec 0008 §4.8, spec 0012 §4.5).

Purpose: hold the SAFE (`SG-1` to `SG-9`) and SAP2000 (`SP-1` to `SP-8`) gap identifiers and messages
(`NotImplementedGap`). SAFE T3 wires only SG-1 (new model); SAP2000 T3 wires only SP-1 (new model). Later tasks wire
the remaining ids to their steps. No units are involved.
"""

from collections.abc import Mapping
from typing import NoReturn

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

SAFE_GAPS: Mapping[str, str] = {
    "SG-1": "creating a new model is not implemented: provide a prepared model",
    "SG-2": "defining or changing a footing slab section is not implemented",
    "SG-3": "defining or assigning an area spring soil support is not implemented",
    "SG-4": "resizing or moving a footing area is not implemented",
    "SG-5": "slab design run and punching or flexure results are not implemented",
    "SG-6": "soil pressure table reads beyond 2000 rows require per-footing groups",
    "SG-7": "setting column punching dimensions (XDim, YDim) on a point load is not implemented",
    "SG-8": "clearing a joint load with an all-zero assignment is not implemented",
    "SG-9": "FE slab forces, strip results and displacements are not implemented",
}

# Spec 0012 section 4.5 gap table (messages paraphrase the Missing column; way-out is not a message).
SAP2000_GAPS: Mapping[str, str] = {
    "SP-1": "creating a new model is not implemented: provide a prepared model",
    "SP-2": "defining sections, materials or load cases is not implemented",
    "SP-3": "concrete design results for frames that are not beams are not implemented",
    "SP-4": "table-based reads and the edits that need them are not implemented",
    "SP-5": "design orientation, frame labels and local axes are not implemented",
    "SP-6": "choosing which load cases an analysis runs is not implemented",
    "SP-7": "levels and grids are not implemented",
    "SP-8": "cable, link and general-shell workflows are not implemented",
}

_GAPS: Mapping[str, str] = {**SAFE_GAPS, **SAP2000_GAPS}

STEP_GAPS: Mapping[str, str] = {
    "new_model": "SG-1",
}

SAP2000_STEP_GAPS: Mapping[str, str] = {
    "new_model": "SP-1",
}


def raise_gap(gap_id: str) -> NoReturn:
    """Raise `NotImplementedGap` for `gap_id`; `KeyError` for an unknown gap identifier."""
    raise NotImplementedGap(_GAPS[gap_id], evidence=(gap_id,))


def refuse_step(step: str, *, product: str = "SAFE") -> NoReturn:
    """Raise the `NotImplementedGap` wired to `step` for `product`; `KeyError` when none is wired."""
    if product == "SAP2000":
        raise_gap(SAP2000_STEP_GAPS[step])
    raise_gap(STEP_GAPS[step])


def new_model(*, product: str = "SAFE") -> NoReturn:
    """Refuse creating a new model (SG-1 or SP-1); nothing is sent to the host."""
    refuse_step("new_model", product=product)
