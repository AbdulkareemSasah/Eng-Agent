"""The shipped calcs: explicit registration, no discovery (spec 0003 4.2). Calcs arrive with plan 0003 T7 to T12."""

from eng_contract.kinds import NEUTRAL_KINDS

from eng_harness.calc import CalcRegistry
from eng_harness.calcs.footing import FOOTING_CALCS, FOOTING_KINDS

REGISTRY = CalcRegistry(NEUTRAL_KINDS.extend(FOOTING_KINDS), FOOTING_CALCS)
"""The registry of the shipped calcs: the footing calcs (spec 0010 4.4) so far."""

__all__ = ["REGISTRY"]
