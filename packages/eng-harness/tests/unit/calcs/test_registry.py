"""Calc decorator and registry (plan 0003 T1; spec 0003 AC1, 4.2)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from eng_contract.kinds import NEUTRAL_KINDS, KindRegistry
from eng_harness.calc import (
    CalcDef,
    CalcInput,
    CalcRegistry,
    CalcRegistryError,
    CalcStatus,
    InputMeta,
    TraceBuilder,
    calc,
)
from pydantic import BaseModel

HASH = "ab" * 32
_PATH = Path(__file__).resolve().parents[2] / "data" / "calcs" / "fixture_calcs.py"


def _load() -> ModuleType:
    """Load the fixture calc module by path (it is test data, not a package)."""
    spec = importlib.util.spec_from_file_location("fixture_calcs", _PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fixture_calcs"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fixtures() -> ModuleType:
    return _load()


@pytest.fixture
def kinds(fixtures: ModuleType) -> KindRegistry:
    return NEUTRAL_KINDS.extend({fixtures.OUTPUT_KIND: fixtures.FixtureOut})


def _hasher(definition: CalcDef) -> str:
    return HASH


def _build(fixtures: ModuleType, **override: object) -> CalcDef:
    """A calc like the fixture one, with `override` replacing decorator arguments."""
    args: dict[str, object] = {
        "id": "harness.fixture_sum",
        "version": 1,
        "output_kind": fixtures.OUTPUT_KIND,
        "title": "Fixture",
        "method_source": "Test double",
    } | override

    def fn(inp: fixtures.FixtureIn, meta: InputMeta, trace: TraceBuilder) -> fixtures.FixtureOut:
        return fixtures.FixtureOut(total=0.0)

    return calc(**args)(fn)  # type: ignore[arg-type]  # B-140: the test passes deliberately wrong argument values


def test_registration_rules(fixtures: ModuleType, kinds: KindRegistry) -> None:
    class NotACalcInput(BaseModel):
        pass

    def wrong_input(inp: NotACalcInput, meta: InputMeta, trace: TraceBuilder) -> fixtures.FixtureOut:
        return fixtures.FixtureOut(total=0.0)

    decorate = calc(id="harness.fixture_sum", version=1, output_kind=fixtures.OUTPUT_KIND, title="t", method_source="m")
    cases: list[tuple[str, CalcDef]] = [
        ("id", _build(fixtures, id="model.fixture")),
        ("id", _build(fixtures, id="harness.Fixture")),
        ("version", _build(fixtures, version=0)),
        ("version", _build(fixtures, version=10000)),
        ("version", _build(fixtures, version=True)),
        ("input_type", decorate(wrong_input)),
        ("output_kind", _build(fixtures, output_kind="harness.unknown/1")),
        ("output_kind", _build(fixtures, output_kind="model.stories/1")),
        ("method_source", _build(fixtures, method_source="   ")),
        ("verification", _build(fixtures, verification="approved")),
    ]
    for rule, definition in cases:
        with pytest.raises(CalcRegistryError) as caught:
            CalcRegistry(kinds, [definition], hasher=_hasher)
        assert caught.value.rule == rule, definition
    good = _build(fixtures)
    with pytest.raises(CalcRegistryError) as duplicate:
        CalcRegistry(kinds, [good, good], hasher=_hasher)
    assert duplicate.value.rule == "duplicate"
    assert list(CalcRegistry(kinds, [good], hasher=_hasher)) == ["harness.fixture_sum"]


def test_registry_lookup_and_hash(fixtures: ModuleType, kinds: KindRegistry) -> None:
    registry = CalcRegistry(kinds, [fixtures.fixture_sum], hasher=_hasher)
    entry = registry["harness.fixture_sum"]
    assert entry.version == 3
    assert entry.input_type is fixtures.FixtureIn
    assert entry.verification == CalcStatus.DRAFT
    assert registry.content_hash("harness.fixture_sum") == HASH
    assert issubclass(fixtures.FixtureIn, CalcInput)
    with pytest.raises(KeyError):
        registry["harness.absent"]


def test_statuses() -> None:
    assert [s.value for s in CalcStatus] == ["draft", "verified", "approved", "withdrawn"]
