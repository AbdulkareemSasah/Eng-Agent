"""The model edit cycle workflow (spec 0007): definition, basis fields and steps 1 to 10 (plan 0007 T8).

Purpose: `model_edit_cycle` (version 1) with its input and output models and the design basis fields of spec 0007
4.8, which are the blank template's `ask_each_run` list; the change-set model (plan 0007 T1b) and the child blocks of
`_cycle.py`. Steps 11 to 17 and the registration of the workflow come with plan 0007 T9a and T9b.
Units: the quantity fields carry the canonical unit of their name's suffix (contract 4.7.2).
Errors: `RegistryError` at import for an invalid declaration; the step errors of the ctx calls reach the engine.
"""

from pathlib import Path
from typing import Any

from eng_contract.refs import Ref
from pydantic import BaseModel, ConfigDict

from eng_harness.block import FieldSpec, workflow
from eng_harness.ctx import ModelHandle
from eng_harness.errors import NotImplementedGap
from eng_harness.workflows.model_edit_cycle._change_set import (
    REFUSED_KIND_GAPS,
    ChangeSetDraft,
    ChangeSetSettings,
    refused_gap,
)
from eng_harness.workflows.model_edit_cycle._cycle import (
    ChangeSetRequest,
    CycleInput,
    apply_change_set,
    edit_cycle_once,
    obtain_change_set,
    read_state,
)

__all__ = [
    "BASIS_FIELDS",
    "CSI_BUILD",
    "REFUSED_KIND_GAPS",
    "AcceptedRevision",
    "ChangeSetDraft",
    "ChangeSetRequest",
    "ChangeSetSettings",
    "EditCycleInput",
    "EditCycleOutput",
    "apply_change_set",
    "edit_cycle_once",
    "model_edit_cycle",
    "obtain_change_set",
    "read_state",
    "refused_gap",
]

CSI_BUILD = "61da80f61a6562c8e3553168056bc107e3f93013"
"""The Sasaah CSI server build pinned in `adapters/csi/_allowlist.toml` (block code may not import the adapter)."""


def _quantity(path: str, label: str, unit: str) -> FieldSpec:
    return FieldSpec(path=path, kind="quantity", label=label, unit=unit)


def _count(path: str, label: str) -> FieldSpec:
    return FieldSpec(path=path, kind="count", label=label)


BASIS_FIELDS: tuple[FieldSpec, ...] = (
    _quantity("compare.length_mm", "Comparison tolerance of lengths", "mm"),
    _quantity("compare.angle_deg", "Comparison tolerance of angles", "deg"),
    _quantity("compare.stress_MPa", "Comparison tolerance of stresses", "MPa"),
    _quantity("compare.unit_weight_kN_m3", "Comparison tolerance of unit weights", "kN/m3"),
    _quantity("compare.line_load_kN_m", "Comparison tolerance of line loads", "kN/m"),
    _quantity("compare.area_load_kPa", "Comparison tolerance of area loads", "kPa"),
    _quantity("compare.dimensionless_ratio", "Comparison tolerance of dimensionless values", "1"),
    _quantity("checks.readback_relative_tolerance_ratio", "Relative tolerance of the host read-back check", "1"),
    _count("report.top_n", "Rows of the design summary"),
    _quantity("limits.ratio_limit_ratio", "Limit of the host design ratio", "1"),
    _quantity("limits.drift_ratio", "Limit of the story drift ratio", "1"),
    _quantity("bounds.thickness_min_mm", "Smallest accepted thickness", "mm"),
    _quantity("bounds.thickness_max_mm", "Largest accepted thickness", "mm"),
    _quantity("bounds.line_load_min_kN_m", "Smallest accepted line load", "kN/m"),
    _quantity("bounds.line_load_max_kN_m", "Largest accepted line load", "kN/m"),
    _quantity("bounds.area_load_min_kPa", "Smallest accepted area load", "kPa"),
    _quantity("bounds.area_load_max_kPa", "Largest accepted area load", "kPa"),
    _quantity("bounds.ratio_min_ratio", "Smallest accepted self-weight multiplier or combination scale", "1"),
    _quantity("bounds.ratio_max_ratio", "Largest accepted self-weight multiplier or combination scale", "1"),
    FieldSpec(
        path="design.run",
        kind="choice",
        label="Designs the host runs",
        choices=("steel", "concrete", "steel_and_concrete"),
    ),
    _count("attempts.cycles", "Edit cycles before the run stops"),
    _count("attempts.change_set", "Attempts to obtain a valid change set"),
    _count("attempts.approval_void", "Returns to the model read after a voided approval"),
)
"""The final list of spec 0007 4.8; no value, bound or default (spec 0004 Q8)."""


class EditCycleInput(BaseModel):
    """The model file (absolute path; its base name is the model key) and whether the host window is visible."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: Path
    visible_host: bool = True


class AcceptedRevision(BaseModel):
    """The `model_saved` identity of the accepted revision: model, revision, fingerprint and file hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    revision: int
    fingerprint: str
    file_sha256: str


class EditCycleOutput(BaseModel):
    """What the run delivers: the accepted revision, the cycle count, the promoted model, the last summaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted_revision: AcceptedRevision
    cycles: int
    promoted: ModelHandle
    summaries: tuple[Ref, ...]
    signed: bool


@workflow(
    name="model_edit_cycle",
    version=1,
    description="Edit an existing model on a working copy: read, change set, approval, write, read back, analysis.",
    min_server_builds={"sasaah-csi-mcp": CSI_BUILD},
    always_ask=("csi_unlock_model",),
    basis_fields=BASIS_FIELDS,
    copy_on_open=True,
)
async def model_edit_cycle(ctx: Any, inp: EditCycleInput) -> EditCycleOutput:
    """Step 2, the open of the model, and the first cycle; the rest comes with plan 0007 T9a and T9b."""
    model = inp.model.name
    await ctx.tool("csi_open_model", {"model": model})
    await ctx.block(edit_cycle_once, CycleInput(model=model, previous=None, ask=True))
    raise NotImplementedGap("the edit cycle after step 10 is built by plan 0007 T9a and T9b", evidence=["T9a", "T9b"])
