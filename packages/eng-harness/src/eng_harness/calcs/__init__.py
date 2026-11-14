"""The shipped calcs: explicit registration, no discovery (spec 0003 4.2). Calcs arrive with plan 0003 T7 to T12."""

from eng_contract.kinds import NEUTRAL_KINDS

from eng_harness.calc import CalcRegistry, read_lock, removed_ids
from eng_harness.calcs.footing import FOOTING_CALCS, FOOTING_KINDS
from eng_harness.calcs.model_diff import model_diff
from eng_harness.calcs.model_fingerprint import StateMatch, model_fingerprint, same_state
from eng_harness.calcs.readback_check import readback_check
from eng_harness.kinds.calcs import CALC_KINDS

REGISTRY = CalcRegistry(
    NEUTRAL_KINDS.extend(CALC_KINDS).extend(FOOTING_KINDS),
    [model_fingerprint, model_diff, readback_check, *FOOTING_CALCS],
    removed=removed_ids(read_lock()),
)
"""The registry of the shipped calcs, checked against the neutral, calc and footing kinds."""

__all__ = ["REGISTRY", "StateMatch", "same_state"]
