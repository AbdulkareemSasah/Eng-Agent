"""Rules of the edit cycle decision points (spec 0007 section 4.6; spec 0005 section 4.4).

Purpose: the two rules that answer D-2 and D-3 without the engineer; both ship `draft` for the owner's review
(spec 0005 Q7). A rule states only what the spec table states, reads no basis path and holds no number.
Units: none. Errors: none; a state outside a rule gives `None` and the next rule, or the engineer, decides.
"""

from eng_contract.verdicts import VerdictStatus

from eng_harness.decisions.types import Pick, RuleBasis, rule
from eng_harness.workflows.model_edit_cycle._points import (
    AnalysisAction,
    AnalysisState,
    ReadbackAction,
    ReadbackReason,
    ReadbackState,
)

__all__ = ["analysis_messages_clean", "readback_result_pass"]


@rule(
    id="edit_cycle_readback_result.pass",
    version=2,
    point="edit_cycle_readback_result",
    rationale="The read-back passed without a model change or failed pre-read check, so the cycle continues.",
)
def readback_result_pass(state: ReadbackState, basis: RuleBasis) -> Pick[ReadbackAction] | None:
    """Spec 0007 4.6: status `PASS` and reason `readback` give `continue`; `check_model_failed` does not."""
    if state.status == VerdictStatus.PASS and state.reason == ReadbackReason.READBACK:
        return Pick(ReadbackAction.CONTINUE)
    return None


@rule(
    id="edit_cycle_analysis_messages.clean",
    version=2,
    point="edit_cycle_analysis_messages",
    rationale="No error, no unclassified message and no drift above the basis limit: the cycle continues.",
)
def analysis_messages_clean(state: AnalysisState, basis: RuleBasis) -> Pick[AnalysisAction] | None:
    """Spec 0007 4.6: no error, no unclassified message and drift `PASS` give `continue` (Q20).

    Drift is `PASS` when the summary's `exceeding` is empty, else `NEEDS_ENGINEER` (4.4.4).
    """
    if not state.has_errors and not state.has_unclassified and state.drift_status == VerdictStatus.PASS:
        return Pick(AnalysisAction.CONTINUE)
    return None
