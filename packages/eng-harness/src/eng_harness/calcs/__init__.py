"""The shipped calcs: explicit registration, no discovery (spec 0003 4.2). Calcs arrive with plan 0003 T7 to T12."""

from eng_contract.kinds import NEUTRAL_KINDS

from eng_harness.calc import CalcRegistry, read_lock, removed_ids
from eng_harness.calcs.column_design import COLUMN_DESIGN_CALCS, COLUMN_DESIGN_KINDS
from eng_harness.calcs.design_summary import design_summary
from eng_harness.calcs.edit_cycle import EDIT_CYCLE_CALCS, EDIT_CYCLE_KINDS
from eng_harness.calcs.footing import FOOTING_CALCS, FOOTING_KINDS
from eng_harness.calcs.model_diff import model_diff
from eng_harness.calcs.model_fingerprint import StateMatch, model_fingerprint, same_state
from eng_harness.calcs.readback_check import readback_check
from eng_harness.calcs.section_round import section_round
from eng_harness.kinds.calcs import CALC_KINDS

REGISTRY = CalcRegistry(
    NEUTRAL_KINDS.extend(CALC_KINDS).extend(FOOTING_KINDS).extend(EDIT_CYCLE_KINDS).extend(COLUMN_DESIGN_KINDS),
    [
        model_fingerprint,
        model_diff,
        readback_check,
        design_summary,
        section_round,
        *FOOTING_CALCS,
        *EDIT_CYCLE_CALCS,
        *COLUMN_DESIGN_CALCS,
    ],
    removed=removed_ids(read_lock()),
)
"""The registry of the shipped calcs, checked against the neutral, calc, footing, edit-cycle and column kinds."""

__all__ = ["REGISTRY", "StateMatch", "same_state"]
