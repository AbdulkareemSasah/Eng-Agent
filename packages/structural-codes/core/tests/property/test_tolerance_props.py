"""Property test of the tolerance comparison (plan 0001 T9; spec 0001 AC31); Hypothesis runs derandomized."""

from hypothesis import given, settings
from hypothesis import strategies as st

from structural_codes.verification import compare

# Whole numbers keep `a - e` exact in float64, so the properties hold without rounding slack.
_whole = st.integers(min_value=-1_000_000, max_value=1_000_000).map(float)
_tol = st.sampled_from([0.0, 1.0e-6, 0.005, 0.01, 0.5, 1.0, 10.0, 1000.0])
_dev = st.integers(min_value=0, max_value=100_000).map(float)


@settings(derandomize=True, max_examples=300, deadline=None)
@given(e=_whole, d1=_dev, d2=_dev, rel=_tol, floor=_tol, wider=_tol)
def test_symmetric_and_monotone(e: float, d1: float, d2: float, rel: float, floor: float, wider: float) -> None:
    near, far = sorted((d1, d2))
    # Symmetric: the sign of the deviation, and the sign of the whole problem, do not matter.
    assert compare(e + d1, e, rel_tol=rel, abs_tol=floor) == compare(e - d1, e, rel_tol=rel, abs_tol=floor)
    assert compare(-(e + d1), -e, rel_tol=rel, abs_tol=floor) == compare(e + d1, e, rel_tol=rel, abs_tol=floor)
    # Monotone in the deviation: a case that passes at the larger deviation passes at the smaller one.
    if compare(e + far, e, rel_tol=rel, abs_tol=floor):
        assert compare(e + near, e, rel_tol=rel, abs_tol=floor)
    # Monotone in each tolerance: a looser tolerance never turns a pass into a fail.
    if compare(e + d1, e, rel_tol=rel, abs_tol=floor):
        assert compare(e + d1, e, rel_tol=max(rel, wider), abs_tol=floor)
        assert compare(e + d1, e, rel_tol=rel, abs_tol=max(floor, wider))
    # Zero deviation always passes.
    assert compare(e, e, rel_tol=rel, abs_tol=floor)
