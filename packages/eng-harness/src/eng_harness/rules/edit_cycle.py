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
    version=1,
    point="edit_cycle_readback_result",
    rationale="The read-back passed and the model did not change during the apply, so the cycle continues.",
)
def readback_result_pass(state: ReadbackState, basis: RuleBasis) -> Pick[ReadbackAction] | None:
    """Spec 0007 4.6: status `PASS` and reason `readback` give `continue`."""
    if state.status == VerdictStatus.PASS and state.reason == ReadbackReason.READBACK:
        return Pick(ReadbackAction.CONTINUE)
    return None


@rule(
    id="edit_cycle_analysis_messages.clean",
    version=1,
    point="edit_cycle_analysis_messages",
    rationale="The analysis reported no error message and no message of unknown severity, so the cycle continues.",
)
def analysis_messages_clean(state: AnalysisState, basis: RuleBasis) -> Pick[AnalysisAction] | None:
    """Spec 0007 4.6: no error and no unclassified message give `continue`."""
    if not state.has_errors and not state.has_unclassified:
        return Pick(AnalysisAction.CONTINUE)
    return None
