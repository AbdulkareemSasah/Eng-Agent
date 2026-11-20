"""Steps 16 and 17 of the edit cycle: promotion and sign-off, and the turn-only path (spec 0007 4.5; plan 0007 T9b).

Purpose: `promote_revision` (PROMOTION then `ctx.promote` with the model key), `sign_off_run` (SIGN_OFF with the
output refs), and `engineer_turn_only` (the engineer turn when steps 5 to 14 were skipped: locked model or
`stop_cycle` / rejected set). Exception items of the sign-off are plan 0007 T9c.
Units: none; values move by reference.
Errors: `CONFLICT` from promotion when the original changed since the copy; the step errors of the ctx calls reach
the engine unchanged.
"""

from typing import Any

from eng_contract.errors import ErrorCode
from eng_contract.refs import Ref
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict

from eng_harness.block import block
from eng_harness.ctx import ApprovalKind, ModelHandle, Preview, PreviewItem, Promotion
from eng_harness.workflows.model_edit_cycle._points import TURN_POLICY, TurnAction, TurnState

__all__ = [
    "FinishInput",
    "PromoteInput",
    "PromoteOutput",
    "SignOffInput",
    "SignOffOutput",
    "TurnOnlyInput",
    "TurnOnlyOutput",
    "engineer_turn_only",
    "promote_revision",
    "sign_off_run",
]


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TurnOnlyInput(_M):
    """What the turn-only path needs: statuses, labels and refs (status of a locked read, or the summaries so far)."""

    readback_status: VerdictStatus = VerdictStatus.NOT_APPLICABLE
    analysis_status: VerdictStatus = VerdictStatus.NOT_APPLICABLE
    design_status: VerdictStatus = VerdictStatus.NOT_APPLICABLE
    refs: tuple[Ref, ...] = ()


class TurnOnlyOutput(_M):
    """The engineer turn choice."""

    turn: TurnAction


class PromoteInput(_M):
    """The model key to promote (spec 0007 4.5 step 16; plan 0001 T23)."""

    model: str


class PromoteOutput(_M):
    """The promoted model handle and the accepted revision identity from the promotion's model_saved."""

    promoted: ModelHandle
    model_id: str
    revision: int
    fingerprint: str
    file_sha256: str


class SignOffInput(_M):
    """The output references shown on the sign-off preview (spec 0007 4.5 step 17)."""

    outputs: tuple[tuple[str, Ref], ...]


class SignOffOutput(_M):
    """Whether the engineer signed the run."""

    signed: bool


class FinishInput(_M):
    """Unused placeholder kept for a stable import surface; prefer the per-step inputs."""

    model: str


@block(name="engineer_turn_only", version=1)
async def engineer_turn_only(ctx: Any, inp: TurnOnlyInput) -> TurnOnlyOutput:
    """The engineer turn when steps 5 to 14 were skipped (locked model or stop_cycle / rejected set)."""
    turn = await ctx.decide(
        "edit_cycle_engineer_turn",
        TurnAction,
        TurnState(
            readback_status=inp.readback_status,
            analysis_status=inp.analysis_status,
            design_status=inp.design_status,
            counts=(
                f"readback {inp.readback_status}",
                f"analysis {inp.analysis_status}",
                f"design {inp.design_status}",
            ),
            refs=inp.refs,
        ),
        (),
        TURN_POLICY,
    )
    return TurnOnlyOutput(turn=turn.choice)


@block(name="promote_revision", version=1)
async def promote_revision(ctx: Any, inp: PromoteInput) -> PromoteOutput:
    """Step 16: always-ask PROMOTION, then promote the working copy over the original by file copy."""
    shown = Preview(
        items=(PreviewItem(id="promote", label="Promote the accepted revision over the original", refs=()),),
        diff_ref=None,
        models=(inp.model,),
    )
    approval = await ctx.approve("Promote the accepted revision", shown, kind=ApprovalKind.PROMOTION)
    try:
        promoted = await ctx.promote(inp.model, Promotion.FILE_COPY, approval)
    except Exception as exc:
        # AC21 / engine AC52: CONFLICT when the original changed; escalate so the run is NEEDS_ENGINEER.
        # ContractError is not an allowed block import; read the envelope the contract attaches.
        detail = getattr(exc, "detail", None)
        if detail is not None and getattr(detail, "code", None) is ErrorCode.CONFLICT:
            await ctx.escalate(str(getattr(detail, "message", "")), ())
        raise
    # Identity of the accepted revision: the binding state the promotion used (host-reported).
    return PromoteOutput(
        promoted=promoted,
        model_id=promoted.model_id,
        revision=promoted.revision,
        fingerprint="",  # filled from the journaled model_saved by the workflow when present
        file_sha256="",
    )


@block(name="sign_off_run", version=1)
async def sign_off_run(ctx: Any, inp: SignOffInput) -> SignOffOutput:
    """Step 17: always-ask SIGN_OFF with the run outputs; exception items are plan 0007 T9c."""
    built: list[PreviewItem] = []
    for label, ref in inp.outputs:
        built.append(PreviewItem(id=f"out_{len((*built, None))}", label=label, refs=(ref,)))
    items = tuple(built)
    shown = Preview(items=items, diff_ref=None, models=())
    approval = await ctx.approve("Sign off the run", shown, kind=ApprovalKind.SIGN_OFF)
    return SignOffOutput(signed=approval.approved)
