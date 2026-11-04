"""Trace builder and framework surface (plan 0003 T1; spec 0003 AC5, 4.1, 4.2)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from eng_contract.cited import Cited
from eng_contract.kinds import NEUTRAL_KINDS

from eng_harness import errors
from eng_harness.calc import CalcRegistry, InputMeta, NotImplementedGap, RefMeta, TraceBuilder, TraceError

HASH = "cd" * 32
_PATH = Path(__file__).resolve().parents[2] / "data" / "calcs" / "fixture_calcs.py"


@pytest.fixture(scope="module")
def fixtures() -> ModuleType:
    """The fixture calc module, loaded by path (it is test data, not a package)."""
    spec = importlib.util.spec_from_file_location("fixture_calcs", _PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fixture_calcs"] = module
    spec.loader.exec_module(module)
    return module


def _meta(fixtures: ModuleType) -> InputMeta:
    ref = RefMeta(
        result_id=fixtures.SYNTHETIC_ID,
        kind="model.sections/1",
        complete=True,
        model_id=None,
        model_revision=None,
        parents=(),
        producer_tool="fixture_tool",
    )
    return InputMeta(refs={"span_mm": ref})


def test_trace_records_inputs_and_rules(fixtures: ModuleType) -> None:
    kinds = NEUTRAL_KINDS.extend({fixtures.OUTPUT_KIND: fixtures.FixtureOut})
    registry = CalcRegistry(kinds, [fixtures.fixture_sum], hasher=lambda _: HASH)
    definition = registry["harness.fixture_sum"]
    trace = TraceBuilder()
    out = definition(fixtures.FixtureIn(span_mm=500.0, offset=2.5), _meta(fixtures), trace)
    built = trace.build(definition, registry.content_hash(definition.id))
    assert out.model_dump()["total"] == pytest.approx(502.5, abs=1e-9)
    assert (built.calc_id, built.calc_version, built.content_sha256) == ("harness.fixture_sum", "3", HASH)
    by_name = {i.name: i for i in built.inputs}
    assert by_name["span_mm"].ref == f"{fixtures.SYNTHETIC_ID}#/value"
    assert by_name["span_mm"].unit == "mm"
    assert by_name["offset"].value == 2.5
    assert [(s.name, s.source, s.uses) for s in built.steps] == [("total", "fixture rule R1", ["span_mm", "offset"])]
    assert built.outputs == ["total"]


def test_builder_refuses_bad_steps() -> None:
    trace = TraceBuilder()
    trace.input("a", 1)
    with pytest.raises(TraceError, match="earlier"):
        trace.step("s", 1, formula="b", source="rule", uses=["b"])
    with pytest.raises(TraceError, match="duplicate"):
        trace.input("a", 2)
    with pytest.raises(TraceError, match="source"):
        trace.step("s", 1, formula="a", source=" ", uses=["a"])
    with pytest.raises(TraceError, match="output"):
        trace.output("missing")


def test_step_keeps_uses_given_as_a_one_shot_iterator() -> None:
    trace = TraceBuilder()
    trace.input("a", 1)
    trace.step("s", 1, formula="a", source="rule", uses=(n for n in ["a"]))
    assert list(trace._steps[0].uses) == ["a"]


def test_builder_records_cited_constants(fixtures: ModuleType) -> None:
    trace = TraceBuilder()
    cited = Cited(value=2, unit="1", source="Test double source")
    trace.constant("k", cited)
    trace.step("s", 4, formula="k * k", source="rule", uses=["k"])
    trace.output("s")
    built = trace.build(fixtures.fixture_sum, HASH)
    assert [(c.name, c.cited) for c in built.constants] == [("k", cited)]
    assert built.steps[0].uses == ["k"]


def test_gap_and_codes_are_the_harness_ones() -> None:
    assert NotImplementedGap is errors.NotImplementedGap
    refused = errors.CalcRefused(errors.HarnessCode.CALC_WITHDRAWN, "x")
    assert refused.code == errors.HarnessCode.CALC_WITHDRAWN
