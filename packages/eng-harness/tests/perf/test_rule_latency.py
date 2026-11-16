"""Latency of a rule decision through the cascade (plan 0005 T10; spec 0005 AC40; 12 section 1).

1,000 rule decisions, no journal and no store of results (the label store is not written for a rule answer). The bound
is the spec's p95 under 1 ms. The machine may run other jobs, so the measurement is taken in up to three rounds and the
test passes when one round meets the bound (a loaded round says nothing about the code); every round must still answer
all 1,000 calls with the rule, which is a count and does not depend on load.
"""

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path

from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.basis import DesignBasis
from pydantic import BaseModel, ConfigDict

from eng_harness.ctx import BasisView
from eng_harness.decisions import Cascade, LabelStore
from eng_harness.decisions._points import PointRegistry, decision_point
from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings
from eng_harness.decisions.interfaces import DecisionAnswer, DecisionCall
from eng_harness.decisions.types import Pick, RuleBasis, rule

DECISIONS = 1_000
LIMIT_S = 0.001  # AC40: p95 under 1 ms
ROUNDS = 3


class _Action(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


class _State(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    failing: bool


POINT = decision_point(name="pick_action", version=1, title="Pick an action", options=_Action, state=_State)(object)


@rule(id="pick_action.enlarge", version=1, point="pick_action", rationale="Enlarge when the check fails.")
def enlarge(state: _State, basis: RuleBasis) -> Pick[_Action] | None:
    return Pick(_Action.ENLARGE) if state.failing else None


@contextmanager
def _no_guard() -> Iterator[None]:
    yield


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[int(len(ordered) * 0.95) - 1]


def test_rule_decision_p95(tmp_path: Path) -> None:
    """AC40: p95 of a rule decision through the cascade is under 1 ms."""
    settings, clock = DecisionSettings(), FixedClock(1_767_225_600_000, 1)
    labels = LabelStore(tmp_path, settings, clock, SeededIdSource(b"labels", clock))
    cascade = Cascade(
        PointRegistry([POINT]), settings, labels, clock=clock, monotonic=time.perf_counter, rule_guard=_no_guard
    )
    basis = BasisView("res_" + "0" * 26, DesignBasis(template=None, fields={}), ())
    calls = [
        DecisionCall(
            request_id=f"dec_{n:032d}", run_id="run_x", step_path=str(n), point=POINT, options=_Action,
            state=_State(failing=True), rules=(enlarge,), policy=DecisionPolicy(), basis=basis,
        )
        for n in range(DECISIONS)
    ]  # fmt: skip
    p95s: list[float] = []

    async def measure() -> None:
        for _ in range(ROUNDS):
            samples = []
            for call in calls:
                started = time.perf_counter()
                answer = await cascade.decide(call)
                samples.append(time.perf_counter() - started)
                assert isinstance(answer, DecisionAnswer)
                assert answer.decided_by == "rule:pick_action.enlarge"
            p95s.append(_p95(samples))
            if p95s[-1] < LIMIT_S:
                break

    try:
        asyncio.run(measure())
    finally:
        labels.close()
    assert min(p95s) < LIMIT_S, p95s
