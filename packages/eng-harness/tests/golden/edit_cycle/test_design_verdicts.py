"""Golden cases and contract of harness.host_design_verdicts (plan 0007 T4b; spec 0007 AC30, 4.4.3, gap EC-G2)."""

import copy
import math
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from pydantic import ValidationError

from eng_harness.calc import InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.edit_cycle.host_design_verdicts import BASIS_FIELDS, VerdictsInput, host_design_verdicts
from eng_harness.kinds.edit_cycle import HostDesignVerdicts

from . import EditCycleGoldenCase, load_cases

KINDS = {"results": "harness.csi_design_results/1", "basis": "basis.design_basis/1"}
"""The record kind of each reference input of `harness.host_design_verdicts`."""
CALC_ID = "harness.host_design_verdicts"
DIGEST = "ab" * 32
STEMS = ["verdicts-concrete", "verdicts-empty", "verdicts-steel"]
LIMIT = "limits.ratio_limit_ratio"
NOT_MAPPED = "host concrete design output not mapped"
FRAME = "frame is not a valid subject id"
COMBO = "combo is not a valid case name"
RATIO = "ratio is not a finite number of at least zero"


def meta_for(refs: dict[str, str], incomplete: frozenset[str] = frozenset()) -> InputMeta:
    """`InputMeta` of the calc: a complete record per reference."""
    return InputMeta(
        refs={
            name: RefMeta(
                result_id=result_id,
                kind=KINDS[name],
                complete=name not in incomplete,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="csi" if name == "results" else "harness",
            )
            for name, result_id in refs.items()
        }
    )


def run_verdicts(
    case: EditCycleGoldenCase, *, trace: TraceBuilder | None = None, meta: InputMeta | None = None, **changes: Any
) -> dict[str, Any]:
    """Run `harness.host_design_verdicts` on the case input with some input fields replaced."""
    inp = VerdictsInput.model_validate(copy.deepcopy(case.input) | changes)
    return host_design_verdicts(inp, meta or meta_for(case.refs), trace or TraceBuilder()).model_dump(mode="json")


def _case(stem: str = "verdicts-steel") -> EditCycleGoldenCase:
    return load_cases("verdicts")[stem]


def _basis(case: EditCycleGoldenCase, **changes: Any) -> dict[str, Any]:
    """The case basis with the limit field changed."""
    basis: dict[str, Any] = copy.deepcopy(case.input["basis"])
    basis["fields"][LIMIT] |= changes
    return basis


def _refused(case: EditCycleGoldenCase, field: str, message: str, **kwargs: Any) -> None:
    with pytest.raises(ContractError) as caught:
        run_verdicts(case, **kwargs)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert (caught.value.detail.field, caught.value.detail.message) == (field, message)


def test_golden_cases() -> None:
    cases = load_cases("verdicts")
    assert sorted(cases) == STEMS
    actual = {stem: run_verdicts(case) for stem, case in cases.items()}
    assert {stem: body for stem, body in actual.items() if body != cases[stem].expected} == {}


def test_golden_bodies_are_valid_payloads() -> None:
    """The kind takes each golden body with the calc port's wrapper (calc, draft, trace)."""
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
    for stem, case in load_cases("verdicts").items():
        payload = HostDesignVerdicts.model_validate(case.expected | wrapper)
        assert len(payload.verdicts) == len(case.input["results"]["rows"]), stem


def test_registered_with_its_kind_and_inputs() -> None:
    definition = REGISTRY[CALC_ID]
    assert (definition.version, definition.output_kind, definition.verification) == (1, f"{CALC_ID}/1", "draft")
    assert definition.input_type is VerdictsInput
    properties = VerdictsInput.model_json_schema()["properties"]
    assert {name: properties[name]["x-eng"]["ref_kinds"] for name in KINDS} == {n: [k] for n, k in KINDS.items()}
    assert not any(properties[name]["x-eng"]["stale_ok"] for name in KINDS)
    assert set(properties) == {*KINDS, "kind"}
    assert BASIS_FIELDS == (LIMIT,)


def test_trace_records_the_limit_the_rows_and_the_counts() -> None:
    case = _case()
    trace = TraceBuilder()
    run_verdicts(case, trace=trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    inputs = {i.name: i for i in built.inputs}
    assert list(inputs) == ["limits_ratio_limit_ratio", "rows"]
    limit = inputs["limits_ratio_limit_ratio"]
    assert (limit.value, limit.unit) == (0.95, "1")
    assert limit.ref == f"{case.refs['basis']}#/fields/{LIMIT}"
    assert (inputs["rows"].value, inputs["rows"].ref) == (4, f"{case.refs['results']}#/rows")
    steps = {s.name: s for s in built.steps}
    assert list(steps) == ["verdict_count", "fail_verdicts", "needs_engineer_verdicts"]
    assert [steps[name].value for name in steps] == [4, 2, 0]
    assert steps["verdict_count"].uses == ["rows"]
    assert steps["fail_verdicts"].uses == ["rows", "limits_ratio_limit_ratio"]
    assert steps["needs_engineer_verdicts"].uses == ["rows"]
    assert {s.source for s in built.steps} == {"spec 0007 4.4.3"}
    assert built.outputs == ["verdict_count"]


def test_a_ratio_at_the_limit_passes_and_one_just_above_fails() -> None:
    case = _case()
    rows = [
        {"frame": "A", "ratio": 0.95, "combo": "C"},
        {"frame": "B", "ratio": math.nextafter(0.95, 1.0), "combo": "C"},
        {"frame": "C", "ratio": math.nextafter(0.95, 0.0), "combo": "C"},
    ]
    body = run_verdicts(case, results={"rows": rows})
    assert [(v["subject"]["id"], v["status"]) for v in body["verdicts"]] == [
        ("A", "PASS"),
        ("B", "FAIL"),
        ("C", "PASS"),
    ]


def test_the_limit_is_the_basis_value_as_stored() -> None:
    case = _case()
    body = run_verdicts(case, basis=_basis(case, value=0.4))
    assert {v["ratio_limit"] for v in body["verdicts"]} == {0.4}
    assert [v["status"] for v in body["verdicts"]] == ["FAIL", "FAIL", "PASS", "FAIL"]
    body = run_verdicts(case, basis=_basis(case, value=2))
    assert {v["ratio_limit"] for v in body["verdicts"]} == {2.0}
    assert body["counts"]["PASS"] == 4


def test_a_row_without_a_combo_has_no_case_and_other_columns_are_ignored() -> None:
    case = _case()
    rows = [{"frame": "A", "ratio": 0.5, "ratio_type": "PMM", "location": 1500.0, "extra": [1, {"x": None}]}]
    verdict = run_verdicts(case, results={"rows": rows})["verdicts"][0]
    assert verdict["subject"] == {"kind": "frame", "id": "A", "station_mm": None, "case": None}
    assert verdict["status"] == "PASS"
    assert run_verdicts(case, results={"rows": [rows[0] | {"combo": None}]})["verdicts"] == [verdict]


def test_a_zero_ratio_passes() -> None:
    body = run_verdicts(_case(), results={"rows": [{"frame": "A", "ratio": 0, "combo": "C"}]})
    assert (body["verdicts"][0]["ratio"], body["verdicts"][0]["status"]) == (0.0, "PASS")


def test_the_kind_must_be_steel_or_concrete() -> None:
    case = _case()
    for bad in ("aluminum", "Steel", ""):
        with pytest.raises(ValidationError):
            VerdictsInput.model_validate(copy.deepcopy(case.input) | {"kind": bad})


def test_concrete_gives_needs_engineer_whatever_the_columns() -> None:
    """Gap EC-G2: a concrete row with a column named ratio is still not mapped to a ratio."""
    case = _case("verdicts-concrete")
    rows = [{"frame": "B9", "ratio": 5.0, "combo": "COMB9"}]
    trace = TraceBuilder()
    body = run_verdicts(case, results={"rows": rows}, trace=trace)
    [verdict] = body["verdicts"]
    assert (verdict["status"], verdict["ratio"], verdict["assumptions"]) == ("NEEDS_ENGINEER", None, [NOT_MAPPED])
    assert verdict["subject"]["case"] == "COMB9"
    assert body["counts"]["NEEDS_ENGINEER"] == 1
    steps = {s.name: s.value for s in trace.build(REGISTRY[CALC_ID], DIGEST).steps}
    assert steps == {"verdict_count": 1, "fail_verdicts": 0, "needs_engineer_verdicts": 1}


def test_a_frame_name_and_a_combo_are_taken_as_the_host_wrote_them() -> None:
    case = _case()
    rows = [{"frame": " F 1 ", "ratio": 0.1, "combo": "1.2D + 1.6L"}]
    subject = run_verdicts(case, results={"rows": rows})["verdicts"][0]["subject"]
    assert (subject["id"], subject["case"]) == (" F 1 ", "1.2D + 1.6L")


@pytest.mark.parametrize("name", ["results", "basis"])
def test_an_input_without_a_record_is_refused(name: str) -> None:
    case = _case()
    refs = {key: value for key, value in case.refs.items() if key != name}
    _refused(case, name, "each input must be a record reference", meta=meta_for(refs))


def test_the_limit_must_be_present_confirmed_a_number_and_above_zero() -> None:
    case = _case()
    field = f"basis.fields.{LIMIT}"
    missing = f"basis field {LIMIT} is missing or not confirmed"
    _refused(case, field, missing, basis={"template": None, "fields": {}})
    _refused(case, field, missing, basis=_basis(case, confirmed=False))
    _refused(case, field, f"basis field {LIMIT} is not a number", basis=_basis(case, value="1.0"))
    _refused(case, field, f"basis field {LIMIT} is not a number", basis=_basis(case, value=True))
    for value in (0, -1.0):
        _refused(case, field, f"basis field {LIMIT} must be above zero", basis=_basis(case, value=value))


@pytest.mark.parametrize(
    ("row", "field", "message"),
    [
        ({"ratio": 0.5}, "results.rows[1].frame", FRAME),
        ({"frame": "", "ratio": 0.5}, "results.rows[1].frame", FRAME),
        ({"frame": 7, "ratio": 0.5}, "results.rows[1].frame", FRAME),
        ({"frame": "x" * 201, "ratio": 0.5}, "results.rows[1].frame", FRAME),
        ({"frame": "A", "ratio": 0.5, "combo": 3}, "results.rows[1].combo", COMBO),
        ({"frame": "A", "ratio": 0.5, "combo": "x" * 201}, "results.rows[1].combo", COMBO),
        ({"frame": "A"}, "results.rows[1].ratio", RATIO),
        ({"frame": "A", "ratio": None}, "results.rows[1].ratio", RATIO),
        ({"frame": "A", "ratio": "0.5"}, "results.rows[1].ratio", RATIO),
        ({"frame": "A", "ratio": True}, "results.rows[1].ratio", RATIO),
        ({"frame": "A", "ratio": -0.1}, "results.rows[1].ratio", RATIO),
    ],
)  # fmt: skip
def test_a_steel_row_the_mapping_cannot_use_is_refused_with_its_field(
    row: dict[str, Any], field: str, message: str
) -> None:
    case = _case()
    rows = [case.input["results"]["rows"][0], row]
    _refused(case, field, f"design result row 1: {message}", results={"rows": rows})


def test_a_concrete_row_needs_a_frame_but_no_ratio() -> None:
    case = _case("verdicts-concrete")
    rows = [case.input["results"]["rows"][0], {"location": 0.0}]
    _refused(case, "results.rows[1].frame", f"design result row 1: {FRAME}", results={"rows": rows})
    assert len(run_verdicts(case, results={"rows": [{"frame": "A"}]})["verdicts"]) == 1


def test_the_verdicts_keep_the_row_order() -> None:
    case = _case()
    rows = case.input["results"]["rows"]
    forward = run_verdicts(case)
    backward = run_verdicts(case, results={"rows": list(reversed(rows))})
    assert [v["subject"]["id"] for v in forward["verdicts"]] == [r["frame"] for r in rows]
    assert backward["verdicts"] == list(reversed(forward["verdicts"]))
    assert backward["counts"] == forward["counts"]
