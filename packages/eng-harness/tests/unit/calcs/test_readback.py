"""Calc 3, read-back check (plan 0003 T9; spec 0003 4.8, AC30 to AC34): independence, effects, changes, status."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

CALC_ID = "harness.readback_check"
MDL = "mdl_00000000000000000000000000"
OTHER = "mdl_00000000000000000000000001"
FP = "model.frame_placements/1"
SECTIONS = "model.sections/1"
LOADS = "model.load_set/1"
CHANGE_SET = "res_00000000000000000000000005"
HINT = "read the after state from the model after the write, and the effects from the change set only"
UNITS = {
    "compare.length_mm": "mm",
    "compare.angle_deg": "deg",
    "compare.stress_MPa": "MPa",
    "compare.unit_weight_kN_m3": "kN/m3",
    "compare.line_load_kN_m": "kN/m",
    "compare.area_load_kPa": "kPa",
    "compare.dimensionless_ratio": "1",
}


def _frame(fid: str, *, section: str = "S1", x: float = 0.0) -> dict[str, Any]:
    return {
        "id": fid,
        "kind": "column",
        "section": section,
        "i": {"x_mm": x, "y_mm": 0.0, "z_mm": 0.0},
        "j": {"x_mm": x, "y_mm": 0.0, "z_mm": 3000.0},
        "rotation_deg": 0.0,
    }


def _frames(*frames: dict[str, Any]) -> dict[str, Any]:
    return {"frames": list(frames)}


def _field(value: Any, unit: str | None) -> dict[str, Any]:
    source = "engineer:synthetic@2026-01-01T00:00:00.000Z"
    return {"value": value, "unit": unit, "source": source, "confirmed": True, "citation": None}


def _basis(**values: float) -> dict[str, Any]:
    return {"template": None, "fields": {p: _field(values.get(p, 1.0), u) for p, u in UNITS.items()}}


def _rid(n: int) -> str:
    return f"res_{n:026d}"


def _ref(
    n: int,
    kind: str,
    *,
    revision: int | None = 3,
    model: str | None = MDL,
    complete: bool = True,
    parents: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "result_id": _rid(n),
        "kind": kind,
        "complete": complete,
        "model_id": model if revision is not None else None,
        "model_revision": revision,
        "parents": list(parents),
        "producer_tool": "csi" if revision is not None else "harness",
    }


def _effect(item_id: str, section: str, key: list[str], op: str, **rest: Any) -> dict[str, Any]:
    return {"item_id": item_id, "section": section, "key": key, "op": op, **rest}


def _effects(*effects: dict[str, Any]) -> dict[str, Any]:
    return {"change_set": CHANGE_SET, "model_id": MDL, "effects": list(effects)}


def _meta(**refs: Any) -> dict[str, Any]:
    base = {
        "basis": _ref(9, "basis.design_basis/1", revision=None),
        "effects": _ref(8, "harness.expected_effects/1", revision=None, parents=(CHANGE_SET, _rid(1))),
    }
    return base | refs


def _frames_refs(before: int = 3, after: int = 4) -> dict[str, Any]:
    return {"before_frames": _ref(1, FP, revision=before), "after_frames": _ref(2, FP, revision=after)}


def _run(fields: dict[str, Any], refs: dict[str, Any], trace: TraceBuilder | None = None) -> dict[str, Any]:
    definition = REGISTRY[CALC_ID]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    inp = input_type.model_validate({"basis": _basis(), **fields})
    body = definition(inp, InputMeta.model_validate({"refs": refs}), trace or TraceBuilder())
    return body.model_dump(mode="json")


def _refused(fields: dict[str, Any], refs: dict[str, Any]) -> ContractError:
    with pytest.raises(ContractError) as caught:
        _run(fields, refs)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    return caught.value


SET_SECTION = _effect("e1", FP, ["frames", "F1"], "set", pointer="/section", value="S2")


def test_not_read() -> None:
    """AC32: an effect on a section the after read set does not hold is `not_read`: NEEDS_ENGINEER unless one fails."""
    thickness = _effect("e2", SECTIONS, ["area_sections", "W1"], "set", pointer="/thickness_mm", value=200.0)
    fields = {
        "before_frames": _frames(_frame("F1")),
        "after_frames": _frames(_frame("F1", section="S2")),
        "effects": _effects(SET_SECTION, thickness),
    }
    out = _run(fields, _meta(**_frames_refs()))
    assert out["items"] == [
        {"item_id": "e1", "result": "match", "expected": "S2", "read": "S2", "tolerance": None, "rule": "D4"},
        {"item_id": "e2", "result": "not_read", "expected": 200.0, "read": None, "tolerance": None, "rule": "R2"},
    ]
    assert (out["status"], out["unexpected"], out["complete"]) == ("NEEDS_ENGINEER", [], True)
    # a section read before but not after is not read either, and the report does not compare it (D1)
    area = {"name": "W1", "material": "C30", "kind": "wall", "thickness_mm": 250.0}
    fields_before = fields | {"before_sections": {"frame_sections": [], "area_sections": [area]}}
    refs = _meta(**_frames_refs(), before_sections=_ref(3, SECTIONS))
    out = _run(fields_before, refs)
    assert [i["result"] for i in out["items"]] == ["match", "not_read"]
    assert (out["status"], out["diff"]["not_compared"], out["complete"]) == ("NEEDS_ENGINEER", [SECTIONS], False)
    # another item that fails makes the whole check FAIL; the gap stays `not_read`
    added = _effect("e3", FP, ["frames", "F9"], "add", value=_frame("F9", x=6000.0))
    out = _run(fields | {"effects": _effects(SET_SECTION, thickness, added)}, _meta(**_frames_refs()))
    assert [i["result"] for i in out["items"]] == ["match", "not_read", "missing"]
    assert out["items"][2] == {
        "item_id": "e3", "result": "missing", "expected": _frame("F9", x=6000.0), "read": None, "tolerance": None,
        "rule": "R2",
    }  # fmt: skip
    assert out["status"] == "FAIL"


def test_circular_inputs_refused() -> None:
    """AC33 (R0, ب5): after not a later revision of the same model, one record on both sides, effects from after."""
    frames = _frames(_frame("F1"))
    fields = {"before_frames": frames, "after_frames": frames, "effects": _effects(SET_SECTION)}
    later = "the after records must be a later revision of the before records' model"
    same_record = {"before_frames": _ref(1, FP), "after_frames": _ref(1, FP)}
    for refs in (
        same_record,
        _frames_refs(before=3, after=3),
        _frames_refs(before=4, after=3),
        _frames_refs() | {"after_frames": _ref(2, FP, revision=4, model=OTHER)},
    ):
        error = _refused(fields, _meta(**refs))
        assert (error.detail.field, error.detail.message, error.detail.hint) == ("after", later, HINT)
    # the after record is a before record, even at a later revision (the check never compares a value with itself)
    error = _refused(fields, _meta(before_frames=_ref(1, FP), after_frames=_ref(1, FP, revision=4)))
    assert (error.detail.field, error.detail.message, error.detail.hint) == (
        "after", "an after record is also a before record", HINT,
    )  # fmt: skip
    # one of several after records is a before record
    loads: dict[str, Any] = {"patterns": [], "combinations": [], "frame_loads": [], "area_loads": []}
    both = fields | {"before_loads": loads, "after_loads": loads}
    refs = _frames_refs() | {"before_loads": _ref(3, LOADS), "after_loads": _ref(3, LOADS, revision=4)}
    error = _refused(both, _meta(**refs))
    assert error.detail.message == "an after record is also a before record"
    # the expected effects derive from an after record
    effects = _ref(8, "harness.expected_effects/1", revision=None, parents=(CHANGE_SET, _rid(2)))
    error = _refused(fields, _meta(**_frames_refs(), effects=effects))
    assert (error.detail.field, error.detail.message, error.detail.hint) == (
        "effects", "the expected effects have an after record among their parents", HINT,
    )  # fmt: skip
    # the effects must come from a record
    refs = _meta(**_frames_refs())
    del refs["effects"]
    error = _refused(fields, refs)
    assert (error.detail.field, error.detail.message) == ("effects", "the effects must be a record reference")
    # a later revision of the same model, with effects from the change set and the before record, is accepted
    assert _run(fields, _meta(**_frames_refs()))["status"] == "FAIL"  # e1 expects S2, F1 still reads S1
