"""Section size rounding properties (plan 0003 T11; spec 0003 AC41): multiple, never below, less than one step above."""

from fractions import Fraction
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"
_positive = st.floats(min_value=0.0, max_value=1e6, exclude_min=True, allow_nan=False, allow_infinity=False)


def _ref(n: int, kind: str) -> dict[str, Any]:
    return {
        "result_id": f"res_{n:026d}",
        "kind": kind,
        "complete": True,
        "model_id": None,
        "model_revision": None,
        "parents": [],
        "producer_tool": "harness",
    }


def _field(value: Any, unit: str | None) -> dict[str, Any]:
    return {"value": value, "unit": unit, "source": SRC, "confirmed": True, "citation": None}


@settings(derandomize=True, max_examples=300, deadline=None)
@given(required=_positive, increment=_positive)
def test_rounding_properties(required: float, increment: float) -> None:
    """AC41: on exact fractions, size = n x increment, integer n >= 1, size >= required, size < required + increment."""
    definition = REGISTRY["harness.section_round"]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    fields = {"modeling.section_increment_mm": _field(increment, "mm"), "modeling.section_rounding": _field("up", None)}
    inp = input_type.model_validate(
        {"required": {"value": required, "unit": "mm"}, "basis": {"template": None, "fields": fields}}
    )
    meta = InputMeta.model_validate({"refs": {"basis": _ref(9, "basis.design_basis/1")}})
    out = definition(inp, meta, TraceBuilder()).model_dump(mode="json")
    r, i, n = Fraction(required), Fraction(increment), out["multiple"]
    assert type(n) is int
    assert n >= 1
    assert out["size"] == {"value": float(n * i), "unit": "mm"}
    assert n * i >= r
    assert n * i - r < i
