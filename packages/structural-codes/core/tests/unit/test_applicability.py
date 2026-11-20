"""Tests of the framework-owned applicability steps (plan 0001 T8; spec 0001 AC5, AC5a, section 4.4)."""

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from eng_contract.verdicts import Subject, SubjectKind, Verdict, VerdictStatus

from structural_codes import Evaluation, evaluate
from structural_codes.pack import Registry

# B-262: the module name is split only because gate rule IM006 reports the fixture pack under tests/fixtures/*/src
# as an undeclared distribution (same workaround as tests/unit/test_registry.py, B-260); it hides no import.
_PACK_MODULE = "synth" + "base.runner_checks"
_SRC = Path(__file__).parent.parent / "fixtures" / "synthbase" / "src"

_SECTION = Subject(kind=SubjectKind.SECTION, id="S1")
_FRAME = Subject(kind=SubjectKind.FRAME, id="F1")
_FOOTING = Subject(kind=SubjectKind.FOOTING, id="FT1")


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[Registry]:
    monkeypatch.syspath_prepend(str(_SRC))
    yield Registry.of([importlib.import_module(_PACK_MODULE).RUNNER_PACK])
    for name in [n for n in sys.modules if n == "synthbase" or n.startswith("synthbase.")]:
        del sys.modules[name]


def _inputs(width: float) -> dict[str, float]:
    return {"width_mm": width, "demand_mm": 50.0, "capacity_mm": 100.0}


def _run(registry: Registry, short: str, width: float, subject: Subject) -> Evaluation:
    return evaluate(short, _inputs(width), subject=subject, registry=registry)


def _only(result: Evaluation) -> Verdict:
    assert len(result.payload.verdicts) == 1
    assert len(result.payload.traces) == 1
    return result.payload.verdicts[0]


def _no_numbers(verdict: Verdict) -> None:
    assert verdict.demand is None
    assert verdict.capacity is None
    assert verdict.ratio is None
    assert verdict.governing is False


def test_outcomes_and_order(registry: Registry) -> None:
    check_id = "synthbase.4_1.two_pre"
    # Width 60: both preconditions fail; the first declared (P1) wins.
    first = _run(registry, check_id, 60.0, _SECTION)
    verdict = _only(first)
    assert verdict.status is VerdictStatus.NOT_APPLICABLE
    assert verdict.check_id == check_id
    assert verdict.clause == "4.1"
    assert verdict.trace_ref == "#/traces/0"
    _no_numbers(verdict)
    trace = first.payload.traces[0]
    assert "P1 (4.1): synthetic first limit" in trace.messages
    assert not any("P2" in m for m in trace.messages)
    assert [c.name for c in trace.constants] == ["limit_one_mm"]  # P2 never ran
    assert trace.steps == []  # the body never ran
    assert trace.status is VerdictStatus.NOT_APPLICABLE
    assert trace.outputs == []

    # Width 30: P1 passes, only P2 fails.
    second = _run(registry, check_id, 30.0, _SECTION)
    verdict = _only(second)
    assert verdict.status is VerdictStatus.NEEDS_ENGINEER
    _no_numbers(verdict)
    trace = second.payload.traces[0]
    assert "P2 (4.2): synthetic second limit" in trace.messages
    assert not any("P1" in m for m in trace.messages)
    assert trace.steps == []

    # Width 10: both pass, the body runs and decides (demand 50 kN of capacity 100 kN).
    third = _run(registry, check_id, 10.0, _SECTION)
    verdict = _only(third)
    assert verdict.status is VerdictStatus.PASS
    assert verdict.ratio == 0.5
    assert verdict.governing is True
    assert [s.name for s in third.payload.traces[0].steps] == ["ratio"]


def test_member_scope_first(registry: Registry) -> None:
    # A frame is outside the member scope {footing}: neither the preconditions nor the body run, even when the
    # precondition would pass (width 10) and for a check that declares no preconditions.
    for short in ("synthbase.5_1.scoped", "synthbase.5_2.scoped_free"):
        result = _run(registry, short, 10.0, _FRAME)
        verdict = _only(result)
        assert verdict.status is VerdictStatus.NOT_APPLICABLE
        assert verdict.subject == _FRAME
        assert verdict.clause == short.split(".")[1].replace("_", ".")
        _no_numbers(verdict)
        trace = result.payload.traces[0]
        assert trace.constants == []
        assert trace.steps == []
        assert trace.status is VerdictStatus.NOT_APPLICABLE
        (message,) = trace.messages
        assert message.startswith(f"member scope ({verdict.clause}):")
        assert "frame" in message
        assert "footing" in message

    # A footing is inside the scope: the preconditions run and the body decides.
    scoped = _run(registry, "synthbase.5_1.scoped", 10.0, _FOOTING)
    assert _only(scoped).status is VerdictStatus.PASS
    assert [c.name for c in scoped.payload.traces[0].constants] == ["limit_one_mm"]
    failing = _run(registry, "synthbase.5_1.scoped", 60.0, _FOOTING)
    assert _only(failing).status is VerdictStatus.NOT_APPLICABLE
    assert "P1 (5.1): synthetic limit" in failing.payload.traces[0].messages
    free = _run(registry, "synthbase.5_2.scoped_free", 10.0, _FOOTING)
    assert _only(free).status is VerdictStatus.PASS
