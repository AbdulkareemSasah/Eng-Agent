"""Cited (plan T6; spec 4.8)."""

import math
import operator
from typing import Any

import pytest
from pydantic import ValidationError

from eng_contract.cited import Cited
from eng_contract.errors import ErrorCode
from eng_contract.units import UnitError

_SOURCE = "ACI 318-14 Table 21.2.1(b)"


def test_construction_and_json() -> None:
    c = Cited(value=0.75, unit="1", source=_SOURCE)
    assert c.note is None
    assert c.model_dump(mode="json") == {"value": 0.75, "unit": "1", "source": _SOURCE, "note": None}
    assert Cited.model_validate(c.model_dump(mode="json")) == c
    assert isinstance(Cited(value=3, unit="mm", source=_SOURCE, note="n").value, int)


def test_unit_must_be_known() -> None:
    with pytest.raises(UnitError) as info:
        Cited(value=1, unit="furlong", source=_SOURCE)
    assert info.value.detail.code is ErrorCode.UNIT_MISMATCH


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan, True, "1"])
def test_value_must_be_a_finite_number(value: object) -> None:
    with pytest.raises(ValidationError):
        Cited.model_validate({"value": value, "unit": "1", "source": _SOURCE})


@pytest.mark.parametrize("source", ["", "short", "        ", "a" * 501])
def test_source_length_and_blank(source: str) -> None:
    with pytest.raises(ValidationError):
        Cited(value=1, unit="1", source=source)


def test_source_and_note_boundaries() -> None:
    assert Cited(value=1, unit="1", source="a" * 8).source == "a" * 8
    assert Cited(value=1, unit="1", source="a" * 500, note="n" * 500).note == "n" * 500
    with pytest.raises(ValidationError):
        Cited(value=1, unit="1", source=_SOURCE, note="n" * 501)


def test_frozen_and_no_extra_members() -> None:
    c: Any = Cited(value=1, unit="1", source=_SOURCE)
    with pytest.raises(ValidationError):
        c.value = 2
    with pytest.raises(ValidationError):
        Cited.model_validate({"value": 1, "unit": "1", "source": _SOURCE, "extra": 1})


def test_no_arithmetic_or_ordering() -> None:
    c: Any = Cited(value=0.75, unit="1", source=_SOURCE)
    for op in (operator.add, operator.mul, operator.lt, operator.ge):
        with pytest.raises(TypeError):
            op(c, c)
    with pytest.raises(TypeError):
        c * 2
    with pytest.raises(TypeError):
        float(c)
