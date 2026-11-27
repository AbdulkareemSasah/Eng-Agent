"""The model edit cycle workflow (spec 0007): definition, basis fields and steps 1 to 10 (plan 0007 T8).

Purpose: `model_edit_cycle` (version 1) with its input and output models and the design basis fields of spec 0007
4.8, which are the blank template's `ask_each_run` list; the change-set model (plan 0007 T1b) and the child blocks of
`_cycle.py`. Steps 11 to 17, the cycle loop and the registration of the workflow are plan 0007 T9a and T9b.
Units: the quantity fields carry the canonical unit of their name's suffix (contract 4.7.2).
Errors: `RegistryError` at import for an invalid declaration; the step errors of the ctx calls reach the engine.
"""

from typing import Any

from eng_contract.refs import Ref
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict

from eng_harness.block import FieldSpec, ModelFile, workflow
from eng_harness.ctx import ModelHandle
from eng_harness.workflows.model_edit_cycle._change_set import (
    REFUSED_KIND_GAPS,
    ChangeSetDraft,
    ChangeSetSettings,
    refused_gap,
)
from eng_harness.workflows.model_edit_cycle._cycle import (
    ChangeSetRequest,
    CycleInput,
    Route,
    SummarizeInput,
    apply_change_set,
    edit_cycle_once,
    obtain_change_set,
    read_state,
    run_and_summarize,
)
from eng_harness.workflows.model_edit_cycle._finish import (
    PromoteInput,
    SignOffInput,
    TurnOnlyInput,
    engineer_turn_only,
    promote_revision,
    sign_off_run,
)
from eng_harness.workflows.model_edit_cycle._points import TurnAction

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
    "engineer_turn_only",
    "model_edit_cycle",
    "obtain_change_set",
    "promote_revision",
    "read_state",
    "refused_gap",
    "run_and_summarize",
    "sign_off_run",
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

    model: ModelFile
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
    """Steps 2 to 17: open, the cycle loop, promotion and sign-off (spec 0007 4.5; plan 0007 T9b)."""
    model = inp.model.name
    await ctx.tool("csi_open_model", {"model": model})
    previous = None
    designs: dict[str, Any] = {}
    ask = True
    done: list[Any] = []
    summary_refs: list[Any] = []
    analysis_ref = None
    file_sha256 = ""
    fingerprint = ""
    async for _ in ctx.attempts(ctx.basis.count("attempts.cycles")):
        out = await ctx.block(edit_cycle_once, CycleInput(model=model, previous=previous, ask=ask))
        done.append(out)
        previous = out.state
        if out.route is Route.DONE:
            if out.snapshot_sha256:
                file_sha256 = out.snapshot_sha256
            if out.fingerprint:
                fingerprint = out.fingerprint
            summarized = await ctx.block(
                run_and_summarize,
                SummarizeInput(
                    model=model,
                    state=out.state,
                    diff=out.diff,
                    readback=out.readback,
                    previous_designs=tuple(designs.items()),
                ),
            )
            designs = dict(summarized.designs)
            analysis_ref = summarized.analysis
            summary_refs = [summarized.analysis, *(ref for _, ref in summarized.designs)]
            turn = summarized.turn
        elif out.route in (Route.STOPPED, Route.REJECTED):
            refs = (out.state.status, out.diff) if out.route is Route.STOPPED else (out.diff,)
            if out.readback is not None:
                refs = (out.readback, *refs)
            only = await ctx.block(
                engineer_turn_only,
                TurnOnlyInput(
                    readback_status=(
                        VerdictStatus.NOT_APPLICABLE if out.readback is None else VerdictStatus.NEEDS_ENGINEER
                    ),
                    refs=refs,
                ),
            )
            turn = only.turn
        else:
            only = await ctx.block(engineer_turn_only, TurnOnlyInput(refs=(out.diff,)))
            turn = only.turn
        if turn is TurnAction.ACCEPT:
            break
        ask = turn is TurnAction.MORE_EDITS
    promoted_out = await ctx.block(promote_revision, PromoteInput(model=model))
    outputs: list[tuple[str, Any]] = []
    if analysis_ref is not None:
        outputs.append(("Analysis summary", analysis_ref))
    outputs.extend((f"Design summary ({kind})", ref) for kind, ref in designs.items())
    signed = await ctx.block(sign_off_run, SignOffInput(outputs=tuple(outputs)))
    if not file_sha256:
        file_sha256 = promoted_out.file_sha256
    if not fingerprint:
        fingerprint = promoted_out.fingerprint or file_sha256
    return EditCycleOutput(
        accepted_revision=AcceptedRevision(
            model_id=promoted_out.model_id,
            revision=promoted_out.revision,
            fingerprint=fingerprint,
            file_sha256=file_sha256,
        ),
        cycles=len(done),
        promoted=promoted_out.promoted,
        summaries=tuple(summary_refs),
        signed=signed.signed,
    )
