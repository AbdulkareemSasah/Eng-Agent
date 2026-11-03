"""Property test of canonical JSON (plan T3; spec 4.3.1; AC4)."""

import hashlib

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_contract.canonical import canonical_json, loads, payload_sha256

_BIG_INTEGRAL = st.integers(min_value=2**53 - 4, max_value=2**70).map(float)
_NUMBERS = st.one_of(
    st.integers(min_value=-(2**53 - 1), max_value=2**53 - 1),
    st.floats(allow_nan=False, allow_infinity=False),
    _BIG_INTEGRAL,
    _BIG_INTEGRAL.map(lambda x: -x),
    st.sampled_from([2.0**53, 1e16, 1e20, 1e21, 2.0**60, 2.0**68, 0.0, -0.0]),
)
_SCALARS = st.one_of(st.none(), st.booleans(), _NUMBERS, st.text())
_JSON = st.recursive(
    _SCALARS,
    lambda children: st.one_of(st.lists(children, max_size=5), st.dictionaries(st.text(), children, max_size=5)),
    max_leaves=25,
)


@settings(derandomize=True, max_examples=300, deadline=None)
@given(_JSON)
def test_round_trip_is_stable(value: object) -> None:
    first = canonical_json(value)
    second = canonical_json(loads(first))
    assert second == first
    assert payload_sha256(value) == hashlib.sha256(first).hexdigest()
