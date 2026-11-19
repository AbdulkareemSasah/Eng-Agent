"""SAFE adapter gap registry (plan 0008 T3; spec 0008 section 4.8, AC8, amendment B-418).

Purpose: hold the SG-1 to SG-9 gap identifiers and messages (`NotImplementedGap`); T3 wires only SG-1 (new model)
to a step, while SG-2 to SG-5 and SG-9 are wired in T7 and SG-7/SG-8 in T6. No units are involved.
"""

from collections.abc import Mapping
from typing import NoReturn

from eng_harness.errors import NotImplementedGap

__all__ = ["SAFE_GAPS", "STEP_GAPS", "new_model", "raise_gap", "refuse_step"]

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

STEP_GAPS: Mapping[str, str] = {
    "new_model": "SG-1",
}


def raise_gap(gap_id: str) -> NoReturn:
    """Raise `NotImplementedGap` for `gap_id`; `KeyError` for an unknown gap identifier."""
    raise NotImplementedGap(SAFE_GAPS[gap_id], evidence=(gap_id,))


def refuse_step(step: str) -> NoReturn:
    """Raise the `NotImplementedGap` wired to `step`; `KeyError` when no gap is wired to `step`."""
    raise_gap(STEP_GAPS[step])


def new_model() -> NoReturn:
    """Refuse creating a new model (gap SG-1, spec 0008 AC8); nothing is sent to the host."""
    refuse_step("new_model")
