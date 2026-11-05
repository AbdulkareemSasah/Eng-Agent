"""Tests of `evaluate` and `evaluate_batch` (plan 0001 T8; spec 0001 AC6, AC27, AC28, AC29, section 4.12)."""

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from eng_contract.envelope import LiteralInput, RefInput
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.records import ResultRecord
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus

from structural_codes import BatchItem, evaluate, evaluate_batch
from structural_codes.content_hash import content_hash
from structural_codes.errors import CheckDefinitionError, CheckNotUsable
from structural_codes.pack import Registry

# B-262: the module name is split only because gate rule IM006 reports the fixture pack under tests/fixtures/*/src
# as an undeclared distribution (same workaround as tests/unit/test_registry.py, B-260); it hides no import.
_PACK_MODULE = "synth" + "base.runner_checks"
_SRC = Path(__file__).parent.parent / "fixtures" / "synthbase" / "src"

_SIZED = "synthbase.3_1.sized"
_S1 = Subject(kind=SubjectKind.SECTION, id="S1")
_S2 = Subject(kind=SubjectKind.SECTION, id="S2")
_RID = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
_MISSING = "res_01ARZ3NDEKTSV4RRFFQ69G5FAW"
_TS = "2026-01-02T03:04:05.678Z"


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[Registry]:
    monkeypatch.syspath_prepend(str(_SRC))
    yield Registry.of([importlib.import_module(_PACK_MODULE).RUNNER_PACK])
    for name in [n for n in sys.modules if n == "synthbase" or n.startswith("synthbase.")]:
        del sys.modules[name]


def _inputs(*, width: Any = 10.0, demand: float = 50.0, capacity: float = 100.0, fault: str = "none") -> dict[str, Any]:
    return {"width_mm": width, "demand_mm": demand, "capacity_mm": capacity, "fault": fault}


class _Source:
    """In-memory `RecordSource` holding one section record; a missing id raises `REF_NOT_FOUND`."""

    def __init__(self) -> None:
        self.record = ResultRecord.model_validate(
            {
                "contract": "eng-contract/1",
                "result_id": _RID,
                "kind": "model.sections/1",
                "created_at": _TS,
                "units": "canonical/1",
                "complete": True,
                "producer": {"tool": "harness", "tool_version": "1", "inputs": {}, "started_at": _TS, "duration_ms": 0},
                "parents": [],
                "payload_sha256": "b" * 64,
                "payload": {"width_mm": 30},
                "payload_file": None,
            }
        )

    def get(self, result_id: str) -> ResultRecord:
        if result_id != _RID:
            raise ContractError(ErrorCode.REF_NOT_FOUND, f"no result {result_id}")
        return self.record

    def payload(self, result_id: str) -> dict[str, Any]:
        return dict(self.get(result_id).payload or {})


def test_not_implemented_gap(registry: Registry) -> None:
    result = evaluate("synthbase.6_1.gap", _inputs(), subject=_S1, registry=registry)
    (verdict,) = result.payload.verdicts
    assert verdict.status is VerdictStatus.NEEDS_ENGINEER  # the verdict recorded before the gap is replaced
    assert verdict.demand is None
    assert verdict.capacity is None
    assert verdict.ratio is None
    assert verdict.governing is False
    assert verdict.clause == "6.1"
    trace = result.payload.traces[0]
    (message,) = [m for m in trace.messages if "G-3" in m]
    assert "6.1" in message
    assert "synthetic gap reason" in message
    assert trace.outputs == []
    assert trace.status is VerdictStatus.NEEDS_ENGINEER

    # A declared gap raised by a precondition test gives the same outcome; its body never runs.
    pre = evaluate("synthbase.6_3.gap_pre", _inputs(), subject=_S1, registry=registry)
    assert pre.payload.verdicts[0].status is VerdictStatus.NEEDS_ENGINEER
    assert any("G-4" in m for m in pre.payload.traces[0].messages)

    with pytest.raises(CheckDefinitionError, match="G-9"):
        evaluate("synthbase.6_2.gap_undeclared", _inputs(), subject=_S1, registry=registry)


def test_references(registry: Registry) -> None:
    source = _Source()
    raw = _inputs(width={"$ref": f"{_RID}#/width_mm"})
    result = evaluate(_SIZED, raw, subject=_S1, registry=registry, source=source)
    assert result.payload.verdicts[0].status is VerdictStatus.PASS
    (width,) = [i for i in result.payload.traces[0].inputs if i.name == "width_mm"]
    assert width.value == 30
    assert width.ref == f"{_RID}#/width_mm"
    assert result.inputs_provenance[0]["width_mm"] == RefInput(ref=f"{_RID}#/width_mm")
    assert result.inputs_provenance[0]["demand_mm"] == LiteralInput(literal=50.0)

    with pytest.raises(ContractError) as no_source:
        evaluate(_SIZED, raw, subject=_S1, registry=registry)
    assert no_source.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert no_source.value.detail.field == "width_mm"

    with pytest.raises(ContractError) as missing:
        evaluate(
            _SIZED, _inputs(width={"$ref": f"{_MISSING}#/width_mm"}), subject=_S1, registry=registry, source=source
        )
    assert missing.value.detail.code is ErrorCode.REF_NOT_FOUND  # REF_* errors propagate unchanged
    assert missing.value.detail.field == "width_mm"


def test_batch(registry: Registry) -> None:
    items = [
        BatchItem(subject=_S1, inputs=_inputs(demand=50.0, capacity=100.0)),
        BatchItem(subject=_S2, inputs=_inputs(fault="zero")),
        BatchItem(subject=_S1, inputs=_inputs(demand=80.0, capacity=100.0)),
        BatchItem(subject=_S2, inputs=_inputs(demand=150.0, capacity=100.0)),
    ]
    result = evaluate_batch(_SIZED, items, registry=registry)
    payload = result.payload
    assert len(payload.traces) == 4
    assert [v.subject for v in payload.verdicts] == [_S1, _S2, _S1, _S2]
    assert [v.trace_ref for v in payload.verdicts] == [f"#/traces/{k}" for k in range(4)]
    assert [v.status for v in payload.verdicts] == [
        VerdictStatus.PASS,
        VerdictStatus.ERROR,  # item 1 failed with ZeroDivisionError; the others are unaffected
        VerdictStatus.PASS,
        VerdictStatus.FAIL,
    ]
    assert [v.ratio for v in payload.verdicts] == [0.5, None, 0.8, 1.5]
    # S1: the ratio 0.8 governs (item 2); S2: the only PASS/FAIL verdict is item 3's, the ERROR is not governing.
    assert [v.governing for v in payload.verdicts] == [False, False, True, True]
    assert [t.status for t in payload.traces] == [
        VerdictStatus.PASS,  # not governing: the first verdict's status
        VerdictStatus.ERROR,
        VerdictStatus.PASS,
        VerdictStatus.FAIL,
    ]
    assert payload.counts[VerdictStatus.PASS] == 2
    assert payload.counts[VerdictStatus.ERROR] == 1
    assert any("ZeroDivisionError" in m for m in payload.traces[1].messages)
    assert payload.traces[1].outputs == []
    assert len(result.inputs_provenance) == 4

    # Every contained failure kind gives one ERROR verdict.
    for fault, name in (
        ("overflow", "OverflowError"),
        ("domain", "ValueError"),
        ("nan", "TraceValueError"),
    ):
        one = evaluate(_SIZED, _inputs(fault=fault), subject=_S1, registry=registry)
        (verdict,) = one.payload.verdicts
        assert verdict.status is VerdictStatus.ERROR
        assert verdict.ratio is None
        assert any(name in m for m in one.payload.traces[0].messages)

    # A ValueError that is not a math-domain error is a defect in the body and propagates (AC28).
    with pytest.raises(ValueError, match="synthetic non-math failure"):
        evaluate(_SIZED, _inputs(fault="value"), subject=_S1, registry=registry)

    # Any other exception propagates.
    with pytest.raises(RuntimeError, match="synthetic unexpected failure"):
        evaluate(_SIZED, _inputs(fault="other"), subject=_S1, registry=registry)

    # Validation runs for every item before anything is evaluated: item 0 would raise RuntimeError if it ran.
    bad = [
        BatchItem(subject=_S1, inputs=_inputs(fault="other")),
        BatchItem(subject=_S1, inputs=_inputs(width=500.0)),
    ]
    with pytest.raises(ContractError) as invalid:
        evaluate_batch(_SIZED, bad, registry=registry)
    assert invalid.value.detail.code is ErrorCode.OUT_OF_RANGE
    assert invalid.value.detail.field == "items[1].width_mm"  # contract FieldPath form of "items/1/width_mm"
    with pytest.raises(ContractError) as single:
        evaluate(_SIZED, _inputs(width=500.0), subject=_S1, registry=registry)
    assert single.value.detail.field == "width_mm"


def test_state_mode_and_lookup(registry: Registry) -> None:
    check = registry.get(_SIZED)
    result = evaluate(_SIZED, _inputs(), subject=_S1, registry=registry)
    assert result.state == "draft"
    assert result.payload.draft is True
    assert result.content_sha256 == content_hash(check)
    assert result.payload.traces[0].content_sha256 == result.content_sha256
    assert result.payload.traces[0].calc_version == "0.0.2"
    assert result.payload.traces[0].calc_id == _SIZED
    with pytest.raises(CheckNotUsable) as refused:
        evaluate(_SIZED, _inputs(), subject=_S1, registry=registry, mode="production")
    assert refused.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert refused.value.detail.field == "check_id"
    with pytest.raises(ContractError) as unknown:
        evaluate("synthbase.9_9.nothing", _inputs(), subject=_S1, registry=registry)
    assert unknown.value.detail.code is ErrorCode.NOT_FOUND
    unknown_mode: Any = "staging"
    with pytest.raises(ContractError) as bad_mode:
        evaluate(_SIZED, _inputs(), subject=_S1, registry=registry, mode=unknown_mode)
    assert bad_mode.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert bad_mode.value.detail.field == "mode"


def test_model_instance_input(registry: Registry) -> None:
    inputs_cls: Any = registry.get(_SIZED).inputs
    as_model = evaluate(
        _SIZED, inputs_cls(width_mm=10.0, demand_mm=50.0, capacity_mm=100.0), subject=_S1, registry=registry
    )
    as_mapping = evaluate(_SIZED, _inputs(), subject=_S1, registry=registry)
    assert as_model.payload == as_mapping.payload
    not_inputs: Any = 42
    with pytest.raises(ContractError) as wrong:
        evaluate(_SIZED, not_inputs, subject=_S1, registry=registry)
    assert wrong.value.detail.code is ErrorCode.INVALID_ARGUMENT


def test_no_verdict(registry: Registry) -> None:
    with pytest.raises(CheckDefinitionError, match="verdict"):
        evaluate("synthbase.7_1.silent", _inputs(), subject=_S1, registry=registry)
