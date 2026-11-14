"""Calc 3, read-back check (plan 0003 T9; spec 0003 4.8, AC30 to AC34): independence, effects, changes, status."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.readback_check import ReadbackInput, _explained, locate, read_pointer
from eng_harness.kinds.calcs import Effect

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


def _loads(*rows: dict[str, Any], combos: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    pattern = {"name": "DEAD", "type": "dead", "self_weight_ratio": 1.0}
    return {"patterns": [pattern], "combinations": combos or [], "frame_loads": list(rows), "area_loads": []}


def _load(w: float) -> dict[str, Any]:
    return {"frame": "F1", "pattern": "DEAD", "direction": "gravity", "w_kN_m": w}


LOAD_KEY = ["frame_loads", "F1", "DEAD", "gravity"]


def test_locate_follows_the_reported_keys() -> None:
    """R2 finds an object by the D2 key of the report: list name, key members, nested lists under the parent key."""
    item = {"case": {"case": "DEAD", "case_type": "load_pattern", "step": None}, "scale_ratio": 1.2}
    stepped = {"case": {"case": "DEAD", "case_type": "load_pattern", "step": "Max"}, "scale_ratio": 1.5}
    combo = {"name": "C1", "type": "linear_add", "items": [item, stepped]}
    payload = _loads(_load(10.0), combos=[combo])
    assert list(locate(LOADS, payload, ())) == [payload]
    assert list(locate(LOADS, payload, ("frame_loads", "F1", "DEAD", "gravity"))) == [_load(10.0)]
    assert list(locate(LOADS, payload, ("combinations", "C1"))) == [combo]
    assert list(locate(LOADS, payload, ("combinations", "C1", "items", "DEAD", "load_pattern"))) == [item]
    assert list(locate(LOADS, payload, ("combinations", "C1", "items", "DEAD", "load_pattern", "Max"))) == [stepped]
    for absent in (("combinations", "C2"), ("patterns", "LIVE"), ("frame_loads", "F1"), ("unknown", "F1")):
        assert list(locate(LOADS, payload, absent)) == [], absent
    assert list(locate(LOADS, payload, ("combinations", "C1", "items", "DEAD", "load_pattern", "Min"))) == []
    frames = _frames(_frame("F1"), _frame("F2"), _frame("F1"))
    assert list(locate(FP, frames, ("frames", "F1"))) == [_frame("F1"), _frame("F1")]
    assert list(locate(FP, frames, ("frames", "F1", "extra"))) == []
    assert list(locate(SECTIONS, frames, ("frames", "F1"))) == []  # the list must be one of the section's kind


def test_read_pointer() -> None:
    """A JSON pointer into a read object; an absent member or index reads as null (D5)."""
    value = {"i": {"x_mm": 5.0}, "points": [{"x_mm": 1.0}, {"x_mm": 2.0}], "a/b": 3, "a~b": 4, "n": 7}
    assert read_pointer(value, "") == value
    assert read_pointer(value, "/i/x_mm") == 5.0
    assert read_pointer(value, "/points/1/x_mm") == 2.0
    assert read_pointer(value, "/points/0") == {"x_mm": 1.0}
    assert (read_pointer(value, "/a~1b"), read_pointer(value, "/a~0b")) == (3, 4)
    for absent in ("/points/2", "/points/x", "/points/-1", "/missing", "/n/x", "/i/x_mm/y"):
        assert read_pointer(value, absent) is None, absent


def _results(fields: dict[str, Any], *effects: dict[str, Any]) -> dict[str, Any]:
    return _run(fields | {"effects": _effects(*effects)}, _meta(**_frames_refs()))


def test_set_add_remove() -> None:
    """R2: `set` compares the value at the pointer, `add` every leaf of the object, `remove` wants it gone."""
    moved = _frame("F2", x=6000.5)
    fields = {"before_frames": _frames(_frame("F1")), "after_frames": _frames(_frame("F1"), moved)}
    moved |= {"i_joint": None, "j_joint": None, "story": None}  # the read object, with its null members
    add_near = _effect("a1", FP, ["frames", "F2"], "add", value=_frame("F2", x=6000.0))  # 0.5 mm within 1 mm
    add_far = _effect("a2", FP, ["frames", "F2"], "add", value=_frame("F2", x=6002.0))  # 1.5 mm off
    add_type = _effect("a3", FP, ["frames", "F2"], "add", value=_frame("F2", section="S9", x=6000.5))
    gone = _effect("r1", FP, ["frames", "F3"], "remove")
    kept = _effect("r2", FP, ["frames", "F1"], "remove")
    unset = _effect("s1", FP, ["frames", "F7"], "set", pointer="/section", value="S2")
    noop = _effect("s2", FP, ["frames", "F1"], "set", pointer="/i/x_mm", value=0.0, unit="mm")
    out = _results(fields, add_near, add_far, add_type, gone, kept, unset, noop)
    assert out["items"] == [
        {"item_id": "a1", "result": "match", "expected": _frame("F2", x=6000.0), "read": moved, "tolerance": None,
         "rule": "R2"},
        {"item_id": "a2", "result": "mismatch", "expected": _frame("F2", x=6002.0), "read": moved, "tolerance": None,
         "rule": "R2"},
        {"item_id": "a3", "result": "mismatch", "expected": _frame("F2", section="S9", x=6000.5), "read": moved,
         "tolerance": None, "rule": "R2"},
        {"item_id": "r1", "result": "match", "expected": None, "read": None, "tolerance": None, "rule": "R2"},
        {"item_id": "r2", "result": "mismatch", "expected": None, "read": moved | _frame("F1"), "tolerance": None,
         "rule": "R2"},
        {"item_id": "s1", "result": "missing", "expected": "S2", "read": None, "tolerance": None, "rule": "R2"},
        {"item_id": "s2", "result": "match", "expected": 0.0, "read": 0.0, "tolerance": 1.0, "rule": "D3"},
    ]  # fmt: skip
    assert (out["status"], out["unexpected"]) == ("FAIL", [])  # the added F2 is explained by the add effects
    only_near = _results(fields, add_near)
    assert (only_near["status"], only_near["complete"]) == ("PASS", True)


def test_set_tolerance_boundary() -> None:
    """R2 by D3: a read value exactly the tolerance away matches, one representable step further does not."""
    fields = {"before_loads": _loads(_load(10.0)), "after_loads": _loads(_load(12.5)), "before_frames": _frames()}
    fields |= {"after_frames": _frames()}
    refs = _meta(**_frames_refs(), before_loads=_ref(3, LOADS), after_loads=_ref(4, LOADS, revision=4))
    for expected, result in ((12.0, "match"), (13.0, "match"), (11.999999999999998, "mismatch")):
        effect = _effect("e1", LOADS, LOAD_KEY, "set", pointer="/w_kN_m", value=expected, unit="kN/m")
        basis = _basis(**{"compare.line_load_kN_m": 0.5})
        body = _run(fields | {"effects": _effects(effect), "basis": basis}, refs)
        assert body["items"][0]["result"] == result, expected
        assert (body["items"][0]["tolerance"], body["items"][0]["rule"]) == (0.5, "D3")
    # a string against a number compares exactly (D4), never within a tolerance
    effect = _effect("e1", LOADS, LOAD_KEY, "set", pointer="/w_kN_m", value="12.5")
    out = _run(fields | {"effects": _effects(effect)}, refs)
    assert out["items"][0] == {
        "item_id": "e1", "result": "mismatch", "expected": "12.5", "read": 12.5, "tolerance": None, "rule": "D4",
    }  # fmt: skip


def test_set_of_an_object_compares_leaf_by_leaf() -> None:
    """R2: a `set` of a whole object (spec 0007 4.4.2) is compared leaf by leaf (D3 to D5), not as canonical bytes."""

    def combo(scale: float, step: dict[str, Any]) -> dict[str, Any]:
        case = {"case": "DEAD", "case_type": "load_pattern"} | step
        return {"name": "C1", "type": "linear_add", "items": [{"case": case, "scale_ratio": scale}]}

    loads = _loads(combos=[combo(1.4000001, {})])  # unchanged, so R3 has nothing to explain
    fields = {"before_loads": loads, "after_loads": loads}
    fields |= {
        "before_frames": _frames(),
        "after_frames": _frames(),
        "basis": _basis(**{"compare.dimensionless_ratio": 0.001}),
    }
    refs = _meta(**_frames_refs(), before_loads=_ref(3, LOADS), after_loads=_ref(4, LOADS, revision=4))
    read = combo(1.4000001, {"step": None})  # the read object holds the omitted `step` as null
    cases = [("", combo(1.4, {}), read, "match"), ("", combo(1.402, {}), read, "mismatch")]
    cases += [("/items", combo(1.4, {})["items"], read["items"], "match")]
    cases += [("", combo(1.4, {"step": "Max"}), read, "mismatch")]
    for pointer, value, expected_read, result in cases:
        effect = _effect("e1", LOADS, ["combinations", "C1"], "set", pointer=pointer, value=value)
        out = _run(fields | {"effects": _effects(effect)}, refs)
        assert out["items"] == [
            {"item_id": "e1", "result": result, "expected": value, "read": expected_read, "tolerance": None,
             "rule": "R2"}
        ], (pointer, value)  # fmt: skip
        assert out["status"] == ("PASS" if result == "match" else "FAIL")


def test_duplicate_keys_need_the_engineer() -> None:
    """A key twice in the after set: each object is compared; the report's ambiguous key gives NEEDS_ENGINEER (R3)."""
    fields = {"before_loads": _loads(_load(10.0)), "after_loads": _loads(_load(12.0), _load(12.0))}
    fields |= {"before_frames": _frames(), "after_frames": _frames()}
    refs = _meta(**_frames_refs(), before_loads=_ref(3, LOADS), after_loads=_ref(4, LOADS, revision=4))
    effect = _effect("e1", LOADS, LOAD_KEY, "set", pointer="/w_kN_m", value=12.0, unit="kN/m")
    out = _run(fields | {"effects": _effects(effect)}, refs)
    assert out["items"][0]["read"] == [12.0, 12.0]
    assert (out["items"][0]["result"], out["unexpected"]) == ("match", [])
    assert (out["status"], out["complete"]) == ("NEEDS_ENGINEER", False)
    split = fields | {"after_loads": _loads(_load(12.0), _load(20.0))}
    out = _run(split | {"effects": _effects(effect)}, refs)
    assert (out["items"][0]["result"], out["items"][0]["read"], out["status"]) == ("mismatch", [12.0, 20.0], "FAIL")


def test_incomplete_side_needs_the_engineer() -> None:
    """R4: every effect matched and nothing unexpected, but a side incomplete: NEEDS_ENGINEER."""
    fields = {
        "before_frames": _frames(_frame("F1")),
        "after_frames": _frames(_frame("F1", section="S2")),
        "effects": _effects(SET_SECTION),
    }
    refs = _meta(**_frames_refs() | {"after_frames": _ref(2, FP, revision=4, complete=False)})
    out = _run(fields, refs)
    assert (out["status"], out["complete"], out["items"][0]["result"]) == ("NEEDS_ENGINEER", False, "match")
    assert _run(fields, _meta(**_frames_refs()))["status"] == "PASS"


def _e(section: str, key: list[str], pointer: str | None, op: str = "set") -> Effect:
    value: Any = {"id": "x"} if op == "add" else None
    fields = {"item_id": "e", "section": section, "key": key, "op": op, "value": value}
    return Effect.model_validate(fields | {"pointer": pointer if op == "set" else None})


def test_explained_by_section_key_and_pointer_prefix() -> None:
    """R3: same section, same key (list name included), and a pointer equal to or a prefix of the property's."""
    key = ["frames", "F1"]
    assert _explained([_e(FP, key, "/i")], FP, key, "/i/x_mm")
    assert _explained([_e(FP, key, "/i/x_mm")], FP, key, "/i/x_mm")
    assert _explained([_e(FP, key, "")], FP, key, "/i/x_mm")
    assert _explained([_e(FP, key, None, "add")], FP, key, "")
    assert _explained([_e(FP, key, None, "remove")], FP, key, "/section")
    assert not _explained([_e(FP, key, "/i")], FP, key, "/id")
    assert not _explained([_e(FP, key, "/i/x_mm")], FP, key, "/i")
    assert not _explained([_e(FP, key, "/section")], FP, key, "")  # a set does not explain an added object
    assert not _explained([_e(FP, ["F1"], "/i")], FP, key, "/i/x_mm")  # the key carries its list (B-483)
    assert not _explained([_e(SECTIONS, key, "/i")], FP, key, "/i/x_mm")
    assert not _explained([], FP, key, "/i")
    assert _explained([_e(SECTIONS, key, "/i"), _e(FP, key, "/i")], FP, key, "/i/x_mm")


def test_unexpected_objects() -> None:
    """R3: an added or removed object that no effect names is unexpected with a null pointer."""
    fields = {"before_frames": _frames(_frame("F1"), _frame("F2")), "after_frames": _frames(_frame("F1"), _frame("F3"))}
    out = _results(fields, _effect("e1", FP, ["frames", "F2"], "set", pointer="/section", value="S1"))
    assert out["unexpected"] == [
        {"section": FP, "key": ["frames", "F2"], "pointer": None},
        {"section": FP, "key": ["frames", "F3"], "pointer": None},
    ]
    assert out["items"][0]["result"] == "missing"
    added = _effect("e2", FP, ["frames", "F3"], "add", value=_frame("F3"))
    out = _results(fields, _effect("e1", FP, ["frames", "F2"], "remove"), added)
    assert ([i["result"] for i in out["items"]], out["unexpected"], out["status"]) == (["match", "match"], [], "PASS")


def test_trace_and_schema() -> None:
    """Trace (4.8): the report's tolerances and counts, then the result counts (R2), unexpected (R3) and status (R4)."""
    trace = TraceBuilder()
    fields = {
        "before_frames": _frames(_frame("F1")),
        "after_frames": _frames(_frame("F1", section="S2"), _frame("F2")),
        "effects": _effects(SET_SECTION, _effect("e2", SECTIONS, ["area_sections", "W1"], "remove")),
    }
    _run(fields, _meta(**_frames_refs()), trace)
    built = trace.build(REGISTRY[CALC_ID], "ab" * 32)
    assert [i.name for i in built.inputs] == [p.replace(".", "_") for p in UNITS]
    steps = {s.name: s for s in built.steps}
    assert list(steps) == [
        "frames_counts", "identical", "match_items", "mismatch_items", "missing_items", "not_read_items",
        "unexpected_changes", "status",
    ]  # fmt: skip
    assert [steps[f"{r}_items"].value for r in ("match", "mismatch", "missing", "not_read")] == [1, 0, 0, 1]
    for result in ("match", "mismatch", "missing", "not_read"):
        step = steps[f"{result}_items"]
        assert (step.formula, step.source, step.uses) == (f"effects read back as {result}", "§4.8 R2", [])
    unexpected = steps["unexpected_changes"]
    assert (unexpected.value, unexpected.source, unexpected.uses) == (1, "§4.8 R3", ["identical"])
    assert unexpected.formula == "changes of the difference report that no effect explains"
    status = steps["status"]
    assert (status.value, status.source) == ("FAIL", "§4.8 R4")
    assert status.uses == [*(f"{r}_items" for r in ("match", "mismatch", "missing", "not_read")),
                           "unexpected_changes", "identical"]  # fmt: skip
    assert (
        status.formula
        == "FAIL: mismatch, missing or unexpected; else NEEDS_ENGINEER: not read or incomplete; else PASS"
    )
    assert built.outputs == ["identical", "status"]
    properties = ReadbackInput.model_json_schema()["properties"]
    assert properties["effects"]["x-eng"]["stale_ok"] is False
    assert properties["effects"]["x-eng"]["engineering_quantity"] is True
    assert properties["effects"]["x-eng"]["ref_kinds"] == ["harness.expected_effects/1"]
    assert {n for n, p in properties.items() if p["x-eng"]["stale_ok"]} == {
        n for n in properties if n.startswith("before_")
    }
