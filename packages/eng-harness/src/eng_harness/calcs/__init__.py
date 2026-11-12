"""The shipped calcs: explicit registration, no discovery (spec 0003 4.2). Calcs arrive with plan 0003 T7 to T12."""

from eng_contract.kinds import NEUTRAL_KINDS

from eng_harness.calc import CalcRegistry, read_lock, removed_ids
from eng_harness.calcs.model_diff import model_diff
from eng_harness.calcs.model_fingerprint import StateMatch, model_fingerprint, same_state
from eng_harness.kinds.calcs import CALC_KINDS

REGISTRY = CalcRegistry(
    NEUTRAL_KINDS.extend(CALC_KINDS), [model_fingerprint, model_diff], removed=removed_ids(read_lock())
)
"""The registry of the shipped calcs, checked against the neutral and calc kinds."""

__all__ = ["REGISTRY", "StateMatch", "same_state"]
