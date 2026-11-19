"""Independent minimality and monotonicity properties for spec 0010 AC7."""

from fractions import Fraction

from golden.footing import load_cases
from golden.footing.test_plan_size import run_case
from hypothesis import given
from hypothesis import strategies as st


@given(
    load=st.integers(min_value=1, max_value=12_000),
    added=st.integers(min_value=0, max_value=2_000),
    increment=st.integers(min_value=50, max_value=500),
    minimum=st.integers(min_value=501, max_value=2_000),
)
def test_minimal_and_monotone(load: int, added: int, increment: int, minimum: int) -> None:
    case = load_cases("plan")["plan-gross"]
    raw = case.input
    raw["subjects"]["subjects"] = raw["subjects"]["subjects"][:1]
    reaction = raw["reactions"]["rows"][0]
    raw["reactions"]["rows"] = [reaction]
    fields = raw["basis"]["fields"]
    fields["foundation.plan_increment_mm"]["value"] = increment
    fields["foundation.min_plan_dimension_mm"]["value"] = minimum
    fields["foundation.max_plan_dimension_mm"]["value"] = 20_000

    def size(force: int) -> int:
        reaction["FZ_kN"] = force
        row = run_case(case).model_dump()["footings"][0]
        assert (row["status"], row["reason"], row["plan_at_max"]) == ("OK", None, False)
        assert row["Lx_mm"] == row["Ly_mm"]
        length = int(row["Lx_mm"])
        assert length == row["Lx_mm"]
        assert length % increment == 0
        assert length >= minimum
        # P2: 200 - (0.5 * 24 + 1 * 18 + 10) = 160 kPa.
        # P3: force / 160 m2. Compare with the squared side in metres.
        required_area = Fraction(force, 160)
        assert Fraction(length, 1000) ** 2 >= required_area
        shorter = length - increment
        assert shorter < minimum or Fraction(shorter, 1000) ** 2 < required_area
        return length

    assert size(load) <= size(load + added)
