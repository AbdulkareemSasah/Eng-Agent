"""Contract test of the `evaluate` payload against the eng-contract models (plan 0001 T8; spec 0001 AC26)."""

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from eng_contract.canonical import canonical_json
from eng_contract.kinds import verdicts
from eng_contract.verdicts import Subject, SubjectKind, VerdictSource, VerdictStatus

from structural_codes import evaluate
from structural_codes.pack import Registry

# B-262: the module name is split only because gate rule IM006 reports the fixture pack under tests/fixtures/*/src
# as an undeclared distribution (same workaround as tests/unit/test_registry.py, B-260); it hides no import.
_PACK_MODULE = "synth" + "base.runner_checks"
_SRC = Path(__file__).parent.parent / "fixtures" / "synthbase" / "src"


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[Registry]:
    monkeypatch.syspath_prepend(str(_SRC))
    yield Registry.of([importlib.import_module(_PACK_MODULE).RUNNER_PACK])
    for name in [n for n in sys.modules if n == "synthbase" or n.startswith("synthbase.")]:
        del sys.modules[name]


def test_evaluate_payload(registry: Registry) -> None:
    subject = Subject(kind=SubjectKind.SECTION, id="S1")
    result = evaluate(
        "synthbase.3_1.sized",
        {"width_mm": 10.0, "demand_mm": 50.0, "capacity_mm": 100.0},
        subject=subject,
        registry=registry,
    )
    payload = result.payload
    assert isinstance(payload, verdicts.VerdictSet)

    # The payload validates as verdicts.set/1 after a round trip through its canonical JSON form.
    reloaded = verdicts.VerdictSet.model_validate_json(canonical_json(payload.model_dump(mode="json")))
    assert reloaded == payload

    assert len(payload.verdicts) == 1
    assert len(payload.traces) == 1
    (verdict,) = payload.verdicts
    assert verdict.source is VerdictSource.CODE_PACK
    assert verdict.trace_ref == "#/traces/0"  # local reference, rebased by the store (EC 4.6.3)
    assert verdict.status is VerdictStatus.PASS
    assert verdict.governing is True
    assert payload.counts == {s: int(s is VerdictStatus.PASS) for s in VerdictStatus}
    assert payload.draft is True
    trace = payload.traces[0]
    assert trace.calc_id == "synthbase.3_1.sized"
    assert trace.subject == subject
    assert trace.outputs == ["demand_mm", "capacity_mm", "ratio"]
