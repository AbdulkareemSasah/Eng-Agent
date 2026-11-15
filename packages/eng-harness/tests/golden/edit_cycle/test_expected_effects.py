"""Golden cases and contract of harness.expected_effects (plan 0007 T3; spec 0007 AC8, AC36, AC37, section 4.4.2)."""

import copy
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.calc import InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.edit_cycle.expected_effects import EffectsInput, expected_effects
from eng_harness.calcs.readback_check import ReadbackInput, readback_check
from eng_harness.kinds.calcs import ExpectedEffects

from . import EditCycleGoldenCase, load_cases

CALC_ID = "harness.expected_effects"
MDL = "mdl_00000000000000000000000000"
OTHER = "mdl_00000000000000000000000001"
DIGEST = "ab" * 32
KINDS = {
    "check": "harness.change_set_check/1",
    "change_set": "basis.engineer_input/1",
    "sections": "model.sections/1",
    "loads": "model.load_set/1",
    "restraints": "model.joint_restraints/1",
    "basis": "basis.design_basis/1",
}
"""The record kind of each reference input of `harness.expected_effects`."""
STATE = ("sections", "loads", "restraints")
STEMS = [
    "effects-assignments",
    "effects-combination-replace",
    "effects-loads",
    "effects-none-accepted",
    "effects-pattern-and-delete",
    "effects-restraints",
    "effects-wall-sections",
]
SYNTHETIC = "engineer:test@2026-01-01T00:00:00.000Z"
COMPARE = {
    "compare.length_mm": "mm",
    "compare.angle_deg": "deg",
    "compare.stress_MPa": "MPa",
    "compare.unit_weight_kN_m3": "kN/m3",
    "compare.line_load_kN_m": "kN/m",
    "compare.area_load_kPa": "kPa",
    "compare.dimensionless_ratio": "1",
}


def _case(stem: str = "effects-wall-sections") -> EditCycleGoldenCase:
    return load_cases("effects")[stem]


def meta_for(
    refs: dict[str, str], *, models: dict[str, str | None] | None = None, revisions: dict[str, int] | None = None
) -> InputMeta:
    """`InputMeta` of the effects calc: the state records are reads of model MDL, revision 3."""
    models = models or {}
    revisions = revisions or {}
    return InputMeta(
        refs={
            name: RefMeta(
                result_id=result_id,
                kind=KINDS[name],
                complete=True,
                model_id=models.get(name, MDL if name in STATE else None),
                model_revision=revisions.get(name, 3 if name in STATE else None),
                parents=(),
                producer_tool="csi" if name in STATE else "harness",
            )
            for name, result_id in refs.items()
        }
    )


def run_effects(
    case: EditCycleGoldenCase, *, trace: TraceBuilder | None = None, meta: InputMeta | None = None, **changes: Any
) -> dict[str, Any]:
    """Run `harness.expected_effects` on the case input with some input fields replaced."""
    inp = EffectsInput.model_validate(copy.deepcopy(case.input) | changes)
    return expected_effects(inp, meta or meta_for(case.refs), trace or TraceBuilder()).model_dump(mode="json")


def _refused(case: EditCycleGoldenCase, field: str, message: str, **kwargs: Any) -> None:
    meta = kwargs.pop("meta", None)
    with pytest.raises(ContractError) as caught:
        run_effects(case, meta=meta, **kwargs)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert (caught.value.detail.field, caught.value.detail.message) == (field, message)


def test_golden_cases() -> None:
    cases = load_cases("effects")
    assert sorted(cases) == STEMS
    actual = {stem: run_effects(case) for stem, case in cases.items()}
    assert {stem: body for stem, body in actual.items() if body != cases[stem].expected} == {}


def test_golden_bodies_are_valid_payloads() -> None:
    """The kind takes each golden body bare and with the calc port's wrapper (calc, draft, trace); amendment B-513."""
    wrapper = {
        "calc": {"id": CALC_ID, "version": 1, "content_sha256": DIGEST, "status": "draft"},
        "draft": True,
        "trace": {
            "calc_id": CALC_ID,
            "calc_version": "1",
            "content_sha256": DIGEST,
            "inputs": [],
            "constants": [],
            "steps": [],
            "outputs": [],
        },
    }
    for stem, case in load_cases("effects").items():
        bare = ExpectedEffects.model_validate(case.expected)
        assert (bare.calc, bare.draft, bare.trace) == (None, None, None), stem
        wrapped = ExpectedEffects.model_validate(case.expected | wrapper)
        assert wrapped.effects == bare.effects, stem
        assert wrapped.calc is not None, stem
        assert (wrapped.calc.id, wrapped.draft) == (CALC_ID, True), stem
        assert wrapped.trace is not None, stem
        assert wrapped.trace.calc_id == CALC_ID, stem


def test_registered_with_its_kind_and_inputs() -> None:
    definition = REGISTRY[CALC_ID]
    assert (definition.version, definition.output_kind, definition.verification) == (1, f"{CALC_ID}/1", "draft")
    assert definition.input_type is EffectsInput
    properties = EffectsInput.model_json_schema()["properties"]
    assert {name: properties[name]["x-eng"]["ref_kinds"] for name in KINDS} == {n: [k] for n, k in KINDS.items()}
    assert not any(properties[name]["x-eng"]["stale_ok"] for name in KINDS)
    assert "x-eng" not in properties["approval_items"]
    assert set(properties) == {*KINDS, "approval_items"}


def test_trace_records_items_basis_values_count_and_output() -> None:
    case = _case()
    trace = TraceBuilder()
    run_effects(case, trace=trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    inputs = {i.name: i for i in built.inputs}
    assert list(inputs) == ["items", "geometry_wall_thickness_mm"]
    assert (inputs["items"].value, inputs["items"].ref) == (2, f"{case.refs['check']}#/resolved")
    thickness = inputs["geometry_wall_thickness_mm"]
    assert (thickness.value, thickness.unit) == (300.0, "mm")
    assert thickness.ref == f"{case.refs['basis']}#/fields/geometry.wall_thickness_mm"
    (step,) = built.steps
    assert (step.name, step.value, step.source) == ("effects", 3, "spec 0007 4.4.2")
    assert step.uses == ["items", "geometry_wall_thickness_mm"]
    assert built.outputs == ["effects"]


def test_a_basis_path_is_traced_once() -> None:
    case = _case("effects-loads")
    twice = [
        item | {"q": {"source": "basis", "path": "loads.live_kPa"}} for item in case.input["change_set"]["items"][1:]
    ]
    items = [case.input["change_set"]["items"][0], *twice]
    trace = TraceBuilder()
    body = run_effects(case, trace=trace, change_set={"items": items})
    assert [e["value"] for e in body["effects"] if e["pointer"] == "/q_kPa"] == [3.0]
    assert [i.name for i in trace.build(REGISTRY[CALC_ID], DIGEST).inputs] == ["items", "loads_live_kPa"]


def test_literal_in_metres_is_converted_to_millimetres() -> None:
    """Baseline د6: 0.2 m is 200 mm, never 0.2 and never 200000."""
    case = _case()
    item = case.input["change_set"]["items"][0] | {"thickness": {"source": "input", "value": 0.2, "unit": "m"}}
    body = run_effects(case, change_set={"items": [item]}, approval_items=["b1"])
    assert [e["value"] for e in body["effects"]] == ["C35", 200.0]


def test_no_accepted_item_gives_no_effect_but_names_the_change_set_and_model() -> None:
    case = _case("effects-none-accepted")
    body = run_effects(case)
    assert body == {"change_set": f"{case.refs['change_set']}#/fields/change_set/value", "model_id": MDL, "effects": []}


def test_a_new_combination_keeps_the_change_set_item_order() -> None:
    """Spec 0007 Q15 is open: until it is answered the projection keeps the order of the change set."""
    case = _case("effects-combination-replace")
    items = copy.deepcopy(case.input["change_set"]["items"])
    items[1]["items"].reverse()
    body = run_effects(case, change_set={"items": items})
    added = [e for e in body["effects"] if e["item_id"] == "e2"]
    assert [t["case"]["case"] for t in added[0]["value"]["items"]] == ["LIVE", "DEAD"]


def test_effects_do_not_depend_on_the_order_of_the_accepted_ids() -> None:
    case = _case("effects-loads")
    assert run_effects(case, approval_items=["c3", "c1", "c2"]) == case.expected


def test_item_ids_of_one_effect_stay_plain_and_of_several_are_numbered() -> None:
    body = run_effects(_case("effects-restraints"))
    assert [e["item_id"] for e in body["effects"]] == [*(f"f1/{n}" for n in range(1, 7)), "f2"]


def test_check_must_pass() -> None:
    case = _case()
    issue = {"item_id": "b1", "severity": "error", "code": "UNKNOWN_MATERIAL", "detail": "x", "gap": None}
    failed = case.input["check"] | {"status": "FAIL", "issues": [issue]}
    _refused(case, "check", "the check must have status PASS", check=failed)


def test_accepted_items_must_be_items_of_the_check() -> None:
    _refused(_case(), "approval_items", "accepted items not in the check: x1, x2", approval_items=["b1", "x2", "x1"])


def test_item_id_with_a_slash_is_refused() -> None:
    case = _case()
    check = copy.deepcopy(case.input["check"])
    check["resolved"][0]["item_id"] = "b/1"
    items = copy.deepcopy(case.input["change_set"]["items"])
    items[0]["id"] = "b/1"
    message = "item id b/1 contains a slash (INVALID_ITEM_ID, spec 0007 4.4.1 K3)"
    _refused(case, "approval_items", message, check=check, change_set={"items": items}, approval_items=["b/1"])


def test_accepted_item_must_be_in_the_change_set() -> None:
    case = _case()
    items = case.input["change_set"]["items"][1:]
    _refused(case, "change_set", "item b1 of the check is not in the change set", change_set={"items": items})


def test_item_value_must_be_resolved_by_the_check() -> None:
    case = _case()
    check = copy.deepcopy(case.input["check"])
    check["resolved"][0]["values"] = []
    _refused(case, "check", "item b1 has no resolved value at /thickness_mm", check=check)


@pytest.mark.parametrize("name", list(KINDS))
def test_each_input_must_be_a_record(name: str) -> None:
    case = _case()
    meta = meta_for({k: v for k, v in case.refs.items() if k != name})
    _refused(case, name, "each input must be a record reference", meta=meta)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"models": {"loads": OTHER}},
        {"models": {"restraints": None}},
        {"revisions": {"sections": 4}},
    ],
)
def test_state_records_must_be_one_model_revision(kwargs: dict[str, Any]) -> None:
    case = _case()
    message = "the state records must be reads of one host model revision"
    _refused(case, "sections", message, meta=meta_for(case.refs, **kwargs))


@pytest.mark.parametrize("change", [None, {"confirmed": False}, {"value": "thick"}])
def test_basis_value_must_be_present_confirmed_and_a_number(change: dict[str, Any] | None) -> None:
    case = _case()
    path = "geometry.wall_thickness_mm"
    fields = dict(case.input["basis"]["fields"])
    if change is None:
        del fields[path]
    else:
        fields[path] = fields[path] | change
    message = f"basis field {path} is missing, not confirmed or not a number"
    _refused(case, f"basis.fields.{path}", message, basis={"template": None, "fields": fields})


def _basis() -> dict[str, Any]:
    fields = {
        path: {"value": 0.001, "unit": unit, "source": SYNTHETIC, "confirmed": True, "citation": None}
        for path, unit in COMPARE.items()
    }
    return {"template": None, "fields": fields}


def _readback(effects: dict[str, Any], key: str, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """The read-back check of `effects` between a before and an after read of one section (plan 0003 T9)."""
    kind = KINDS[key]

    def ref(n: int, revision: int | None) -> RefMeta:
        return RefMeta(
            result_id=f"res_{n:026d}",
            kind=kind if revision else "harness.expected_effects/1",
            complete=True,
            model_id=MDL if revision else None,
            model_revision=revision,
            parents=() if revision else ("res_00000000000000000000000002", "res_00000000000000000000000011"),
            producer_tool="csi" if revision else "harness",
        )

    fields = {f"before_{key}": before, f"after_{key}": after, "effects": effects, "basis": _basis()}
    refs = {f"before_{key}": ref(11, 3), f"after_{key}": ref(12, 4), "effects": ref(13, None)}
    basis = RefMeta(
        result_id=f"res_{14:026d}",
        kind=KINDS["basis"],
        complete=True,
        model_id=None,
        model_revision=None,
        parents=(),
        producer_tool="harness",
    )
    out = readback_check(ReadbackInput.model_validate(fields), InputMeta(refs=refs | {"basis": basis}), TraceBuilder())
    return out.model_dump(mode="json")


def _term(case: str, case_type: str, scale: float) -> dict[str, Any]:
    return {"case": {"case": case, "case_type": case_type, "step": None}, "scale_ratio": scale}


def _combo_state(*items: dict[str, Any], frame_loads: list[dict[str, Any]]) -> dict[str, Any]:
    patterns = [
        {"name": n, "type": t, "self_weight_ratio": 0.0}
        for n, t in (("DEAD", "dead"), ("LIVE", "live"), ("WIND", "wind"))
    ]
    combo = {"name": "COMB1", "type": "linear_add", "items": list(items)}
    return {"patterns": patterns, "combinations": [combo], "frame_loads": frame_loads, "area_loads": []}


def _load(frame: str, w: float) -> dict[str, Any]:
    return {"frame": frame, "pattern": "DEAD", "direction": "gravity", "w_kN_m": w}


def test_combination_edit_reads_back() -> None:
    """AC36: a scale changed, a case added and one dropped, a frame load on a frame without one in the pattern."""
    case = _case("effects-loads")
    ref = {"source": "input", "unit": "1"}
    terms = [
        {"case": {"case": "DEAD", "case_type": "load_pattern"}, "scale": ref | {"value": 2.0}},
        {"case": {"case": "WIND", "case_type": "load_pattern"}, "scale": ref | {"value": 0.5}},
    ]
    items = [
        {"id": "x1", "kind": "load_combination_set", "name": "COMB1", "type": "linear_add", "items": terms},
        {
            "id": "x2",
            "kind": "frame_uniform_load",
            "frames": ["B2"],
            "pattern": "DEAD",
            "direction": "gravity",
            "w": {"source": "input", "value": 5.0, "unit": "kN/m"},
        },
    ]
    one = {"pointer": "/scale_ratio", "ref": f"{case.refs['change_set']}#/x", "unit": "1"}
    resolved = [
        {
            "item_id": "x1",
            "kind": "load_combination_set",
            "targets": ["COMB1"],
            "values": [one | {"pointer": f"/items/{n}/scale_ratio"} for n in range(2)],
        },
        {
            "item_id": "x2",
            "kind": "frame_uniform_load",
            "targets": ["B2"],
            "values": [one | {"pointer": "/w_kN_m", "unit": "kN/m"}],
        },
    ]
    before = _combo_state(
        _term("DEAD", "load_pattern", 1.0), _term("LIVE", "load_pattern", 1.0), frame_loads=[_load("B1", 10.0)]
    )
    check = case.input["check"] | {"resolved": resolved}
    effects = run_effects(case, change_set={"items": items}, check=check, approval_items=["x1", "x2"], loads=before)
    assert [(e["item_id"], e["op"]) for e in effects["effects"]] == [
        ("x1/1", "set"),
        ("x1/2", "set"),
        ("x1/3", "remove"),
        ("x1/4", "add"),
        ("x2", "add"),
    ]
    both = [_load("B1", 10.0), _load("B2", 5.0)]
    after = _combo_state(_term("DEAD", "load_pattern", 2.0), _term("WIND", "load_pattern", 0.5), frame_loads=both)
    done = _readback(effects, "loads", before, after)
    assert (done["status"], done["unexpected"]) == ("PASS", [])
    assert {i["result"] for i in done["items"]} == {"match"}
    stale = _combo_state(_term("DEAD", "load_pattern", 1.0), _term("WIND", "load_pattern", 0.5), frame_loads=both)
    failed = _readback(effects, "loads", before, stale)
    assert failed["status"] == "FAIL"
    assert [(i["item_id"], i["result"]) for i in failed["items"] if i["result"] != "match"] == [("x1/2", "mismatch")]


def _wall_sections(material: str, thickness: float) -> dict[str, Any]:
    wall = {"name": "W200", "material": material, "kind": "wall", "thickness_mm": thickness}
    return {"frame_sections": [], "area_sections": [wall]}


def test_wall_section_material_reads_back() -> None:
    """AC37: a wall section redefined with another material and thickness reads back; the old material fails."""
    case = _case()
    before = case.input["sections"]
    effects = run_effects(case, approval_items=["b1"])
    done = _readback(effects, "sections", before, _wall_sections("C35", 250.0))
    assert (done["status"], done["unexpected"]) == ("PASS", [])
    assert [(i["item_id"], i["result"]) for i in done["items"]] == [("b1/1", "match"), ("b1/2", "match")]
    old = _readback(effects, "sections", before, _wall_sections("C30", 250.0))
    assert (old["status"], old["unexpected"]) == ("FAIL", [])
    assert [(i["item_id"], i["result"]) for i in old["items"]] == [("b1/1", "mismatch"), ("b1/2", "match")]


def test_item_of_a_refused_kind_has_no_projection() -> None:
    case = _case()
    check = copy.deepcopy(case.input["check"])
    check["resolved"] = [{"item_id": "z1", "kind": "seismic_parameters", "targets": ["Z"], "values": []}]
    items = [{"id": "z1", "kind": "seismic_parameters"}]
    message = "item z1 of kind seismic_parameters has no projection"
    _refused(case, "check", message, check=check, change_set={"items": items}, approval_items=["z1"])
