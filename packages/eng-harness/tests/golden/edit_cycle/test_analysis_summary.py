"""Golden cases and contract of harness.analysis_summary (plan 0007 T4; spec 0007 AC30, section 4.4.4, gap EC-G3)."""

import copy
import importlib
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.calc import InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.edit_cycle.analysis_summary import BASIS_FIELDS, SummaryInput, analysis_summary
from eng_harness.kinds.edit_cycle import AnalysisSummary

from . import EditCycleGoldenCase, load_cases

KINDS = {
    "messages": "harness.csi_analysis_messages/1",
    "drifts": "forces.story_drifts/1",
    "basis": "basis.design_basis/1",
}
"""The record kind of each reference input of `harness.analysis_summary`."""
module = importlib.import_module("eng_harness.calcs.edit_cycle.analysis_summary")
"""The module itself: the package namespace holds the calc under the same name."""
CALC_ID = "harness.analysis_summary"
DIGEST = "ab" * 32
STEMS = [
    "analysis-clean",
    "analysis-drift-exceeding",
    "analysis-messages-unclassified",
    "analysis-no-drifts",
]


def meta_for(refs: dict[str, str]) -> InputMeta:
    """`InputMeta` of the summary calc: three complete records."""
    return InputMeta(
        refs={
            name: RefMeta(
                result_id=result_id,
                ref=result_id,
                kind=KINDS[name],
                complete=True,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="csi" if name != "basis" else "harness",
            )
            for name, result_id in refs.items()
        }
    )


def run_summary(
    case: EditCycleGoldenCase, *, trace: TraceBuilder | None = None, meta: InputMeta | None = None, **changes: Any
) -> dict[str, Any]:
    """Run `harness.analysis_summary` on the case input with some input fields replaced."""
    inp = SummaryInput.model_validate(copy.deepcopy(case.input) | changes)
    return analysis_summary(inp, meta or meta_for(case.refs), trace or TraceBuilder()).model_dump(mode="json")


def test_golden_cases() -> None:
    cases = load_cases("analysis")
    assert sorted(cases) == STEMS
    actual = {stem: run_summary(case) for stem, case in cases.items()}
    assert {stem: body for stem, body in actual.items() if body != cases[stem].expected} == {}


def _case(stem: str = "analysis-drift-exceeding") -> EditCycleGoldenCase:
    return load_cases("analysis")[stem]


def _refused(case: EditCycleGoldenCase, field: str, message: str, **kwargs: Any) -> None:
    meta = kwargs.pop("meta", None)
    with pytest.raises(ContractError) as caught:
        run_summary(case, meta=meta, **kwargs)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert (caught.value.detail.field, caught.value.detail.message) == (field, message)


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
    for stem, case in load_cases("analysis").items():
        payload = AnalysisSummary.model_validate(case.expected | wrapper)
        assert payload.status == case.expected["status"], stem


def test_registered_with_its_kind_and_inputs() -> None:
    definition = REGISTRY[CALC_ID]
    assert (definition.version, definition.output_kind, definition.verification) == (1, f"{CALC_ID}/1", "draft")
    assert definition.input_type is SummaryInput
    properties = SummaryInput.model_json_schema()["properties"]
    assert {name: properties[name]["x-eng"]["ref_kinds"] for name in KINDS} == {n: [k] for n, k in KINDS.items()}
    assert not any(properties[name]["x-eng"]["stale_ok"] for name in KINDS)
    assert set(properties) == set(KINDS)
    assert BASIS_FIELDS == ("limits.drift_ratio",)


def test_trace_records_limit_counts_and_status() -> None:
    case = _case()
    trace = TraceBuilder()
    run_summary(case, trace=trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    inputs = {i.name: i for i in built.inputs}
    assert list(inputs) == ["limits_drift_ratio", "messages", "drifts"]
    limit = inputs["limits_drift_ratio"]
    assert (limit.value, limit.unit) == (0.01, "1")
    assert limit.ref == f"{case.refs['basis']}#/fields/limits.drift_ratio"
    assert (inputs["messages"].value, inputs["messages"].ref) == (0, f"{case.refs['messages']}#/rows")
    assert (inputs["drifts"].value, inputs["drifts"].ref) == (7, f"{case.refs['drifts']}#/rows")
    steps = {s.name: s for s in built.steps}
    assert list(steps) == [
        "error_messages",
        "warning_messages",
        "info_messages",
        "unclassified_messages",
        "governing_directions",
        "exceeding_rows",
        "status",
    ]
    assert (steps["governing_directions"].value, steps["exceeding_rows"].value) == (2, 3)
    assert (steps["status"].value, steps["status"].source) == ("NEEDS_ENGINEER", "spec 0007 4.4.4")
    assert steps["status"].uses == ["error_messages", "unclassified_messages", "exceeding_rows"]
    assert steps["exceeding_rows"].uses == ["drifts", "limits_drift_ratio"]
    assert built.outputs == ["status"]


def test_every_message_is_unclassified_whatever_its_columns() -> None:
    """Gap EC-G3: no column is read, a row that names an error is still unclassified."""
    case = _case("analysis-messages-unclassified")
    body = run_summary(case)
    assert body["counts"] == {"error": 0, "warning": 0, "info": 0, "unclassified": 4}
    assert (body["has_errors"], body["has_unclassified"], body["status"]) == (False, True, "NEEDS_ENGINEER")


def test_a_ratio_at_the_limit_does_not_exceed_and_one_just_above_does() -> None:
    case = _case("analysis-clean")
    rows = case.input["drifts"]["rows"]
    at = run_summary(case)
    assert (at["exceeding"], at["status"]) == ([], "PASS")
    above = [rows[0], rows[1] | {"drift_ratio": 0.010000000000000002}]
    body = run_summary(case, drifts={"rows": above})
    assert [(r["story"], r["ratio"]) for r in body["exceeding"]] == [("S2", 0.010000000000000002)]
    assert body["status"] == "NEEDS_ENGINEER"


def test_the_limit_is_compared_exactly_as_stored() -> None:
    case = _case("analysis-clean")
    basis = copy.deepcopy(case.input["basis"])
    basis["fields"]["limits.drift_ratio"]["value"] = 0.0039
    body = run_summary(case, basis=basis)
    assert body["limit_ratio"] == 0.0039
    assert [r["story"] for r in body["exceeding"]] == ["S1", "S2"]


def test_highest_ratio_per_row_does_not_depend_on_the_input_order() -> None:
    case = _case()
    rows = list(reversed(case.input["drifts"]["rows"]))
    assert run_summary(case, drifts={"rows": rows}) == case.expected


def test_an_error_message_fails_and_counts_by_severity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once the severity is confirmed, an error message is a FAIL, whatever else holds."""
    severities = iter(["error", "warning", "info", "unclassified"])
    monkeypatch.setattr(module, "_severity", lambda row: next(severities))
    body = run_summary(_case("analysis-messages-unclassified"))
    assert body["counts"] == {"error": 1, "warning": 1, "info": 1, "unclassified": 1}
    assert (body["has_errors"], body["has_unclassified"], body["status"]) == (True, True, "FAIL")


def test_warnings_and_info_alone_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    severities = iter(["warning", "info", "info", "warning"])
    monkeypatch.setattr(module, "_severity", lambda row: next(severities))
    body = run_summary(_case("analysis-messages-unclassified"))
    assert body["counts"] == {"error": 0, "warning": 2, "info": 2, "unclassified": 0}
    assert (body["has_errors"], body["has_unclassified"], body["status"]) == (False, False, "PASS")


@pytest.mark.parametrize("name", ["messages", "drifts", "basis"])
def test_an_input_without_a_record_is_refused(name: str) -> None:
    case = _case()
    refs = {key: value for key, value in case.refs.items() if key != name}
    _refused(case, name, "each input must be a record reference", meta=meta_for(refs))


def test_the_limit_must_be_present_confirmed_and_a_number() -> None:
    case = _case()
    path = "limits.drift_ratio"
    field = case.input["basis"]["fields"][path]
    for fields, message in (
        ({}, f"basis field {path} is missing or not confirmed"),
        ({path: field | {"confirmed": False}}, f"basis field {path} is missing or not confirmed"),
        ({path: field | {"value": "0.01"}}, f"basis field {path} is not a number"),
        ({path: field | {"value": True}}, f"basis field {path} is not a number"),
    ):
        _refused(case, f"basis.fields.{path}", message, basis={"template": None, "fields": fields})
