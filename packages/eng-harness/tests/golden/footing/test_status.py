"""Golden cases and contract of harness.footing_status (plan 0010 T6; spec 0010 AC10, section 4.4.5)."""

import copy
from pathlib import Path
from typing import Any

import pytest
from eng_contract.envelope import FailureEnvelope, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from pydantic import JsonValue

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.footing.status import BASIS_FIELDS, FAMILIES, StatusInput, footing_status
from eng_harness.kinds.footing import FootingStatus
from eng_harness.ports import RunClass

from . import FootingGoldenCase, input_meta, load_cases

CALC_ID = "harness.footing_status"
KINDS = {
    "subjects": "harness.footing_subjects/1",
    "design": "harness.footing_design/1",
    "bearing": "verdicts.set/1",
    "one_way_shear": "verdicts.set/1",
    "punching": "verdicts.set/1",
    "flexure": "verdicts.set/1",
    "min_steel": "verdicts.set/1",
    "development": "verdicts.set/1",
}
STEMS = ["status-family-order", "status-mixed-fail-and-needs-engineer", "status-ratio-governing"]
DIGEST = "ab" * 32


def _run_with(case: FootingGoldenCase, trace: TraceBuilder | None, changes: dict[str, Any]) -> dict[str, Any]:
    raw = copy.deepcopy(case.input) | changes
    result = footing_status(StatusInput.model_validate(raw), input_meta(case.refs, KINDS), trace or TraceBuilder())
    return result.model_dump(mode="json")


def _run(case: FootingGoldenCase, trace: TraceBuilder | None = None, **changes: Any) -> dict[str, Any]:
    return _run_with(case, trace, changes)


def _verdict_set(case: FootingGoldenCase, family: str, drop: str | None = None, **change: Any) -> dict[str, Any]:
    """The verdict set of `family` without the verdicts about footing `drop`, with `change` on each remaining one."""
    payload: dict[str, Any] = copy.deepcopy(case.input[family])
    kept = [v for v in payload["verdicts"] if v["subject"]["id"] != drop]
    payload["verdicts"] = [v | change for v in kept]
    payload["traces"] = payload["traces"][: len(kept)]
    for index, verdict in enumerate(payload["verdicts"]):
        verdict["trace_ref"] = f"#/traces/{index}"
    payload["counts"] = {s: sum(v["status"] == s for v in payload["verdicts"]) for s in payload["counts"]}
    return payload


def test_golden_cases() -> None:
    cases = load_cases("status")
    assert sorted(cases) == STEMS
    actual = {stem: _run(case) for stem, case in cases.items()}
    assert {stem: body for stem, body in actual.items() if body != cases[stem].expected} == {}


def test_the_calc_reads_no_basis_field_and_names_the_six_families() -> None:
    assert BASIS_FIELDS == ()
    assert FAMILIES == ("bearing", "one_way_shear", "punching", "flexure", "min_steel", "development")
    assert list(StatusInput.model_fields) == ["subjects", "design", *FAMILIES]


def test_trace_records_inputs_counts_and_closures() -> None:
    case = load_cases("status")["status-family-order"]
    trace = TraceBuilder()
    _run(case, trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    inputs = {i.name: i for i in built.inputs}
    assert {n: i.value for n, i in inputs.items()} == {
        "subjects": 6,
        "design_footings": 6,
        "bearing_verdicts": 6,
        "one_way_shear_verdicts": 12,
        "punching_verdicts": 6,
        "flexure_verdicts": 6,
        "min_steel_verdicts": 6,
        "development_verdicts": 6,
    }
    assert inputs["subjects"].ref == case.refs["subjects"]
    assert inputs["design_footings"].ref == case.refs["design"]
    assert inputs["one_way_shear_verdicts"].ref == case.refs["one_way_shear"]
    assert built.constants == []
    steps = {s.name: s for s in built.steps}
    assert [(n, steps[n].value) for n in ("footings", "passed", "failing", "needs_engineer")] == [
        ("footings", 6),
        ("passed", 1),
        ("failing", 2),
        ("needs_engineer", 3),
    ]
    assert list(steps["footings"].uses) == [
        "design_footings",
        "bearing_verdicts",
        "one_way_shear_verdicts",
        "punching_verdicts",
        "flexure_verdicts",
        "min_steel_verdicts",
        "development_verdicts",
    ]
    assert all(list(steps[n].uses) == ["footings"] for n in ("passed", "failing", "needs_engineer"))
    assert all(s.source.startswith("spec 0010 4.4.5") for s in built.steps)
    assert built.outputs == ["footings", "passed", "failing", "needs_engineer"]


def test_rows_are_sorted_by_footing_id() -> None:
    case = load_cases("status")["status-mixed-fail-and-needs-engineer"]
    assert [row["id"] for row in _run(case)["footings"]] == ["J1", "J2", "J3"]


def test_the_ratio_shown_is_the_largest_of_the_governing_verdicts() -> None:
    case = load_cases("status")["status-ratio-governing"]
    bearing = copy.deepcopy(case.input["bearing"])
    first = next(v for v in bearing["verdicts"] if v["subject"]["id"] == "J1" and v["ratio"] == 0.3)
    first["governing"] = True  # two governing verdicts of J1: 0.3 and 0.8
    body = _run(case, bearing=bearing)
    assert body["footings"][0]["families"]["bearing"] == {"status": "PASS", "ratio": 0.8}


def test_a_family_without_a_governing_verdict_shows_no_ratio() -> None:
    case = load_cases("status")["status-ratio-governing"]
    bearing = _verdict_set(case, "bearing", governing=False)
    body = _run(case, bearing=bearing)
    assert [f["families"]["bearing"] for f in body["footings"]] == [
        {"status": "PASS", "ratio": None},
        {"status": "FAIL", "ratio": None},
    ]


def test_the_state_flags_come_from_the_design_rows() -> None:
    case = load_cases("status")["status-mixed-fail-and-needs-engineer"]
    states = {row["id"]: row["state"] for row in _run(case)["footings"]}
    flags = {
        fid: [s["plan_at_max"], s["depth_at_max"], s["spacing_at_min"], s["engineer_sized"]]
        for fid, s in states.items()
    }
    assert flags == {
        "J1": [True, False, False, False],
        "J2": [False, True, False, True],
        "J3": [False, False, True, False],
    }


def test_a_footing_of_the_design_that_is_no_subject_is_refused() -> None:
    case = load_cases("status")["status-mixed-fail-and-needs-engineer"]
    subjects = copy.deepcopy(case.input["subjects"])
    subjects["subjects"] = [s for s in subjects["subjects"] if s["id"] != "J2"]
    with pytest.raises(ContractError) as caught:
        _run(case, subjects=subjects)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "design"
    assert caught.value.detail.received == "J2"


@pytest.mark.parametrize("family", FAMILIES)
def test_a_footing_without_a_verdict_in_a_family_is_refused(family: str) -> None:
    case = load_cases("status")["status-mixed-fail-and-needs-engineer"]
    with pytest.raises(ContractError) as caught:
        _run_with(case, None, {family: _verdict_set(case, family, drop="J3")})
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == family
    assert caught.value.detail.received == "J3"
    assert caught.value.detail.message == f"footing J3 has no verdict in the {family} set"


def test_a_verdict_about_another_footing_is_refused() -> None:
    case = load_cases("status")["status-mixed-fail-and-needs-engineer"]
    flexure = copy.deepcopy(case.input["flexure"])
    flexure["verdicts"][0]["subject"]["id"] = "J9"
    with pytest.raises(ContractError) as caught:
        _run(case, flexure=flexure)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "flexure"
    assert caught.value.detail.received == "J9"
    assert caught.value.detail.message == "a verdict of the flexure set is about footing J9, which is not in the design"


def test_a_verdict_about_a_subject_that_is_no_footing_is_refused() -> None:
    case = load_cases("status")["status-mixed-fail-and-needs-engineer"]
    punching = copy.deepcopy(case.input["punching"])
    punching["verdicts"][0]["subject"]["kind"] = "joint"
    with pytest.raises(ContractError) as caught:
        _run(case, punching=punching)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "punching"
    assert caught.value.detail.received == "J1"
    assert caught.value.detail.message == "a verdict of the punching set is about a joint, not a footing"


def test_run_through_the_calc_port(tmp_path: Path) -> None:
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"harness", clock)
    store = ResultStore(Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, ids, clock)
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=FixedClock(1, 1).now(), duration_ms=0)
    case = load_cases("status")["status-mixed-fail-and-needs-engineer"]
    args: dict[str, JsonValue] = {
        name: {"$ref": store.put(kind, case.input[name], producer).result_id} for name, kind in KINDS.items()
    }
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(
        REGISTRY,
        approvals,
        store,
        CalcSettings(max_items=1000),
        RunClass.TRIAL,
        clock,
        ids,
        basis_fields={CALC_ID: BASIS_FIELDS},
    )
    info = port.describe(CALC_ID)
    assert info.basis_fields == ()
    assert {name: sorted(rule.kinds) for name, rule in info.ref_rules.items()} == {n: [k] for n, k in KINDS.items()}
    out = port.run(CALC_ID, args)
    assert isinstance(out, SuccessEnvelope)
    assert out.kind == "harness.footing_status/1"
    stored = FootingStatus.model_validate(store.payload(out.result_id))
    assert stored.draft is True
    assert [(f.id, f.closure) for f in stored.footings] == [
        ("J1", "failing"),
        ("J2", "needs_engineer"),
        ("J3", "failing"),
    ]
    assert stored.trace.calc_id == CALC_ID
    literal = port.run(CALC_ID, args | {"bearing": case.input["bearing"]})
    assert isinstance(literal, FailureEnvelope)
    assert literal.error.code is ErrorCode.INVALID_ARGUMENT
