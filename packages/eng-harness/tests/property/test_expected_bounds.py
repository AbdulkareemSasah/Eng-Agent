"""The median of the expected time lies between the minimum and the maximum (spec 0006 AC15)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.progress import estimate


@settings(derandomize=True, max_examples=200)
@given(st.lists(st.integers(min_value=0, max_value=10**12), min_size=1, max_size=50))
def test_median_within_range(samples: list[int]) -> None:
    est = estimate(samples)
    assert est.min_ms <= est.median_ms <= est.max_ms
    assert (est.min_ms, est.max_ms, est.samples) == (min(samples), max(samples), len(samples))
