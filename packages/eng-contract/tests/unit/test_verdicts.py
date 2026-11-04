"""Verdict, Subject (plan T10; spec 4.9.1, AC35a, AC44)."""

from typing import Any

import pytest
from pydantic import ValidationError

from eng_contract.quantity import Quantity
from eng_contract.verdicts import Subject, SubjectKind, Verdict, VerdictSource, VerdictStatus

_CP_ID = "aci318_14.flexure.beam_moment"
_TRACE = "#/traces/0"
_SUBJECT = {"kind": "frame", "id": "B12"}


def _code_pack(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source": "code_pack",
        "check_id": _CP_ID,
        "code": "ACI 318-14",
        "clause": "22.2.1",
        "subject": _SUBJECT,
        "demand": Quantity(100, "kN"),
        "capacity": Quantity(200, "kN"),
        "ratio": 0.5,
        "status": "PASS",
        "trace_ref": _TRACE,
    }
    base.update(over)
    return base


def _host(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source": "host",
        "check_id": "steel:stress-ratio",
        "code": "AISC 360-16",
        "subject": _SUBJECT,
        "ratio": 0.9,
        "status": "PASS",
    }
    base.update(over)
    return base


def test_valid_verdicts_and_defaults() -> None:
    v = Verdict.model_validate(_code_pack())
    assert v.source is VerdictSource.CODE_PACK
    assert v.status is VerdictStatus.PASS
    assert v.ratio_limit == 1.0
    assert v.governing is False
    assert v.assumptions == []
    assert v.subject.kind is SubjectKind.FRAME
    assert v.subject.station_mm is None
    host = Verdict.model_validate(_host())
    assert host.demand is None
    assert host.clause is None
    assert Verdict.model_validate(v.model_dump(mode="json")) == v


@pytest.mark.parametrize(
    "over",
    [
        {"status": "PASS", "ratio": 1.2},
        {"status": "FAIL", "ratio": 0.5},
        {"status": "FAIL", "ratio": 1.0},
        {"status": "PASS", "ratio": None},
        {"status": "FAIL", "ratio": None},
        {"demand": Quantity(1, "mm")},
        {"trace_ref": None},
        {"clause": None},
        {"status": "PASS", "demand": None},
        {"status": "PASS", "capacity": None},
        {"ratio": -0.1},
        {"ratio_limit": 0},
        {"check_id": "Bad-Id"},
        {"check_id": "steel:stress-ratio"},
        {"code": ""},
        {"unknown": 1},
        {"assumptions": ["x" * 501]},
    ],
)
def test_consistency_rules(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Verdict.model_validate(_code_pack(**over))


def test_consistency_boundaries_and_stricter_limit() -> None:
    assert Verdict.model_validate(_code_pack(ratio=1.0)).status is VerdictStatus.PASS
    assert Verdict.model_validate(_code_pack(status="FAIL", ratio=1.0001)).status is VerdictStatus.FAIL
    with pytest.raises(ValidationError):
        Verdict.model_validate(_code_pack(ratio=0.9, ratio_limit=0.8))
    assert Verdict.model_validate(_code_pack(status="FAIL", ratio=0.9, ratio_limit=0.8)).governing is False


def test_non_decisive_statuses_need_no_ratio() -> None:
    for status in ("NOT_APPLICABLE", "NEEDS_ENGINEER", "ERROR"):
        v = Verdict.model_validate(_code_pack(status=status, ratio=None, demand=None, capacity=None))
        assert v.status.value == status


def test_host_rules() -> None:
    with pytest.raises(ValidationError):
        Verdict.model_validate(_host(check_id="Upper Case"))
    full = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV#/traces/0"
    assert Verdict.model_validate(_host(trace_ref=full)).trace_ref == full


def test_trace_ref_forms() -> None:
    for bad in ("#/traces/01", "#/traces/", "free text"):
        with pytest.raises(ValidationError):
            Verdict.model_validate(_code_pack(trace_ref=bad))


def test_subject() -> None:
    s = Subject.model_validate({"kind": "joint", "id": "1", "station_mm": 0, "case": "D+L"})
    assert (s.station_mm, s.case) == (0.0, "D+L")
    for bad in (
        {"kind": "wall", "id": "1"},
        {"kind": "joint", "id": ""},
        {"kind": "joint", "id": "1", "station_mm": -1},
    ):
        with pytest.raises(ValidationError):
            Subject.model_validate(bad)


def test_model_equality() -> None:
    with_demand = Verdict.model_validate(_host(demand=Quantity(1, "kN"), capacity=Quantity(2, "kN"), ratio=0.5))
    without = Verdict.model_validate(_host(ratio=0.5))
    assert (with_demand == without) is False
    assert (without == with_demand) is False
    other_dim = Verdict.model_validate(_host(demand=Quantity(1, "mm"), capacity=Quantity(2, "mm"), ratio=0.5))
    assert (with_demand == other_dim) is False
    inch = Verdict.model_validate(_host(demand=Quantity(1, "in"), capacity=Quantity(2, "in"), ratio=0.5))
    mm = Verdict.model_validate(_host(demand=Quantity(25.4, "mm"), capacity=Quantity(50.8, "mm"), ratio=0.5))
    assert inch == mm
    assert with_demand == Verdict.model_validate(with_demand.model_dump())
