"""SAFE adapter gap registry (plan 0008 T3, T7; spec 0008 section 4.8, AC8, AC24, AC25, amendment B-418).

Purpose: hold the SG-1 to SG-9 gap identifiers and messages (`NotImplementedGap`); T3 wires SG-1 (new model), T6
raises SG-7 and SG-8 from the load import, T7 wires SG-2 to SG-5 and SG-9 to steps and raises SG-6 as LIMIT_EXCEEDED on
soil-pressure truncation. No units are involved.
"""

from collections.abc import Mapping
from typing import NoReturn

from eng_harness.errors import NotImplementedGap

__all__ = [
    "SAFE_GAPS",
    "STEP_GAPS",
    "area_forces",
    "define_area_spring",
    "define_slab_section",
    "design_results",
    "new_model",
    "raise_gap",
    "refuse_step",
    "resize_area",
    "slab_design",
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

STEP_GAPS: Mapping[str, str] = {
    "new_model": "SG-1",
    "define_slab_section": "SG-2",
    "define_area_spring": "SG-3",
    "resize_area": "SG-4",
    "slab_design": "SG-5",
    "design_results": "SG-5",
    "area_forces": "SG-9",
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


def define_slab_section() -> NoReturn:
    """Refuse defining a footing slab section (gap SG-2, AC25); nothing is sent."""
    refuse_step("define_slab_section")


def define_area_spring() -> NoReturn:
    """Refuse defining or assigning an area spring (gap SG-3, AC25); nothing is sent."""
    refuse_step("define_area_spring")


def resize_area() -> NoReturn:
    """Refuse resizing or moving a footing area (gap SG-4, AC25); nothing is sent."""
    refuse_step("resize_area")


def slab_design() -> NoReturn:
    """Refuse SAFE slab design run (gap SG-5, AC24); nothing is sent."""
    refuse_step("slab_design")


def design_results() -> NoReturn:
    """Refuse reading SAFE design results (gap SG-5, AC24); nothing is sent."""
    refuse_step("design_results")


def area_forces() -> NoReturn:
    """Refuse FE slab forces, strips and displacements (gap SG-9, AC25); nothing is sent."""
    refuse_step("area_forces")
