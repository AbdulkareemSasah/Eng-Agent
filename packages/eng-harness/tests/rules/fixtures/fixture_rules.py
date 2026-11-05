"""Fixture rule module (test double): rules for a made-up point, used by plan 0005 T4 tests; never discovered."""

from enum import StrEnum

from eng_contract.quantity import Quantity
from pydantic import BaseModel, ConfigDict

from eng_harness.decisions.types import Pick, RuleBasis, rule

POINT = "fixture_point"


class Action(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


class FixtureState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bearing_ratio: Quantity
    bearing_fails: bool


@rule(
    id="fixture_point.bearing_only",
    version=1,
    point=POINT,
    rationale="Only the bearing check fails, and a larger plan lowers the bearing pressure.",
    thresholds=("limits.bearing_ratio",),
)
def bearing_only(state: FixtureState, basis: RuleBasis) -> Pick[Action] | None:
    if state.bearing_fails and state.bearing_ratio > basis.quantity("limits.bearing_ratio"):
        return Pick(Action.ENLARGE)
    return None


@rule(
    id="fixture_point.reads_undeclared",
    version=2,
    point=POINT,
    rationale="Reads a path that it did not declare.",
    thresholds=("limits.bearing_ratio",),
)
def reads_undeclared(state: FixtureState, basis: RuleBasis) -> Pick[Action] | None:
    basis.quantity("limits.other_ratio")
    return None
