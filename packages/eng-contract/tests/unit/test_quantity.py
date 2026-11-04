"""Quantity (plan T6; spec 4.8; AC34, AC35).

Expected values come from the spec's examples and from the cited unit definitions (1 in = 0.0254 m exactly).
"""

import math
import operator
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from eng_contract.errors import ErrorCode
from eng_contract.quantity import LabeledQuantity, Quantity
from eng_contract.units import UnitError

_Q = Quantity(450, "mm")

_ARITHMETIC: dict[str, Callable[[Quantity], object]] = {
    "add": lambda q: q + q,
    "add_number": lambda q: q + 1,
    "radd": lambda q: 1 + q,
    "sub": lambda q: q - q,
    "rsub": lambda q: 1 - q,
    "mul": lambda q: q * 2,
    "rmul": lambda q: 2 * q,
    "truediv": lambda q: q / 2,
    "rtruediv": lambda q: 2 / q,
    "floordiv": lambda q: q // 2,
    "mod": lambda q: q % 2,
    "pow": lambda q: q**2,
    "neg": operator.neg,
    "pos": operator.pos,
    "abs": abs,
    "round": round,
    "float": float,
    "int": int,
    "index": operator.index,
    "bool": bool,
}


@pytest.mark.parametrize("name", sorted(_ARITHMETIC))
def test_no_arithmetic(name: str) -> None:
    with pytest.raises(TypeError):
        _ARITHMETIC[name](_Q)


def test_in_place_arithmetic_is_refused() -> None:
    q: Any = Quantity(1, "mm")
    with pytest.raises(TypeError):
        q += q


def test_construction_and_json() -> None:
    q = Quantity(450, "mm")
    assert q.value == 450.0
    assert isinstance(q.value, float)
    assert q.model_dump(mode="json") == {"value": 450.0, "unit": "mm"}
    assert Quantity.model_validate({"value": 450.0, "unit": "mm"}) == q
    assert Quantity(value=450, unit="mm") == q


def test_validation() -> None:
    for bad in (math.inf, -math.inf, math.nan):
        with pytest.raises(ValidationError):
            Quantity(bad, "mm")
    with pytest.raises(ValidationError):
        Quantity.model_validate({"value": True, "unit": "mm"})
    with pytest.raises(ValidationError):
        Quantity.model_validate({"value": 1.0, "unit": "mm", "member": "B1"})
    with pytest.raises(UnitError) as info:
        Quantity(1, "furlong")
    assert info.value.detail.code is ErrorCode.UNIT_MISMATCH


def test_frozen() -> None:
    q: Any = Quantity(450, "mm")
    with pytest.raises(ValidationError):
        q.value = 1.0


def test_comparisons() -> None:
    inch, mm = Quantity(1, "in"), Quantity(25.4, "mm")
    assert inch == mm
    assert operator.ne(inch, mm) is False
    assert not inch < mm
    assert not mm < inch
    assert inch <= mm
    assert mm >= inch
    assert Quantity(24, "mm") < inch < Quantity(26, "mm")
    assert Quantity(26, "mm") > inch
    assert Quantity(212, "degF") == Quantity(100, "degC")
    assert Quantity(1, "K") < Quantity(0, "degC") < Quantity(300, "K")

    force, length = Quantity(1, "kN"), Quantity(1, "mm")
    for op in (operator.lt, operator.le, operator.gt, operator.ge):
        with pytest.raises(TypeError):
            op(force, length)
    assert force != length
    assert operator.eq(force, length) is False

    other: Any
    for other in (1, 1.0, None, "1 mm"):
        for op in (operator.lt, operator.le, operator.gt, operator.ge):
            with pytest.raises(TypeError):
                op(length, other)
            with pytest.raises(TypeError):
                op(other, length)
        assert operator.eq(length, other) is False
        assert length != other


def test_labels_do_not_take_part_in_comparison() -> None:
    labeled = LabeledQuantity.model_validate({"value": 1.0, "unit": "in", "member": "B1", "combo": 3, "flag": True})
    assert labeled == Quantity(25.4, "mm")
    assert hash(labeled) == hash(Quantity(25.4, "mm"))
    assert labeled.model_dump(mode="json") == {"value": 1.0, "unit": "in", "member": "B1", "combo": 3, "flag": True}
    assert LabeledQuantity.model_validate({"value": 1.0, "unit": "mm", "end": "i"}).model_extra == {"end": "i"}
    for bad in (1.5, None, [1], {"a": 1}):
        with pytest.raises(ValidationError):
            LabeledQuantity.model_validate({"value": 1.0, "unit": "mm", "member": bad})


def test_hash_consistent_with_eq() -> None:
    assert hash(Quantity(1, "in")) == hash(Quantity(25.4, "mm"))
    assert hash(Quantity(180, "deg")) == hash(Quantity(math.pi, "rad"))
    assert Quantity(180, "deg") == Quantity(math.pi, "rad")
    assert hash(Quantity(1, "kN")) != hash(Quantity(1, "mm"))
    assert len({Quantity(1, "in"), Quantity(25.4, "mm"), Quantity(1, "m")}) == 2
    assert Quantity(1, "kN") not in {Quantity(1, "mm")}


def test_extreme_values_hash_and_compare() -> None:
    big, small = Quantity(1e308, "MN"), Quantity(1e308, "N")
    assert small < big
    assert hash(big) == hash(Quantity(1e308, "MN"))


def test_conversions() -> None:
    assert Quantity(1, "in").to("mm") == Quantity(25.4, "mm")
    assert Quantity(1, "in").to("mm").unit == "mm"
    assert LabeledQuantity.model_validate({"value": 1.0, "unit": "in", "member": "B1"}).to("mm") == Quantity(25.4, "mm")
    assert Quantity(1, "kip").canonical("force").unit == "kN"
    assert Quantity(1, "kip").canonical("force").value == pytest.approx(4.4482216152605, rel=1e-14)
    with pytest.raises(UnitError):
        Quantity(1, "kip").canonical("length")
    with pytest.raises(UnitError):
        Quantity(1, "kip").canonical("no_such_kind")
    with pytest.raises(UnitError):
        Quantity(1, "kip").to("mm")
