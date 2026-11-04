"""Tests of the verdict builder and governing selection (plan 0001 T5; spec 0001 sections 3.3 and 4.5; AC11 to AC14)."""

import math
from typing import Any, NoReturn

import pytest
from eng_contract.cited import Cited
from eng_contract.envelope import LiteralInput
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import InputPolicy, ValidatedInput, validate_input
from eng_contract.quantity import Quantity
from eng_contract.records import ResultRecord
from eng_contract.verdicts import Subject, SubjectKind, Verdict, VerdictSource, VerdictStatus

from structural_codes._verdict import VerdictDraft, assign_governing
from structural_codes.errors import CheckDefinitionError
from structural_codes.inputs import CheckInputs, bounded
from structural_codes.trace import TraceRecorder

# Structural fixtures only: the numbers are labels for the verdict machinery, not engineering data.
_LOW = Cited(value=0, unit="mm", source="10-structural-codes synthetic lower bound")
_HIGH = Cited(value=100, unit="mm", source="10-structural-codes synthetic upper bound")
_SYNTH = "synthetic"
_CHECK_ID = "synth.21_2_1.demo"
_SUBJECT = Subject(kind=SubjectKind.FOOTING, id="F1")
_PASS, _FAIL = VerdictStatus.PASS, VerdictStatus.FAIL


class _Inputs(CheckInputs):
    width_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm")


class _NoSource:
    def get(self, result_id: str) -> ResultRecord:
        raise AssertionError(result_id)

    def payload(self, result_id: str) -> NoReturn:
        raise AssertionError(result_id)


def _recorder(ratio_limit: float | None = None) -> TraceRecorder:
    model = _Inputs(width_mm=10.0, ratio_limit=ratio_limit)
    provenance: dict[str, Any] = {"width_mm": LiteralInput(literal=10.0)}
    if ratio_limit is not None:
        provenance["ratio_limit"] = LiteralInput(literal=ratio_limit)
    return TraceRecorder(
        ValidatedInput(model, provenance),
        calc_id=_CHECK_ID,
        calc_version="1.0.0",
        content_sha256="a" * 64,
        subject=_SUBJECT,
    )


def _step(t: TraceRecorder, name: str, value: float, unit: str | None = "kN") -> None:
    t.step(name, value, unit=unit, formula="x", source=_SYNTH, uses=[])


def _pair(t: TraceRecorder, demand: float, capacity: float) -> None:
    _step(t, "demand_kN", demand)
    _step(t, "capacity_kN", capacity)


def _verdict_of(demand: float, capacity: float, ratio_limit: float | None = None) -> VerdictDraft:
    t = _recorder(ratio_limit)
    _pair(t, demand, capacity)
    t.verdict(demand="demand_kN", capacity="capacity_kN")
    (draft,) = t.verdicts
    return draft


def test_status_from_ratio() -> None:
    t = _recorder()
    _pair(t, 60.0, 100.0)
    t.verdict(demand="demand_kN", capacity="capacity_kN")
    (draft,) = t.verdicts
    assert draft.status is _PASS
    assert draft.ratio == 0.6
    assert draft.ratio_name == "ratio"
    assert (draft.demand_name, draft.capacity_name) == ("demand_kN", "capacity_kN")
    assert draft.demand == Quantity(60.0, "kN")
    assert draft.capacity == Quantity(100.0, "kN")
    assert draft.ratio_limit == 1.0
    assert draft.clause is None
    assert draft.assumptions == ()
    step = next(s for s in t.to_trace(outputs=[], status=None).steps if s.name == "ratio")
    assert (step.value, step.formula, step.source, step.uses) == (
        0.6,
        "demand / capacity",
        "04-tool-contract §5.1",
        ["demand_kN", "capacity_kN"],
    )
    assert t.value("ratio") == 0.6

    # Exact float64 comparison, no tolerance: equal to the limit passes, the next float above fails.
    assert _verdict_of(100.0, 100.0).status is _PASS
    assert _verdict_of(math.nextafter(1.0, math.inf), 1.0).status is _FAIL
    assert _verdict_of(math.nextafter(1.0, 0.0), 1.0).status is _PASS
    assert _verdict_of(0.0, 5.0).status is _PASS
    assert _verdict_of(0.0, 5.0).ratio == 0.0
    assert _verdict_of(150.0, 100.0).status is _FAIL

    # Later verdicts of one evaluation get unique ratio names.
    t.verdict(demand="demand_kN", capacity="capacity_kN")
    t.verdict(demand="capacity_kN", capacity="demand_kN")
    assert [d.ratio_name for d in t.verdicts] == ["ratio", "ratio_2", "ratio_3"]
    assert [d.status for d in t.verdicts] == [_PASS, _PASS, _FAIL]

    # Dimensionless operands (no unit) are allowed and become quantities in "1".
    u = _recorder()
    _step(u, "load", 1.0, None)
    _step(u, "resistance", 2.0, None)
    u.verdict(demand="load", capacity="resistance", clause="21.2.2", assumptions=("a",))
    assert u.verdicts[0].demand == Quantity(1.0, "1")
    assert u.verdicts[0].ratio == 0.5
    assert u.verdicts[0].clause == "21.2.2"
    assert u.verdicts[0].assumptions == ("a",)


def test_verdict_definition_errors() -> None:
    t = _recorder()
    _pair(t, 1.0, 2.0)
    _step(t, "length_mm", 1.0, "mm")
    _step(t, "force_N", 1.0, "N")
    with pytest.raises(CheckDefinitionError, match="dimension"):
        t.verdict(demand="demand_kN", capacity="length_mm")
    with pytest.raises(CheckDefinitionError, match="same unit"):
        t.verdict(demand="demand_kN", capacity="force_N")
    with pytest.raises(CheckDefinitionError, match="missing_kN"):
        t.verdict(demand="missing_kN", capacity="capacity_kN")
    with pytest.raises(CheckDefinitionError, match="missing_kN"):
        t.verdict(demand="demand_kN", capacity="missing_kN")
    assert list(t.verdicts) == []
    # A refused verdict records no ratio step and leaves the name free.
    assert "ratio" not in {s.name for s in t.to_trace(outputs=[], status=None).steps}
    t.verdict(demand="demand_kN", capacity="capacity_kN")
    assert t.verdicts[0].ratio_name == "ratio"
    # An input name is a recorded value too, but a name without a numeric value is refused.
    with pytest.raises(CheckDefinitionError, match="ratio_limit"):
        t.verdict(demand="ratio_limit", capacity="capacity_kN")


def test_invalid_capacity_gives_error() -> None:
    cases = ((1.0, 0.0, "capacity_kN = 0"), (1.0, -2.5, "capacity_kN = -2.5"), (-3.0, 5.0, "demand_kN = -3"))
    for demand, capacity, shown in cases:
        t = _recorder()
        _pair(t, demand, capacity)
        t.verdict(demand="demand_kN", capacity="capacity_kN")
        (draft,) = t.verdicts
        assert draft.status is VerdictStatus.ERROR
        assert draft.ratio is None
        assert draft.ratio_name is None
        assert draft.demand == Quantity(demand, "kN")
        assert draft.capacity == Quantity(capacity, "kN")
        trace = t.to_trace(outputs=[], status=VerdictStatus.ERROR)
        assert any(shown in m for m in trace.messages), trace.messages
        assert "ratio" not in {s.name for s in trace.steps}

    # An error verdict still counts for the ratio numbering.
    t = _recorder()
    _pair(t, 1.0, 0.0)
    t.verdict(demand="demand_kN", capacity="capacity_kN")
    _step(t, "capacity2_kN", 4.0)
    t.verdict(demand="demand_kN", capacity="capacity2_kN")
    assert [d.ratio_name for d in t.verdicts] == [None, "ratio_2"]

    # A ratio beyond float64 is an ERROR verdict, not an exception.
    t = _recorder()
    _pair(t, 1e308, 1e-10)
    t.verdict(demand="demand_kN", capacity="capacity_kN")
    assert t.verdicts[0].status is VerdictStatus.ERROR
    assert t.verdicts[0].ratio is None
    assert any("not finite" in m for m in t.to_trace(outputs=[], status=None).messages)


def test_ratio_limit() -> None:
    draft = _verdict_of(0.95, 1.0, ratio_limit=0.95)
    assert (draft.ratio_limit, draft.status) == (0.95, _PASS)
    draft = _verdict_of(math.nextafter(0.95, math.inf), 1.0, ratio_limit=0.95)
    assert (draft.ratio_limit, draft.status) == (0.95, _FAIL)
    # Absent: the contract default.
    draft = _verdict_of(0.97, 1.0)
    assert draft.ratio_limit == Verdict.model_fields["ratio_limit"].default == 1.0
    assert draft.status is _PASS

    # Above the default or not above zero: OUT_OF_RANGE from validate_input, nothing is clamped.
    for bad in (1.01, 0, -0.5):
        with pytest.raises(ContractError) as info:
            validate_input(
                _Inputs,
                {"width_mm": 10.0, "ratio_limit": bad},
                source=_NoSource(),
                current_revision=lambda _id: None,
                policy=InputPolicy(),
            )
        assert info.value.detail.code is ErrorCode.OUT_OF_RANGE


def _v(
    subject_id: str,
    status: VerdictStatus,
    ratio: float | None,
    *,
    governing: bool = False,
    kind: SubjectKind = SubjectKind.FOOTING,
    case: str | None = None,
) -> Verdict:
    sized = status in (_PASS, _FAIL)
    return Verdict(
        source=VerdictSource.CODE_PACK,
        check_id=_CHECK_ID,
        code="Synthetic Code",
        clause="21.2.1",
        subject=Subject(kind=kind, id=subject_id, case=case),
        demand=Quantity(ratio, "kN") if sized and ratio is not None else None,
        capacity=Quantity(1.0, "kN") if sized else None,
        ratio=ratio if sized else None,
        status=status,
        governing=governing,
        trace_ref="#/traces/0",
    )


def test_governing_selection() -> None:
    na, err, ne = VerdictStatus.NOT_APPLICABLE, VerdictStatus.ERROR, VerdictStatus.NEEDS_ENGINEER
    batch = [
        _v("A", _PASS, 0.5),
        _v("A", _PASS, 0.9),
        _v("A", _PASS, 0.7),
        _v("B", _PASS, 0.9),
        _v("B", _FAIL, 1.2),
        _v("C", na, None),
        _v("D", _PASS, 0.4),
        _v("D", err, None),
        _v("E", _PASS, 0.8),
        _v("E", _PASS, 0.8),
        _v("F", ne, None),
        _v("F", err, None),
    ]
    result = assign_governing(batch)
    assert [v.governing for v in result] == [
        False,
        True,
        False,
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        False,
        False,
    ]
    # Order and everything but `governing` is unchanged; the input is not mutated.
    assert [v.model_copy(update={"governing": False}) for v in result] == batch
    assert not any(v.governing for v in batch)
    assert assign_governing([]) == []

    # A body cannot set `governing`: a flag on the wrong verdict, or on a subject without PASS/FAIL, is cleared.
    preset = [_v("A", _PASS, 0.5, governing=True), _v("A", _FAIL, 2.0), _v("C", na, None, governing=True)]
    assert [v.governing for v in assign_governing(preset)] == [False, True, False]

    # A subject is the member (kind and id): other cases of it compete; another kind does not.
    mixed = [
        _v("A", _PASS, 0.5, case="COMB1"),
        _v("A", _PASS, 0.6, case="COMB2"),
        _v("A", _PASS, 0.3, kind=SubjectKind.FRAME),
    ]
    assert [v.governing for v in assign_governing(mixed)] == [False, True, True]
