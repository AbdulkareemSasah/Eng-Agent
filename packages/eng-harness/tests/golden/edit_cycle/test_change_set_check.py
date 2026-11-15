"""Golden cases and contract of harness.change_set_check (plan 0007 T2; spec 0007 AC4, AC5, AC7, section 4.4.1)."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.calc import TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.edit_cycle.change_set_check import BASIS_FIELDS, BOUNDS, CheckInput
from eng_harness.kinds.edit_cycle import ChangeSetCheck

from . import CHECK_KINDS, input_meta, load_cases, run_check

CALC_ID = "harness.change_set_check"
STEMS = [
    "check-bounds-edges",
    "check-bounds-unit-scale",
    "check-conflict-engineer",
    "check-duplicate-target",
    "check-item-id-refused-kind",
    "check-item-id-slash",
    "check-resolve-added-earlier",
    "check-resolve-empty-selection",
    "check-resolve-select",
    "check-source-missing",
    "check-unknown-names",
]
DIGEST = "ab" * 32
BEAM_LOAD = {"id": "a1", "kind": "frame_uniform_load", "frames": ["B1"], "pattern": "DEAD", "direction": "gravity"}


def _case(stem: str = "check-resolve-select") -> Any:
    return load_cases("check")[stem]


def _issues(body: dict[str, Any]) -> list[tuple[str, str]]:
    return [(issue["item_id"], issue["code"]) for issue in body["issues"]]


def test_golden_cases() -> None:
    cases = load_cases("check")
    assert sorted(cases) == STEMS
    actual = {stem: run_check(case) for stem, case in cases.items()}
    assert {stem: body for stem, body in actual.items() if body != cases[stem].expected} == {}


def test_golden_bodies_are_valid_payloads() -> None:
    trace = {"calc_id": CALC_ID, "calc_version": "1", "content_sha256": DIGEST}
    wrapper = {
        "calc": {"id": CALC_ID, "version": 1, "content_sha256": DIGEST, "status": "draft"},
        "draft": True,
        "trace": trace | {"inputs": [], "constants": [], "steps": [], "outputs": []},
    }
    for case in load_cases("check").values():
        ChangeSetCheck.model_validate(case.expected | wrapper)


def test_registered_with_its_kind_and_inputs() -> None:
    definition = REGISTRY[CALC_ID]
    assert (definition.version, definition.output_kind, definition.verification) == (1, f"{CALC_ID}/1", "draft")
    assert definition.input_type is CheckInput
    properties = CheckInput.model_json_schema()["properties"]
    assert {name: prop["x-eng"]["ref_kinds"] for name, prop in properties.items()} == {
        name: [kind] for name, kind in CHECK_KINDS.items()
    }
    assert not any(prop["x-eng"]["stale_ok"] for prop in properties.values())


def test_basis_fields_are_the_bounds_of_spec_4_8() -> None:
    assert BASIS_FIELDS == (
        "bounds.thickness_min_mm",
        "bounds.thickness_max_mm",
        "bounds.line_load_min_kN_m",
        "bounds.line_load_max_kN_m",
        "bounds.area_load_min_kPa",
        "bounds.area_load_max_kPa",
        "bounds.ratio_min_ratio",
        "bounds.ratio_max_ratio",
    )
    assert [kind for kind, _, _ in BOUNDS] == ["length", "line_load", "area_load", "dimensionless"]


def test_trace_records_bounds_count_and_status() -> None:
    case = _case("check-duplicate-target")
    trace = TraceBuilder()
    run_check(case, trace=trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    inputs = {i.name: i for i in built.inputs}
    assert list(inputs) == [path.replace(".", "_") for path in BASIS_FIELDS] + ["items"]
    low = inputs["bounds_thickness_min_mm"]
    assert (low.value, low.unit, low.ref) == (100.0, "mm", f"{case.refs['basis']}#/fields/bounds.thickness_min_mm")
    assert inputs["bounds_line_load_max_kN_m"].value == 100.0
    assert inputs["items"].value == 5
    assert inputs["items"].ref == f"{case.refs['change_set']}#/fields/change_set/value"
    steps = {s.name: s for s in built.steps}
    assert [(name, steps[name].value) for name in ("errors", "warnings", "status")] == [
        ("errors", 2),
        ("warnings", 0),
        ("status", "FAIL"),
    ]
    assert steps["status"].source == "spec 0007 4.4.1 K7"
    assert steps["status"].uses == ["errors"]
    assert steps["errors"].uses == ["items", *(path.replace(".", "_") for path in BASIS_FIELDS)]
    assert built.outputs == ["status"]


@pytest.mark.parametrize("item_id", ["a/b", "/a", "a/", "/", "a//b"])
def test_item_id_with_a_slash_is_refused(item_id: str) -> None:
    """K3 and AC4: an item id that contains `/` is the error INVALID_ITEM_ID, wherever the slash is."""
    case = _case()
    item = {"id": item_id, "kind": "frame_section", "frames": ["B1"], "section": "C400"}
    body = run_check(case, items=[item])
    assert body["issues"] == [
        {
            "item_id": item_id,
            "severity": "error",
            "code": "INVALID_ITEM_ID",
            "detail": f"item id {item_id} contains / (spec 0007 4.4.1 K3)",
            "gap": None,
        }
    ]
    assert body["status"] == "FAIL"
    assert [resolved["item_id"] for resolved in body["resolved"]] == [item_id]


def test_item_id_without_a_slash_is_not_refused() -> None:
    item = {"id": "a-b.c_1\\d", "kind": "frame_section", "frames": ["B1"], "section": "C400"}
    assert run_check(_case(), items=[item])["issues"] == []


def test_item_id_rule_changes_no_other_rule() -> None:
    """The slash issue comes first for its item; the issues of the other rules follow as without it."""
    case = _case()
    items = [
        {"id": "a/1", "kind": "frame_section", "frames": ["B1"], "section": "NOPE"},
        {"id": "a/2", "kind": "frame_section", "frames": ["B1"], "section": "C400"},
    ]
    assert _issues(run_check(case, items=items)) == [
        ("a/1", "INVALID_ITEM_ID"),
        ("a/1", "UNKNOWN_SECTION"),
        ("a/2", "INVALID_ITEM_ID"),
        ("a/2", "DUPLICATE_TARGET"),
    ]
    ok = [item | {"id": item["id"].replace("/", "-")} for item in items]
    assert _issues(run_check(case, items=ok)) == [("a-1", "UNKNOWN_SECTION"), ("a-2", "DUPLICATE_TARGET")]


def test_warnings_counted_in_the_trace() -> None:
    trace = TraceBuilder()
    run_check(_case("check-conflict-engineer"), trace=trace)
    steps = {s.name: s.value for s in trace.build(REGISTRY[CALC_ID], DIGEST).steps}
    assert steps == {"errors": 0, "warnings": 2, "status": "PASS"}


@pytest.mark.parametrize("path", BASIS_FIELDS)
@pytest.mark.parametrize(("change", "why"), [(None, "is missing"), ({"confirmed": False}, "not confirmed")])
def test_bounds_field_missing_or_unconfirmed_is_refused(path: str, change: dict[str, Any] | None, why: str) -> None:
    case = _case()
    fields = dict(case.input["basis"]["fields"])
    if change is None:
        del fields[path]
    else:
        fields[path] = fields[path] | change
    with pytest.raises(ContractError) as caught:
        run_check(case, basis={"template": None, "fields": fields})
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == f"basis.fields.{path}"
    assert why in caught.value.detail.message


def test_bounds_field_not_a_number_is_refused() -> None:
    case = _case()
    fields = dict(case.input["basis"]["fields"])
    fields["bounds.ratio_max_ratio"] = fields["bounds.ratio_max_ratio"] | {"value": "ten"}
    with pytest.raises(ContractError) as caught:
        run_check(case, basis={"template": None, "fields": fields})
    assert caught.value.detail.field == "basis.fields.bounds.ratio_max_ratio"
    assert caught.value.detail.message == "basis field bounds.ratio_max_ratio is not a number"


@pytest.mark.parametrize("name", list(CHECK_KINDS))
def test_each_input_must_be_a_record(name: str) -> None:
    case = _case()
    meta = input_meta({k: v for k, v in case.refs.items() if k != name})
    with pytest.raises(ContractError) as caught:
        run_check(case, meta=meta)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == name


@pytest.mark.parametrize("name", list(CHECK_KINDS))
def test_incomplete_record_makes_the_check_incomplete(name: str) -> None:
    case = _case()
    body = run_check(case, meta=input_meta(case.refs, frozenset({name})))
    assert (body["complete"], body["status"]) == (False, "PASS")


def test_incomplete_difference_report_makes_the_check_incomplete() -> None:
    case = _case()
    body = run_check(case, diff=case.input["diff"] | {"complete": False, "identical": False})
    assert body["complete"] is False


def test_basis_value_that_is_not_a_number_is_source_missing() -> None:
    case = _case()
    fields = dict(case.input["basis"]["fields"])
    fields["loads.label_kN_m"] = fields["loads.partition_kN_m"] | {"value": "high", "confirmed": True}
    item = BEAM_LOAD | {"w": {"source": "basis", "path": "loads.label_kN_m"}}
    body = run_check(case, items=[item], basis={"template": None, "fields": fields})
    assert _issues(body) == [("a1", "SOURCE_MISSING")]


def test_basis_value_without_a_unit_suffix_is_a_unit_mismatch() -> None:
    case = _case()
    fields = dict(case.input["basis"]["fields"])
    fields["report.top_n"] = fields["loads.sdl_kPa"] | {"value": 3, "unit": None}
    body = run_check(
        case,
        items=[BEAM_LOAD | {"w": {"source": "basis", "path": "report.top_n"}}],
        basis={
            "template": None,
            "fields": fields,
        },
    )
    assert body["issues"][0]["detail"] == "the unit of basis field report.top_n is not of kind line_load"
    assert _issues(body) == [("a1", "UNIT_MISMATCH")]


def test_basis_value_out_of_bounds() -> None:
    case = _case()
    fields = dict(case.input["basis"]["fields"])
    fields["loads.heavy_kN_m"] = fields["loads.partition_kN_m"] | {"value": 100.5, "confirmed": True}
    body = run_check(
        case,
        items=[BEAM_LOAD | {"w": {"source": "basis", "path": "loads.heavy_kN_m"}}],
        basis={
            "template": None,
            "fields": fields,
        },
    )
    assert body["issues"][0]["detail"] == "w 100.5 kN/m is outside [0.0, 100.0] kN/m (spec 0007 4.8)"


def test_reversed_bounds_refuse_every_value() -> None:
    case = _case()
    fields = dict(case.input["basis"]["fields"])
    fields["bounds.line_load_min_kN_m"] = fields["bounds.line_load_min_kN_m"] | {"value": 10.0}
    fields["bounds.line_load_max_kN_m"] = fields["bounds.line_load_max_kN_m"] | {"value": 5.0}
    item = BEAM_LOAD | {"w": {"source": "input", "value": 7.0, "unit": "kN/m"}}
    body = run_check(case, items=[item], basis={"template": None, "fields": fields})
    assert _issues(body) == [("a1", "OUT_OF_BOUNDS")]


def test_combination_cases_are_checked_by_their_type() -> None:
    terms = [
        {
            "case": {"case": "NOPE", "case_type": "load_combination"},
            "scale": {"source": "input", "value": 1.0, "unit": "1"},
        },
        {"case": {"case": "ANY", "case_type": "load_case"}, "scale": {"source": "input", "value": 1.0, "unit": "1"}},
        {
            "case": {"case": "COMB1", "case_type": "load_combination"},
            "scale": {"source": "input", "value": 1.0, "unit": "1"},
        },
    ]
    items: list[dict[str, Any]] = [
        {"id": "c1", "kind": "load_combination_set", "name": "C2", "type": "srss", "items": terms},
        {"id": "c2", "kind": "load_combination_delete", "name": "C2"},
    ]
    body = run_check(_case(), items=items)
    assert _issues(body) == [("c1", "UNKNOWN_COMBINATION"), ("c2", "DUPLICATE_TARGET")]
    assert body["issues"][0]["detail"] == "combination NOPE is not in the model"


def test_conflict_on_another_property_or_key_is_no_warning() -> None:
    case = _case("check-conflict-engineer")
    diff = case.input["diff"]
    rows = diff["changes"][0]["properties"]
    other = diff | {"changes": [diff["changes"][0] | {"properties": [rows[0] | {"pointer": "/rotation_deg"}]}]}
    other["counts"] = {"model.frame_placements/1": diff["counts"]["model.frame_placements/1"]}
    item = {"id": "a1", "kind": "frame_section", "frames": ["B1"], "section": "C400"}
    assert run_check(case, items=[item], diff=other)["issues"] == []
    item_b2 = item | {"frames": ["B2"]}
    assert run_check(case, items=[item_b2])["issues"] == []


def test_restraint_conflict_covers_every_component() -> None:
    case = _case("check-conflict-engineer")
    row = {"pointer": "/ux", "before": True, "after": False, "unit": None, "quantity_kind": None, "tolerance": None}
    change = {"section": "model.joint_restraints/1", "key": ["joints", "J0"], "change": "changed", "before": None}
    count = dict.fromkeys(("added", "removed", "ambiguous", "unchanged", "within_tolerance"), 0) | {"changed": 1}
    diff = case.input["diff"] | {
        "changes": [change | {"after": None, "properties": [row | {"rule": "D4"}]}],
        "counts": {"model.joint_restraints/1": count},
    }
    flags = dict.fromkeys(("ux", "uy", "uz", "rx", "ry", "rz"), True)
    body = run_check(case, items=[{"id": "r1", "kind": "joint_restraints", "joints": ["J0"]} | flags], diff=diff)
    assert [i["detail"] for i in body["issues"]] == [
        "the engineer changed joints/J0/ux from True to False; item sets restraints"
    ]
    assert body["status"] == "PASS"


def test_pattern_add_conflicts_with_an_engineer_pattern() -> None:
    case = _case("check-conflict-engineer")
    count = dict.fromkeys(("removed", "changed", "ambiguous", "unchanged", "within_tolerance"), 0) | {"added": 1}
    pattern = {"name": "P9", "type": "other", "self_weight_ratio": 0.0}
    change = {"section": "model.load_set/1", "key": ["patterns", "P9"], "change": "added", "before": None}
    diff = case.input["diff"] | {
        "changes": [change | {"after": pattern, "properties": []}],
        "counts": {"model.load_set/1": count},
    }
    item = {"id": "p1", "kind": "load_pattern_add", "name": "P9", "type": "other"}
    body = run_check(case, items=[item | {"self_weight": {"source": "input", "value": 1.0, "unit": "1"}}], diff=diff)
    assert [i["detail"] for i in body["issues"]] == [
        "the engineer added patterns/P9; item sets a new pattern, self weight 1.0 1"
    ]


@pytest.mark.parametrize(
    ("item", "shown"),
    [
        ({"id": "c1", "kind": "load_combination_set", "name": "COMB1", "type": "linear_add"}, "a new definition"),
        ({"id": "c1", "kind": "load_combination_delete", "name": "COMB1"}, "its deletion"),
    ],
)
def test_combination_claim_conflicts_with_an_engineer_change_to_one_of_its_items(
    item: dict[str, Any], shown: str
) -> None:
    case = _case("check-conflict-engineer")
    row = {"pointer": "/scale_ratio", "before": 1.0, "after": 1.2, "unit": "1", "quantity_kind": "dimensionless"}
    key = ["combinations", "COMB1", "items", "DEAD", "load_pattern"]
    change = {"section": "model.load_set/1", "key": key, "change": "changed", "before": None, "after": None}
    count = dict.fromkeys(("added", "removed", "ambiguous", "unchanged", "within_tolerance"), 0) | {"changed": 1}
    diff = case.input["diff"] | {
        "changes": [change | {"properties": [row | {"tolerance": None, "rule": "D3"}]}],
        "counts": {"model.load_set/1": count},
    }
    term = {
        "case": {"case": "DEAD", "case_type": "load_pattern"},
        "scale": {"source": "input", "value": 1.0, "unit": "1"},
    }
    claim = item | ({"items": [term]} if item["kind"] == "load_combination_set" else {})
    body = run_check(case, items=[claim], diff=diff)
    assert [i["detail"] for i in body["issues"]] == [
        "the engineer changed combinations/COMB1/items/DEAD/load_pattern/scale_ratio from 1.0 to 1.2; "
        f"item sets {shown}"
    ]
    assert body["status"] == "PASS"
    other = claim | {"name": "COMB"}
    names = case.input["names"] | {"combinations": ["COMB", "COMB1"]}
    assert run_check(case, items=[other], diff=diff, names=names)["issues"] == []
