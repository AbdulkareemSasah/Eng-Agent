"""Tests of the trace recorder (plan 0001 T4; spec 0001 section 4.5; AC4b, AC8, AC9, AC10)."""

import math

import pytest
from eng_contract.cited import Cited
from eng_contract.envelope import LiteralInput, RefInput
from eng_contract.params import ValidatedInput
from eng_contract.trace import Trace
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus

from structural_codes.errors import CheckDefinitionError, TraceValueError
from structural_codes.inputs import CheckInputs, bounded, unbounded
from structural_codes.trace import TraceRecorder

# Structural fixtures only: the numbers are labels for the recording machinery, not engineering data.
_LOW = Cited(value=0, unit="mm", source="10-structural-codes synthetic lower bound")
_HIGH = Cited(value=100, unit="mm", source="10-structural-codes synthetic upper bound")
_PHI = Cited(value=0.5, unit="1", source="10-structural-codes synthetic constant", note="label")
_REF = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV#/payload/width_mm"
_SHA = "a" * 64
_SYNTH = "synthetic"


class _Inputs(CheckInputs):
    width_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm")
    reaction_kN: float = unbounded(reason="signed reaction; no physical bound", unit="kN")
    flag: bool = False


def _recorder(*, width: float = 10.0, ref: bool = False) -> TraceRecorder:
    model = _Inputs(width_mm=width, reaction_kN=-3.0)
    provenance = {
        "width_mm": RefInput(ref=_REF) if ref else LiteralInput(literal=width),
        "reaction_kN": LiteralInput(literal=-3.0),
    }
    return TraceRecorder(
        ValidatedInput(model, provenance),
        calc_id="synth.21_2_1.demo",
        calc_version="1.2.3",
        content_sha256=_SHA,
        subject=Subject(kind=SubjectKind.FOOTING, id="F1"),
    )


def test_recording_rules() -> None:
    t = _recorder()
    assert t.const("phi", _PHI) == 0.5
    assert t.value("phi") == 0.5
    assert t.value("width_mm") == 10.0
    assert t.value("flag") == 0.0
    assert t.step("area_mm2", 100.0, unit="mm2", formula="width_mm * width_mm", source=_SYNTH, uses=["width_mm"]) == 100.0
    assert t.step("ok", True, unit=None, formula="area_mm2 > 0", source=_SYNTH, uses=["area_mm2"]) == 1.0
    assert t.value("area_mm2") == 100.0
    assert t.step("n", 2, unit=None, formula="2", source=_SYNTH, uses=[]) == 2.0

    with pytest.raises(CheckDefinitionError, match="phi"):
        t.const("phi", _PHI)
    with pytest.raises(CheckDefinitionError, match="width_mm"):
        t.step("width_mm", 1.0, unit="mm", formula="x", source=_SYNTH, uses=[])
    with pytest.raises(CheckDefinitionError, match="later"):
        t.step("a_mm", 1.0, unit="mm", formula="later", source=_SYNTH, uses=["later"])
    with pytest.raises(CheckDefinitionError, match="not a valid name"):
        t.step("1bad", 1.0, unit=None, formula="x", source=_SYNTH, uses=[])
    with pytest.raises(CheckDefinitionError, match="unknown"):
        t.value("unknown")
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(TraceValueError, match="bad_value"):
            t.step("bad_value", bad, unit=None, formula="x", source=_SYNTH, uses=[])
    with pytest.raises(TraceValueError, match="text"):
        t.step("text", "a", unit=None, formula="x", source=_SYNTH, uses=[])  # type: ignore[arg-type]  # B-258: wrong type on purpose
    # A rejected step leaves nothing behind: the name is free again.
    t.step("bad_value", 1.0, unit=None, formula="x", source=_SYNTH, uses=[])
    with pytest.raises(CheckDefinitionError, match="no numeric value"):
        t.value("ratio_limit")

    recorded = t.to_trace(outputs=["area_mm2"], status=None)
    assert [c.cited for c in recorded.constants] == [_PHI]
    assert [s.name for s in recorded.steps] == ["area_mm2", "ok", "n", "bad_value"]
    assert recorded.steps[1].value is True


def test_inputs_and_contract_shape() -> None:
    t = _recorder(ref=True)
    t.note("a note")
    t.step("area_mm2", 100.0, unit="mm2", formula="width_mm * width_mm", source=_SYNTH, uses=["width_mm"])
    trace = t.to_trace(outputs=["area_mm2"], status=VerdictStatus.PASS)

    assert Trace.model_validate(trace.model_dump()) == trace
    assert trace.calc_id == "synth.21_2_1.demo"
    assert trace.calc_version == "1.2.3"
    assert trace.content_sha256 == _SHA
    assert trace.subject == Subject(kind=SubjectKind.FOOTING, id="F1")
    assert trace.outputs == ["area_mm2"]
    assert trace.status is VerdictStatus.PASS
    by_name = {i.name: (i.value, i.unit, i.ref) for i in trace.inputs}
    assert list(by_name) == ["ratio_limit", "width_mm", "reaction_kN", "flag"]
    assert by_name["width_mm"] == (10.0, "mm", _REF)
    assert by_name["reaction_kN"] == (-3.0, "kN", None)
    assert by_name["ratio_limit"] == (None, "1", None)
    assert by_name["flag"] == (False, None, None)
    assert trace.messages == ["reaction_kN: unbounded (signed reaction; no physical bound)", "a note"]

    with pytest.raises(CheckDefinitionError, match="outputs"):
        t.to_trace(outputs=["missing"], status=None)
    t.step("long_step", 1.0, unit=None, formula="x" * 1001, source=_SYNTH, uses=[])
    with pytest.raises(CheckDefinitionError, match="long_step"):
        t.to_trace(outputs=[], status=None)


def test_step_units() -> None:
    t = _recorder()
    for name, unit in (
        ("force_kN", "kN"),
        ("pressure_kPa", "kPa"),
        ("moment_kNm", "kN.m"),
        ("share_ratio", "1"),
        ("plain", "m"),
        ("unitless", None),
    ):
        t.step(name, 1.0, unit=unit, formula="x", source=_SYNTH, uses=[])

    with pytest.raises(CheckDefinitionError, match="demand_kN.*'N'"):
        t.step("demand_kN", 1.0, unit="N", formula="x", source=_SYNTH, uses=[])
    with pytest.raises(CheckDefinitionError, match="depth_mm"):
        t.step("depth_mm", 1.0, unit=None, formula="x", source=_SYNTH, uses=[])
    with pytest.raises(CheckDefinitionError, match="furlong"):
        t.step("odd", 1.0, unit="furlong", formula="x", source=_SYNTH, uses=[])
    mpa = Cited(value=1, unit="MPa", source="10-structural-codes synthetic constant")
    with pytest.raises(CheckDefinitionError, match="bad_kN"):
        t.const("bad_kN", mpa)
    assert t.const("good_MPa", mpa) == 1.0


def test_unbounded_reason_message() -> None:
    trace = _recorder().to_trace(outputs=[], status=None)
    assert trace.messages == ["reaction_kN: unbounded (signed reaction; no physical bound)"]
