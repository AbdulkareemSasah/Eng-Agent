"""Property tests of Quantity ordering (plan T6; spec 4.8 rules 2 to 5; AC36).

The oracle converts both sides exactly to one reference unit of the group with `convert_exact`, taking each float as
its shortest round-trip decimal (the number as written; see the class docstring of `Quantity`).
"""

from collections import defaultdict
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_contract.quantity import Quantity
from eng_contract.units import UNITS, convert_exact

_GROUPS: dict[tuple[tuple[int, ...], int], list[str]] = defaultdict(list)
_DIMENSIONS: dict[tuple[int, ...], list[str]] = defaultdict(list)
for _symbol, _unit in sorted(UNITS.items()):
    _GROUPS[(tuple(_unit.dimension), _unit.pi_power)].append(_symbol)
    _DIMENSIONS[tuple(_unit.dimension)].append(_symbol)

_FLOATS = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
_SAME_PI = st.sampled_from(sorted(_GROUPS)).flatmap(
    lambda key: st.tuples(_FLOATS, st.sampled_from(_GROUPS[key]), _FLOATS, st.sampled_from(_GROUPS[key]))
)
_ANY_PAIR = st.sampled_from(sorted(_DIMENSIONS)).flatmap(
    lambda key: st.tuples(_FLOATS, st.sampled_from(_DIMENSIONS[key]), _FLOATS, st.sampled_from(_DIMENSIONS[key]))
)


@settings(derandomize=True, max_examples=500, deadline=None)
@given(_SAME_PI)
def test_order_consistent(case: tuple[float, str, float, str]) -> None:
    (va, ua, vb, ub) = case
    reference = _GROUPS[(tuple(UNITS[ua].dimension), UNITS[ua].pi_power)][0]
    ka = convert_exact(Decimal(repr(va)), ua, reference)
    kb = convert_exact(Decimal(repr(vb)), ub, reference)
    a, b = Quantity(va, ua), Quantity(vb, ub)
    assert (a < b) == (ka < kb)
    assert (a <= b) == (ka <= kb)
    assert (a > b) == (ka > kb)
    assert (a >= b) == (ka >= kb)
    assert (a == b) == (ka == kb)
    assert (a != b) == (ka != kb)
    if a == b:
        assert hash(a) == hash(b)


@settings(derandomize=True, max_examples=500, deadline=None)
@given(_ANY_PAIR)
def test_order_is_total(case: tuple[float, str, float, str]) -> None:
    (va, ua, vb, ub) = case
    a, b = Quantity(va, ua), Quantity(vb, ub)
    assert [a < b, a == b, a > b].count(True) == 1
    assert (a <= b) == (a < b or a == b)
    assert (a < b) == (b > a)
    if a == b:
        assert hash(a) == hash(b)
