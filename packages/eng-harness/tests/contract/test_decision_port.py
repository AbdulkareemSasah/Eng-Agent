"""The cascade passes the shared `DecisionPort` conformance of the engine (plan 0005 T10; spec 0005 AC41, AC43).

The call, answer and summary checks are those of `test_ports_conformance.py::_check_decision_port` (engine AC57), run
against the real `Cascade` over a temporary label store, with one rule and no provider.
"""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path

from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.basis import DesignBasis
from pydantic import BaseModel, ConfigDict, JsonValue

from eng_harness.ctx import BasisView
from eng_harness.decisions import Cascade, LabelStore
from eng_harness.decisions._points import PointRegistry, decision_point
from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings
from eng_harness.decisions.interfaces import DecisionAnswer, DecisionCall, PendingAnswer
from eng_harness.decisions.types import Pick, RuleBasis, rule
from eng_harness.engine import EngineSettings
from eng_harness.ports import DecisionPort

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z


class _Choice(StrEnum):
    A = "a"
    B = "b"


class _State(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: bool


POINT = decision_point(name="pick_choice", version=1, title="Pick a choice", options=_Choice, state=_State)(object)


@rule(id="pick_choice.when_ready", version=1, point="pick_choice", rationale="A when the state is ready.")
def when_ready(state: _State, basis: RuleBasis) -> Pick[_Choice] | None:
    return Pick(_Choice.A) if state.ready else None


@contextmanager
def _no_guard() -> Iterator[None]:
    yield


@contextmanager
def _cascade(root: Path, runtime: dict[str, JsonValue] | None = None) -> Iterator[Cascade]:
    settings = DecisionSettings()
    clock = FixedClock(START_MS, 1)
    labels = LabelStore(root, settings, clock, SeededIdSource(b"labels", clock))
    try:
        yield Cascade(
            PointRegistry([POINT]), settings, labels, clock=clock, monotonic=lambda: 0.0, rule_guard=_no_guard,
            max_concurrent_decisions=EngineSettings().max_concurrent_decisions, runtime=runtime,
        )  # fmt: skip
    finally:
        labels.close()


def _call(n: int, *, ready: bool) -> DecisionCall:
    basis = BasisView("res_" + "0" * 26, DesignBasis(template=None, fields={}), ())
    return DecisionCall(
        request_id=f"dec_{n:032d}", run_id="run_x", step_path=str(n), point=POINT, options=_Choice,
        state=_State(ready=ready), rules=(when_ready,), policy=DecisionPolicy(), basis=basis,
    )  # fmt: skip


def test_cascade_conforms(tmp_path: Path) -> None:
    """Calls, batches and the runtime summary behave as the port protocol says (AC41, AC43)."""
    with _cascade(tmp_path / "bare") as built:
        port: DecisionPort = built
        one = asyncio.run(port.decide(_call(0, ready=True)))
        assert isinstance(one, DecisionAnswer)
        assert (one.choice, one.decided_by, one.options) == ("a", "rule:pick_choice.when_ready", ("a", "b"))
        many = asyncio.run(port.decide_many([_call(1, ready=True), _call(2, ready=False), _call(3, ready=True)]))
        assert [type(a) for a in many] == [
            DecisionAnswer,
            PendingAnswer,
            DecisionAnswer,
        ]  # one entry per call, in order
        assert many[1].request_id == _call(2, ready=False).request_id
        assert port.runtime_summary() == {}  # built without a summary: empty, and no I/O
    summary: dict[str, JsonValue] = {"providers": {"local": {"tier": "advisory"}}, "points": {"pick_choice": 1}}
    with _cascade(tmp_path / "given", summary) as given:
        assert given.runtime_summary() == summary
        assert given.runtime_summary() == summary  # unchanged by being read twice
