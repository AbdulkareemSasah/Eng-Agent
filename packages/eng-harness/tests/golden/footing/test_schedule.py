"""Golden cases and contract of harness.footing_schedule (plan 0010 T6; spec 0010 AC11, section 4.4.6)."""

import copy
from pathlib import Path
from typing import Any

import pytest
from eng_contract.envelope import FailureEnvelope, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from pydantic import JsonValue, ValidationError

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.footing.schedule import BASIS_FIELDS, ScheduleInput, footing_schedule
from eng_harness.kinds.footing import FootingSchedule
from eng_harness.ports import RunClass

from . import FootingGoldenCase, input_meta, load_cases

CALC_ID = "harness.footing_schedule"
KINDS = {
    "subjects": "harness.footing_subjects/1",
    "design": "harness.footing_design/1",
    "status": "harness.footing_status/1",
    "basis": "basis.design_basis/1",
}
STEMS = [
    "schedule-assembled",
    "schedule-corner-above",
    "schedule-corner-at",
    "schedule-corner-below",
    "schedule-edge-x-at",
    "schedule-edge-x-below",
    "schedule-edge-y-at",
    "schedule-edge-y-below",
    "schedule-overlap",
    "schedule-rectangles",
    "schedule-zero-clear-distance",
]
DIGEST = "ab" * 32
FIELD = "foundation.min_clear_distance_mm"


def _run(case: FootingGoldenCase, trace: TraceBuilder | None = None, **changes: Any) -> dict[str, Any]:
    raw = copy.deepcopy(case.input) | changes
    result = footing_schedule(ScheduleInput.model_validate(raw), input_meta(case.refs, KINDS), trace or TraceBuilder())
    return result.model_dump(mode="json")


def _basis(**field: Any) -> dict[str, Any]:
    base = {"value": 1.0, "unit": "mm", "source": "engineer:x@2026-01-01T00:00:00.000Z", "confirmed": True}
    return {"template": None, "fields": {FIELD: base | {"citation": None} | field}}


def _moved(case: FootingGoldenCase, **places: tuple[float, float]) -> dict[str, Any]:
    """The subjects record of `case` with the named joints at new positions (x, y)."""
    subjects: dict[str, Any] = copy.deepcopy(case.input["subjects"])
    for row in subjects["subjects"]:
        if row["id"] in places:
            row["x_mm"], row["y_mm"] = places[row["id"]]
    return subjects


def _neighbours(body: dict[str, Any]) -> dict[str, str | None]:
    return {row["design"]["id"]: row["neighbour"] for row in body["footings"]}


def test_golden_cases() -> None:
    cases = load_cases("schedule")
    assert sorted(cases) == STEMS
    actual = {stem: _run(case) for stem, case in cases.items()}
    assert {stem: body for stem, body in actual.items() if body != cases[stem].expected} == {}


def test_trace_records_inputs_constants_and_counts() -> None:
    cases = load_cases("schedule")
    case = cases["schedule-assembled"]
    trace = TraceBuilder()
    _run(case, trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    inputs = {i.name: i for i in built.inputs}
    assert {n: i.value for n, i in inputs.items()} == {
        "subjects": 4,
        "design": 4,
        "status": 4,
        "closures": 3,
        "verdict_sets": 4,
        "decisions": 4,
        "min_clear_distance": 350.0,
    }
    assert inputs["min_clear_distance"].unit == "mm"
    assert inputs["min_clear_distance"].ref == f"{case.refs['basis']}#/fields/{FIELD}"
    assert inputs["design"].ref == case.refs["design"]
    assert inputs["subjects"].ref == case.refs["subjects"]
    assert inputs["status"].ref == case.refs["status"]
    assert inputs["closures"].ref is None
    assert {c.name: (c.cited.value, c.cited.unit) for c in built.constants} == {
        "halving": (2, "1"),
        "zero_distance": (0, "mm"),
    }
    assert all(c.cited.source for c in built.constants)
    steps = {s.name: s for s in built.steps}
    assert [
        (n, steps[n].value) for n in ("footings", "pairs", "overlapping_pairs", "close_pairs", "marked_footings")
    ] == [
        ("footings", 4),
        ("pairs", 6),
        ("overlapping_pairs", 0),
        ("close_pairs", 2),
        ("marked_footings", 3),
    ]
    assert list(steps["footings"].uses) == ["design"]
    assert list(steps["pairs"].uses) == ["footings"]
    assert list(steps["overlapping_pairs"].uses) == ["pairs", "subjects", "design", "halving", "zero_distance"]
    assert list(steps["close_pairs"].uses) == ["overlapping_pairs", "min_clear_distance"]
    assert list(steps["marked_footings"].uses) == ["overlapping_pairs", "close_pairs"]
    assert all(s.source.startswith("spec 0010 4.4.6") for s in built.steps)
    assert built.outputs == ["footings", "pairs", "overlapping_pairs", "close_pairs", "marked_footings"]


def test_overlaps_and_close_pairs_are_counted_apart() -> None:
    cases = load_cases("schedule")
    counts = {}
    for stem in ("schedule-overlap", "schedule-corner-below", "schedule-zero-clear-distance", "schedule-corner-at"):
        trace = TraceBuilder()
        _run(cases[stem], trace)
        steps = {s.name: s.value for s in trace.build(REGISTRY[CALC_ID], DIGEST).steps}
        counts[stem] = [steps[n] for n in ("pairs", "overlapping_pairs", "close_pairs", "marked_footings")]
    assert counts == {
        "schedule-overlap": [3, 1, 0, 2],
        "schedule-corner-below": [1, 0, 1, 2],
        "schedule-zero-clear-distance": [3, 1, 0, 2],
        "schedule-corner-at": [1, 0, 0, 0],
    }


def test_a_tie_in_distance_names_the_neighbour_with_the_smaller_id() -> None:
    case = load_cases("schedule")["schedule-assembled"]
    # J2 at x = 5000 has J1 at 2800 and J3 at 7200 at the same gap 2200 - 2000 = 200, both below 350
    body = _run(case, subjects=_moved(case, J1=(2800.0, 0.0)))
    assert _neighbours(body) == {"J1": "J2", "J2": "J1", "J3": "J2", "J4": None}


def test_an_overlap_is_named_before_a_neighbour_at_zero_distance() -> None:
    case = load_cases("schedule")["schedule-overlap"]
    # J1 touches J2 at a corner (gaps 0 and 0), J3 overlaps J2 (gaps -1000 and -2000); clear distance 100
    moved = _moved(case, J1=(3000.0, 2000.0), J2=(5000.0, 0.0), J3=(5500.0, 0.0))
    body = _run(case, subjects=moved, basis=_basis(value=100.0))
    assert _neighbours(body) == {"J1": "J2", "J2": "J3", "J3": "J2"}


def test_rows_are_sorted_by_footing_id_and_closures_come_from_the_status_rows() -> None:
    case = load_cases("schedule")["schedule-assembled"]
    body = _run(case)
    assert [row["design"]["id"] for row in body["footings"]] == ["J1", "J2", "J3", "J4"]
    assert [row["closure"] for row in body["footings"]] == ["failing", "passed", "needs_engineer", "passed"]


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ({"confirmed": False}, ErrorCode.INVALID_ARGUMENT),
        ({"value": "1"}, ErrorCode.INVALID_ARGUMENT),
        ({"value": True}, ErrorCode.INVALID_ARGUMENT),
        ({"value": -0.5}, ErrorCode.OUT_OF_RANGE),
    ],
)
def test_basis_field_is_checked(field: dict[str, Any], code: ErrorCode) -> None:
    with pytest.raises(ContractError) as caught:
        _run(load_cases("schedule")["schedule-overlap"], basis=_basis(**field))
    assert caught.value.detail.code is code
    assert caught.value.detail.field == "basis"


def test_a_basis_unit_other_than_mm_is_refused_by_the_basis_kind() -> None:
    with pytest.raises(ValidationError, match="does not match the unit suffix"):
        _run(load_cases("schedule")["schedule-overlap"], basis=_basis(unit="m"))


def test_missing_basis_field_is_refused() -> None:
    with pytest.raises(ContractError) as caught:
        _run(load_cases("schedule")["schedule-overlap"], basis={"template": None, "fields": {}})
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "basis"
    assert BASIS_FIELDS == (FIELD,)


def test_a_zero_clear_distance_is_accepted() -> None:
    body = _run(load_cases("schedule")["schedule-overlap"], basis=_basis(value=0))
    assert _neighbours(body) == {"J1": "J2", "J2": "J1", "J3": None}


def _refused(case: FootingGoldenCase, field: str, received: str, message: str, **changes: Any) -> None:
    with pytest.raises(ContractError) as caught:
        _run(case, **changes)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == field
    assert caught.value.detail.received == received
    assert caught.value.detail.message == message


def test_a_footing_of_the_design_that_is_no_subject_is_refused() -> None:
    case = load_cases("schedule")["schedule-overlap"]
    subjects = copy.deepcopy(case.input["subjects"])
    subjects["subjects"] = [s for s in subjects["subjects"] if s["id"] != "J3"]
    _refused(case, "design", "J3", "footing J3 of the design is not a subject", subjects=subjects)


def test_a_subject_without_a_design_row_is_refused() -> None:
    case = load_cases("schedule")["schedule-overlap"]
    design = copy.deepcopy(case.input["design"])
    design["footings"] = [f for f in design["footings"] if f["id"] != "J2"]
    status = copy.deepcopy(case.input["status"])
    status["footings"] = [f for f in status["footings"] if f["id"] != "J2"]
    _refused(case, "design", "J2", "subject J2 has no design row", design=design, status=status)


def test_a_footing_without_a_status_row_is_refused() -> None:
    case = load_cases("schedule")["schedule-overlap"]
    status = copy.deepcopy(case.input["status"])
    status["footings"] = [f for f in status["footings"] if f["id"] != "J1"]
    _refused(case, "status", "J1", "footing J1 has no status row", status=status)


def test_a_status_row_of_another_footing_is_refused() -> None:
    case = load_cases("schedule")["schedule-overlap"]
    status = copy.deepcopy(case.input["status"])
    extra = copy.deepcopy(status["footings"][0])
    extra["id"] = "J9"
    status["footings"].append(extra)
    _refused(case, "status", "J9", "status row J9 is not a footing of the design", status=status)


@pytest.mark.parametrize(
    ("field", "row"),
    [
        ("closures", {"id": "J9", "reason": "LIMIT_REACHED"}),
        ("verdict_sets", {"id": "J9", "result": "res_00000000000000000000000031"}),
        ("decisions", {"id": "J9", "decision": "dec_X"}),
    ],
)
def test_a_reference_row_of_another_footing_is_refused(field: str, row: dict[str, str]) -> None:
    case = load_cases("schedule")["schedule-overlap"]
    _refused(case, field, "J9", f"{field} names footing J9, which is not in the design", **{field: [row]})


def test_run_through_the_calc_port(tmp_path: Path) -> None:
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"harness", clock)
    store = ResultStore(Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, ids, clock)
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=FixedClock(1, 1).now(), duration_ms=0)
    case = load_cases("schedule")["schedule-assembled"]
    refs: dict[str, JsonValue] = {
        name: {"$ref": store.put(kind, case.input[name], producer).result_id} for name, kind in KINDS.items()
    }
    lists: dict[str, JsonValue] = {name: case.input[name] for name in ("closures", "verdict_sets", "decisions")}
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
    assert info.basis_fields == BASIS_FIELDS
    assert {name: sorted(rule.kinds) for name, rule in info.ref_rules.items()} == {n: [k] for n, k in KINDS.items()}
    out = port.run(CALC_ID, refs | lists)
    assert isinstance(out, SuccessEnvelope)
    assert out.kind == "harness.footing_schedule/1"
    stored = FootingSchedule.model_validate(store.payload(out.result_id))
    assert stored.draft is True
    assert [(f.design.id, f.neighbour) for f in stored.footings] == [
        ("J1", "J2"),
        ("J2", "J3"),
        ("J3", "J2"),
        ("J4", None),
    ]
    assert stored.trace.calc_id == CALC_ID
    literal = port.run(CALC_ID, refs | lists | {"basis": case.input["basis"]})
    assert isinstance(literal, FailureEnvelope)
    assert literal.error.code is ErrorCode.INVALID_ARGUMENT
