"""The shipped calcs: explicit registration, no discovery (spec 0003 4.2). Calcs arrive with plan 0003 T7 to T12."""

from eng_contract.kinds import NEUTRAL_KINDS

from eng_harness.calc import CalcRegistry

REGISTRY = CalcRegistry(NEUTRAL_KINDS)
"""The registry of the shipped calcs (empty until T7)."""

__all__ = ["REGISTRY"]
