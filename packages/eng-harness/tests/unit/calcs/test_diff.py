"""Calc 2, difference report (plan 0003 T8b; spec 0003 4.7, AC24 to AC28): basis, sides, gaps and the report."""

import json
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_harness.calcs.model_diff import BASIS_FIELDS, DiffInput
from pydantic import ValidationError

from eng_harness.calc import InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

CALC_ID = "harness.model_diff"
MDL = "mdl_00000000000000000000000000"
OTHER = "mdl_00000000000000000000000001"
BASIS_ID = "res_00000000000000000000000009"
FP = "model.frame_placements/1"
SECTIONS = "model.sections/1"
LOADS = "model.load_set/1"
UNITS = {
    "compare.length": "mm",
    "compare.angle": "deg",
    "compare.stress": "MPa",
    "compare.unit_weight": "kN/m3",
    "compare.line_load": "kN/m",
    "compare.area_load": "kPa",
    "compare.ratio": "1",
}
KINDS = {
    "compare.length": "length",
    "compare.angle": "angle",
    "compare.stress": "stress",
    "compare.unit_weight": "unit_weight",
    "compare.line_load": "line_load",
    "compare.area_load": "area_load",
    "compare.ratio": "dimensionless",
}
_NAMES = ("stories", "grids", "frames", "areas", "sections", "materials", "loads", "restraints")
GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden" / "calcs"


def _frame(fid: str, *, section: str = "S1", x: float = 0.0) -> dict[str, Any]:
    return {
        "id": fid,
        "kind": "column",
        "section": section,
        "i": {"x_mm": x, "y_mm": 0.0, "z_mm": 0.0},
        "j": {"x_mm": x, "y_mm": 0.0, "z_mm": 3000.0},
        "rotation_deg": 0.0,
    }


def _field(value: Any, unit: str | None) -> dict[str, Any]:
    source = "engineer:synthetic@2026-01-01T00:00:00.000Z"
    return {"value": value, "unit": unit, "source": source, "confirmed": True, "citation": None}


def _basis(**values: float) -> dict[str, Any]:
    return {"template": None, "fields": {p: _field(values.get(p, 1.0), u) for p, u in UNITS.items()}}


def _ref(n: int, kind: str, *, revision: int | None = 3, model: str | None = MDL, complete: bool = True) -> Any:
    return {
        "result_id": f"res_0000000000000000000000000{n}",
        "kind": kind,
        "complete": complete,
        "model_id": model if revision is not None else None,
        "model_revision": revision,
        "parents": [],
        "producer_tool": "csi",
    }


def _frames(*frames: dict[str, Any]) -> dict[str, Any]:
    return {"frames": list(frames)}


def _input(**fields: Any) -> dict[str, Any]:
    return {"basis": _basis(), **fields}


def _meta(**refs: Any) -> dict[str, Any]:
    return {"basis": _ref(9, "basis.design_basis/1", revision=None), **refs}


def _run(fields: dict[str, Any], refs: dict[str, Any], trace: TraceBuilder | None = None) -> dict[str, Any]:
    inp = DiffInput.model_validate(fields)
    body = REGISTRY[CALC_ID](inp, InputMeta.model_validate({"refs": refs}), trace or TraceBuilder())
    return body.model_dump(mode="json")


def _frames_run(before: dict[str, Any], after: dict[str, Any], **basis: float) -> dict[str, Any]:
    fields = {"before_frames": before, "after_frames": after, "basis": _basis(**basis)}
    return _run(fields, _meta(before_frames=_ref(1, FP), after_frames=_ref(2, FP, revision=4)))


def _refused(fields: dict[str, Any], refs: dict[str, Any]) -> ContractError:
    with pytest.raises(ContractError) as caught:
        _run(fields, refs)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    return caught.value


def _basis_refusal(basis: dict[str, Any]) -> ContractError:
    frames = _frames(_frame("F1"))
    fields = {"before_frames": frames, "after_frames": frames, "basis": basis}
    return _refused(fields, _meta(before_frames=_ref(1, FP), after_frames=_ref(2, FP)))


def test_basis_tolerances_required() -> None:
    """AC26: each 4.4 `compare.*` field must be present, confirmed, in its unit and >= 0; no default is used."""
    assert tuple(UNITS) == BASIS_FIELDS
    for path, unit in UNITS.items():
        name = f"basis.fields.{path}"
        missing = _basis()
        del missing["fields"][path]
        error = _basis_refusal(missing)
        assert (error.detail.field, error.detail.message) == (name, f"basis field {path} is missing (no default)")
        assert error.detail.hint == f"set and confirm {path} in the design basis"
        unconfirmed = _basis()
        unconfirmed["fields"][path]["confirmed"] = False
        error = _basis_refusal(unconfirmed)
        assert (error.detail.field, error.detail.message) == (name, f"basis field {path} is not confirmed")
        wrong = _basis()
        wrong["fields"][path]["unit"] = "kN"
        error = _basis_refusal(wrong)
        assert (error.detail.field, error.detail.message) == (name, f"basis field {path} must be in {unit}, not kN")
        for bad in (-1.0, -5e-324, "1", True, None):
            negative = _basis()
            negative["fields"][path]["value"] = bad
            error = _basis_refusal(negative)
            assert (error.detail.field, error.detail.message) == (name, f"basis field {path} must be a number >= 0")
    zero = _frames_run(_frames(_frame("F1")), _frames(_frame("F1")), **dict.fromkeys(UNITS, 0.0))
    assert zero["identical"] is True


def test_basis_must_be_a_record() -> None:
    frames = _frames(_frame("F1"))
    fields = _input(before_frames=frames, after_frames=frames)
    error = _refused(fields, {"before_frames": _ref(1, FP), "after_frames": _ref(2, FP)})
    assert (error.detail.field, error.detail.message) == ("basis", "the basis must be a record reference")


def test_tolerances_and_trace() -> None:
    """The tolerances are echoed per quantity kind with their basis ref, and recorded as trace inputs (4.7 Trace)."""
    trace = TraceBuilder()
    before, after = _frames(_frame("F1"), _frame("F2", x=6000.0)), _frames(_frame("F1", section="S2"))
    fields = {"before_frames": before, "after_frames": after, "basis": _basis(**{"compare.length": 0.25})}
    out = _run(fields, _meta(before_frames=_ref(1, FP), after_frames=_ref(2, FP, revision=4)), trace)
    assert out["tolerances"] == {
        KINDS[p]: {"value": 0.25 if p == "compare.length" else 1.0, "unit": u, "ref": f"{BASIS_ID}#/fields/{p}"}
        for p, u in UNITS.items()
    }
    built = trace.build(REGISTRY[CALC_ID], "ab" * 32)
    assert [(i.name, i.value, i.unit, i.ref) for i in built.inputs] == [
        (p.replace(".", "_"), 0.25 if p == "compare.length" else 1.0, u, f"{BASIS_ID}#/fields/{p}")
        for p, u in UNITS.items()
    ]
    names = [i.name for i in built.inputs]
    steps = {s.name: s for s in built.steps}
    assert list(steps) == ["frames_counts", "identical"]
    frames = steps["frames_counts"]
    assert frames.value == "added 0, removed 1, changed 1, ambiguous 0, unchanged 0, within tolerance 0"
    assert (frames.source, frames.uses) == ("§4.7 D1 to D5", names)
    assert frames.formula == f"objects of {FP} matched by key (D2), compared by D3 to D5"
    done = steps["identical"]
    assert (done.value, done.source, done.uses) == (False, "§4.7 D7", ["frames_counts"])
    assert done.formula == "no changes or ambiguous keys, nothing not compared, both sides complete"
    assert built.outputs == ["identical"]


def test_not_compared_and_ambiguous() -> None:
    """AC28: a section on one side only is `not_compared`, a duplicate key `ambiguous`; both make it incomplete."""
    row = {"frame": "F1", "pattern": "DEAD", "direction": "gravity", "w_kN_m": 10.0}
    loads = {
        "patterns": [{"name": "DEAD", "type": "dead", "self_weight_ratio": 1.0}],
        "combinations": [],
        "frame_loads": [row, row],
        "area_loads": [],
    }
    section = {"name": "S1", "material": "M1", "shape": {"type": "rectangular", "b_mm": 300.0, "h_mm": 500.0}}
    fields = _input(
        before_frames=_frames(_frame("F1")),
        before_loads=loads,
        after_loads=loads,
        after_sections={"frame_sections": [section], "area_sections": []},
    )
    refs = _meta(
        before_frames=_ref(1, FP), before_loads=_ref(2, LOADS), after_loads=_ref(3, LOADS, revision=4),
        after_sections=_ref(4, SECTIONS, revision=4),
    )  # fmt: skip
    out = _run(fields, refs)
    assert out["not_compared"] == [FP, SECTIONS]
    assert [(c["section"], c["key"], c["change"]) for c in out["changes"]] == [
        (LOADS, ["F1", "DEAD", "gravity"], "ambiguous")
    ]
    assert out["changes"][0]["before"] == out["changes"][0]["after"] == [row, row]
    assert list(out["counts"]) == [LOADS]
    assert out["counts"][LOADS]["ambiguous"] == 1
    assert (out["complete"], out["identical"]) == (False, False)
    assert out["before"]["covered"] == [FP, LOADS]
    assert out["after"]["covered"] == [LOADS, SECTIONS]
    only_gap = _input(before_frames=_frames(_frame("F1")), before_loads=loads | {"frame_loads": [row]})
    only_gap |= {"after_loads": loads | {"frame_loads": [row]}}
    out = _run(only_gap, _meta(before_frames=_ref(1, FP), before_loads=_ref(2, LOADS), after_loads=_ref(3, LOADS)))
    assert (out["changes"], out["not_compared"], out["complete"], out["identical"]) == ([], [FP], False, False)


def test_identical_and_incomplete() -> None:
    """D7: identical only with no change, nothing not compared and both sides complete; incomplete is still compared."""
    frames = _frames(_frame("F1"))
    same = _frames_run(frames, frames)
    assert (same["identical"], same["complete"], same["changes"]) == (True, True, [])
    assert same["counts"] == {
        FP: {"added": 0, "removed": 0, "changed": 0, "ambiguous": 0, "unchanged": 1, "within_tolerance": 0}
    }
    for side in ("before", "after"):
        refs = _meta(before_frames=_ref(1, FP), after_frames=_ref(2, FP))
        refs[f"{side}_frames"] = _ref(1, FP, complete=False)
        out = _run(_input(before_frames=frames, after_frames=_frames(_frame("F1", section="S2"))), refs)
        assert (out["identical"], out["complete"], len(out["changes"])) == (False, False, 1)


def test_sides_record_their_models() -> None:
    """Before and after may be different models (a working copy); each side records its own model and revision."""
    fields = _input(before_frames=_frames(_frame("F1")), after_frames=_frames(_frame("F1")))
    refs = _meta(before_frames=_ref(1, FP, revision=7), after_frames=_ref(2, FP, revision=2, model=OTHER))
    out = _run(fields, refs)
    assert out["before"] == {"model_id": MDL, "model_revision": 7, "covered": [FP]}
    assert out["after"] == {"model_id": OTHER, "model_revision": 2, "covered": [FP]}


def test_side_refusals() -> None:
    """A section given without a record, a record without a host model, or one side mixing revisions is refused."""
    frames, loads = _frames(_frame("F1")), {"patterns": [], "combinations": [], "frame_loads": [], "area_loads": []}
    for side in ("before", "after"):
        other = "after" if side == "before" else "before"
        fields = _input(**{f"{side}_frames": frames, f"{side}_loads": loads, f"{other}_frames": frames})
        good = {f"{side}_frames": _ref(1, FP), f"{side}_loads": _ref(2, LOADS), f"{other}_frames": _ref(3, FP)}
        error = _refused(fields, _meta(**{k: v for k, v in good.items() if k != f"{side}_loads"}))
        assert (error.detail.field, error.detail.message) == (f"{side}_loads", "a section must be a record reference")
        error = _refused(fields, _meta(**good | {f"{side}_loads": _ref(2, LOADS, revision=None)}))
        assert (error.detail.field, error.detail.message) == (f"{side}_loads", "the record names no host model")
        for mixed in (_ref(2, LOADS, revision=4), _ref(2, LOADS, model=OTHER)):
            error = _refused(fields, _meta(**good | {f"{side}_loads": mixed}))
            assert error.detail.field == f"{side}_loads"
            assert error.detail.message == "the records of one side belong to different models or revisions"


def test_each_side_needs_a_section() -> None:
    frames = _frames(_frame("F1"))
    for fields in (_input(before_frames=frames), _input(after_frames=frames), _input()):
        with pytest.raises(ValidationError, match="each side needs at least one section"):
            DiffInput.model_validate(fields)


def test_input_schema_marks_only_before_stale_ok() -> None:
    """4.13: every `before_*` field is `stale_ok`; no `after_*` field and not `basis`."""
    properties = DiffInput.model_json_schema()["properties"]
    flags = {name: prop["x-eng"]["stale_ok"] for name, prop in properties.items()}
    assert sorted(flags) == sorted([f"{s}_{n}" for s in ("before", "after") for n in _NAMES] + ["basis"])
    assert {name for name, flag in flags.items() if flag} == {f"before_{n}" for n in _NAMES}
    assert all(properties[name]["x-eng"]["engineering_quantity"] for name in flags)


def test_golden_tolerances_are_basis_values() -> None:
    """The golden files echo exactly the basis values they set (the hand-derived echo of 4.7 output `tolerances`)."""
    for path in sorted(GOLDEN.glob("diff-*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        fields = case["inputs"]["input"]["basis"]["fields"]
        echoed = {k: t["value"] for k, t in case["expected"]["tolerances"].items()}
        assert echoed == {KINDS[p]: f["value"] for p, f in fields.items()}, path.name
