"""The result codec (plan task T7; spec 0001 section 4.5.2 "Codec", AC11)."""

import pytest
from eng_contract.canonical import CanonicalJsonError, canonical_json, loads
from eng_contract.quantity import LabeledQuantity, Quantity
from eng_contract.refs import Ref

from eng_harness.ctx import ToolResult
from eng_harness.engine._codec import decode, decode_summary

RESULT = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
SUMMARY = {
    "depth": {"value": 450.0, "unit": "mm"},
    "forces": [{"value": 12.5, "unit": "kN", "member": "B1", "combo": 3}, {"value": 0.0, "unit": "kN"}],
    "nested": {"a": {"b": {"value": 2, "unit": "m"}}},
    "count": 3,
    "name": "beam",
    "flag": True,
    "none": None,
}


def _journaled(summary: object) -> object:
    """What the journal stores and a resume reads back: canonical bytes parsed by the contract's parser."""
    return loads(canonical_json(summary))


def _tool_result(summary: dict[str, object]) -> ToolResult:
    return ToolResult.model_validate(
        {"tool": "t/x", "ref": Ref(ref=RESULT), "summary": summary, "warnings": (), "complete": True, "model": None}
    )


def test_live_equals_replayed() -> None:
    live = decode_summary(SUMMARY)
    replayed = decode_summary(_journaled(SUMMARY))
    assert live == replayed
    assert isinstance(live["depth"], Quantity)
    assert live["depth"] == Quantity(450.0, "mm")
    forces = live["forces"]
    assert isinstance(forces, list)
    assert isinstance(forces[0], LabeledQuantity)
    assert forces[0].model_extra == {"member": "B1", "combo": 3}
    assert live["count"] == 3
    assert live["flag"] is True
    assert _tool_result(live) == _tool_result(replayed)
    assert isinstance(_tool_result(live).summary["depth"], Quantity)


def test_integral_float_is_rebuilt_as_float() -> None:
    """Canonical JSON writes 450.0 as 450; the codec must still give a float quantity."""
    wire = _journaled({"value": 450.0, "unit": "mm"})
    assert wire == {"value": 450, "unit": "mm"}
    rebuilt = decode(wire)
    assert isinstance(rebuilt, Quantity)
    assert isinstance(rebuilt.value, float)


def test_only_quantity_objects_are_rebuilt() -> None:
    assert decode({"value": 1, "unit": "not-a-unit"}) == {"value": 1, "unit": "not-a-unit"}
    assert decode({"value": "1", "unit": "mm"}) == {"value": "1", "unit": "mm"}
    assert decode({"value": True, "unit": "mm"}) == {"value": True, "unit": "mm"}
    assert decode({"value": 1}) == {"value": 1}
    assert decode({"value": 1, "unit": "mm", "meta": {"x": 1}}) == {"value": 1, "unit": "mm", "meta": {"x": 1}}


def test_value_passes_through_canonical_form() -> None:
    assert decode({"x": 1.0}) == {"x": 1}
    with pytest.raises(CanonicalJsonError):
        decode({"x": float("nan")})
    with pytest.raises(CanonicalJsonError):
        decode({"x": (1, 2)})


def test_decode_summary_needs_an_object() -> None:
    with pytest.raises(CanonicalJsonError):
        decode_summary([1])
