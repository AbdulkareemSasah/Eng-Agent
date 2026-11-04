"""Property tests of unit conversion (plan T5; spec 4.7.4; AC33)."""

import json
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_contract.units import UNITS, convert, convert_exact

_ROWS = json.loads((Path(__file__).parent.parent / "data" / "units" / "factors.json").read_text(encoding="utf-8"))[
    "units"
]
_FIXTURE = {row["symbol"]: (Fraction(row["factor"]), Fraction(row["offset"])) for row in _ROWS}

_GROUPS: dict[tuple[tuple[int, ...], int], list[str]] = defaultdict(list)
for _row in _ROWS:
    _GROUPS[(tuple(_row["dimension"]), _row["pi_power"])].append(_row["symbol"])
_PAIRS = st.sampled_from(sorted(_GROUPS)).flatmap(
    lambda key: st.tuples(st.sampled_from(_GROUPS[key]), st.sampled_from(_GROUPS[key]))
)
_FLOATS = st.floats(min_value=-1e100, max_value=1e100, allow_nan=False, allow_infinity=False)


def test_fixture_covers_the_groups() -> None:
    assert len(_GROUPS) >= 15
    assert all(len(group) >= 1 for group in _GROUPS.values())
    assert set(_FIXTURE) <= set(UNITS)


@settings(derandomize=True, max_examples=300, deadline=None)
@given(_FLOATS, _PAIRS)
def test_round_trip_exact(value: float, pair: tuple[str, str]) -> None:
    src, dst = pair
    there = convert_exact(value, src, dst)
    assert convert_exact(there, dst, src) == Fraction(value)


@settings(derandomize=True, max_examples=300, deadline=None)
@given(_FLOATS, _PAIRS)
def test_single_rounding(value: float, pair: tuple[str, str]) -> None:
    src, dst = pair
    (f_src, o_src), (f_dst, o_dst) = _FIXTURE[src], _FIXTURE[dst]
    exact = (Fraction(value) * f_src + o_src - o_dst) / f_dst
    assert convert(value, src, dst) == float(exact)
