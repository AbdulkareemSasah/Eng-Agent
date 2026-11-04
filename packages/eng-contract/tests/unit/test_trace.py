"""Trace, TraceInput, TraceConstant, TraceStep (plan T10; spec 4.9.3)."""

from typing import Any

import pytest
from pydantic import ValidationError

from eng_contract.errors import ErrorCode
from eng_contract.trace import Trace
from eng_contract.units import UnitError

_SHA = "a" * 64
_SRC = "ACI 318-14 Table 21.2.1(b)"


def _step(name: str, uses: list[str], value: Any = 1, **over: Any) -> dict[str, Any]:
    return {"name": name, "value": value, "formula": "f", "source": "22.5.1", "uses": uses} | over


def _trace(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "calc_id": "aci318_14.flexure.beam_moment",
        "calc_version": "1.0.0",
        "content_sha256": _SHA,
        "subject": {"kind": "frame", "id": "B1"},
        "inputs": [{"name": "Vc", "value": 100.0, "unit": "kN", "ref": None}],
        "constants": [{"name": "phi", "cited": {"value": 0.75, "unit": "1", "source": _SRC}}],
        "steps": [_step("phiVc", ["phi", "Vc"], 75.0, unit="kN"), _step("ok", ["phiVc"], True)],
        "outputs": ["phiVc", "Vc"],
        "status": "PASS",
        "messages": ["note"],
    }
    base.update(over)
    return base


def test_valid_trace_round_trips() -> None:
    t = Trace.model_validate(_trace())
    assert t.steps[0].uses == ["phi", "Vc"]
    assert Trace.model_validate(t.model_dump(mode="json")) == t
    minimal = Trace.model_validate(
        {
            "calc_id": "harness.load_take.down",
            "calc_version": "1",
            "content_sha256": _SHA,
            "inputs": [],
            "constants": [],
            "steps": [],
            "outputs": [],
        }
    )
    assert minimal.subject is None
    assert minimal.status is None
    assert minimal.messages == []


@pytest.mark.parametrize(
    "over",
    [
        {"calc_id": "Harness.x"},
        {"calc_id": "harness."},
        {"calc_id": "not-a-calc"},
        {"calc_version": "v" * 65},
        {"content_sha256": "A" * 64},
        {"content_sha256": "a" * 63},
        {"status": "MAYBE"},
        {"outputs": ["missing"]},
        {"inputs": [{"name": "1bad", "value": 1}]},
        {"inputs": [{"name": "Vc", "value": 1, "ref": "no id"}]},
        {"steps": [_step("s", [], [1])]},
        {"steps": [_step("s", [], formula="f" * 1001)]},
        {"steps": [_step("s", [], source="x" * 501)]},
    ],
)
def test_rejects_invalid_fields(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Trace.model_validate(_trace(**over))


def test_names_are_unique_across_inputs_constants_and_steps() -> None:
    with pytest.raises(ValidationError):
        Trace.model_validate(_trace(steps=[_step("phi", [])], outputs=[]))
    with pytest.raises(ValidationError):
        Trace.model_validate(_trace(inputs=[{"name": "phi", "value": 2}], outputs=[]))
    dup_in = {"name": "Vc", "value": 2}
    with pytest.raises(ValidationError):
        Trace.model_validate(_trace(inputs=[dup_in, dup_in]))


def test_uses_must_name_earlier_entries() -> None:
    with pytest.raises(ValidationError):
        Trace.model_validate(_trace(steps=[_step("a", ["b"]), _step("b", [])], outputs=["a"]))
    with pytest.raises(ValidationError):
        Trace.model_validate(_trace(steps=[_step("a", ["a"])], outputs=["a"]))
    with pytest.raises(ValidationError):
        Trace.model_validate(_trace(steps=[_step("a", ["z"])], outputs=["a"]))


def test_outputs_may_name_steps_and_inputs_only() -> None:
    with pytest.raises(ValidationError):
        Trace.model_validate(_trace(outputs=["phi"]))  # a constant is not an output
    assert Trace.model_validate(_trace(outputs=[])).outputs == []


def test_unknown_unit_raises_unit_error() -> None:
    for over in (
        {"inputs": [{"name": "Vc", "value": 1, "unit": "furlong"}]},
        {"steps": [_step("s", [], unit="furlong")]},
    ):
        with pytest.raises(UnitError) as info:
            Trace.model_validate(_trace(outputs=[], **over))
        assert info.value.detail.code is ErrorCode.UNIT_MISMATCH
