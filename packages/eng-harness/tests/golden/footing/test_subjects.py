"""Golden cases and contract of harness.footing_subjects (plan 0010 T3; spec 0010 AC6, section 4.4.1)."""

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
from eng_harness.calcs.footing.subjects import BASIS_FIELDS, SubjectsInput, footing_subjects
from eng_harness.kinds.footing import FootingSubjects
from eng_harness.ports import RunClass

from . import FootingGoldenCase, input_meta, load_cases

CALC_ID = "harness.footing_subjects"
KINDS = {
    "placements": "model.frame_placements/1",
    "sections": "model.sections/1",
    "reactions": "forces.joint_reactions/1",
    "basis": "basis.design_basis/1",
}
STEMS = [
    "subjects-angle-tolerance",
    "subjects-basic",
    "subjects-excluded",
    "subjects-no-reactions",
    "subjects-wide-tolerance",
    "subjects-zero-tolerance",
]
DIGEST = "ab" * 32


def _run(case: FootingGoldenCase, trace: TraceBuilder | None = None, **changes: Any) -> dict[str, Any]:
    raw = copy.deepcopy(case.input) | changes
    result = footing_subjects(SubjectsInput.model_validate(raw), input_meta(case.refs, KINDS), trace or TraceBuilder())
    return result.model_dump(mode="json")


def _basis(**field: Any) -> dict[str, Any]:
    base = {"value": 1.0, "unit": "deg", "source": "engineer:x@2026-01-01T00:00:00.000Z", "confirmed": True}
    return {"template": None, "fields": {"compare.angle_deg": base | {"citation": None} | field}}


def test_golden_cases() -> None:
    cases = load_cases("subjects")
    assert sorted(cases) == STEMS
    actual = {stem: _run(case) for stem, case in cases.items()}
    assert {stem: body for stem, body in actual.items() if body != cases[stem].expected} == {}


def test_trace_records_inputs_constants_and_counts() -> None:
    cases = load_cases("subjects")
    trace = TraceBuilder()
    _run(cases["subjects-basic"], trace)
    built = trace.build(REGISTRY[CALC_ID], DIGEST)
    inputs = {i.name: i for i in built.inputs}
    angle = inputs["compare_angle"]
    assert (angle.value, angle.unit) == (1.0, "deg")
    assert angle.ref == f"{cases['subjects-basic'].refs['basis']}#/fields/compare.angle_deg"
    assert inputs["frames"].value == 5
    assert inputs["reaction_rows"].value == 8
    assert inputs["reaction_rows"].ref == cases["subjects-basic"].refs["reactions"]
    assert {c.name: c.cited.value for c in built.constants} == {
        "zero_turn": 0,
        "quarter_turn": 90,
        "half_turn": 180,
        "three_quarter_turn": 270,
        "full_turn": 360,
    }
    assert all(c.cited.unit == "deg" and c.cited.source for c in built.constants)
    steps = {s.name: s for s in built.steps}
    assert [(n, steps[n].value) for n in ("columns", "support_joints", "subjects", "excluded")] == [
        ("columns", 4),
        ("support_joints", 4),
        ("subjects", 4),
        ("excluded", 0),
    ]
    assert all(s.source.startswith("spec 0010 4.4.1 S") for s in built.steps)
    assert built.outputs == ["subjects", "excluded"]


def test_columns_counted_are_those_with_a_named_lower_joint() -> None:
    trace = TraceBuilder()
    _run(load_cases("subjects")["subjects-excluded"], trace)
    steps = {s.name: s.value for s in trace.build(REGISTRY[CALC_ID], DIGEST).steps}
    assert steps == {"columns": 7, "support_joints": 9, "subjects": 1, "excluded": 8}


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ({"confirmed": False}, ErrorCode.INVALID_ARGUMENT),
        ({"unit": "mm"}, ErrorCode.UNIT_MISMATCH),
        ({"value": "1"}, ErrorCode.INVALID_ARGUMENT),
        ({"value": True}, ErrorCode.INVALID_ARGUMENT),
        ({"value": -0.5}, ErrorCode.OUT_OF_RANGE),
    ],
)
def test_basis_field_is_checked(field: dict[str, Any], code: ErrorCode) -> None:
    with pytest.raises(ContractError) as caught:
        _run(load_cases("subjects")["subjects-basic"], basis=_basis(**field))
    assert caught.value.detail.code is code
    assert caught.value.detail.field == "basis"


def test_missing_basis_field_is_refused() -> None:
    with pytest.raises(ContractError) as caught:
        _run(load_cases("subjects")["subjects-basic"], basis={"template": None, "fields": {}})
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "basis"
    assert BASIS_FIELDS == ("compare.angle_deg",)


def test_a_zero_angle_tolerance_is_accepted() -> None:
    body = _run(load_cases("subjects")["subjects-basic"], basis=_basis(value=0))
    assert [s["id"] for s in body["subjects"]] == ["J1", "J2", "J3", "J4"]


def test_unknown_section_of_a_subject_column_is_refused() -> None:
    case = load_cases("subjects")["subjects-basic"]
    sections = copy.deepcopy(case.input["sections"])
    sections["frame_sections"] = [s for s in sections["frame_sections"] if s["name"] != "SEC-B"]
    with pytest.raises(ContractError) as caught:
        _run(case, sections=sections)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == "sections"


def test_unknown_section_of_a_column_that_is_no_subject_is_not_looked_up() -> None:
    case = load_cases("subjects")["subjects-excluded"]
    sections = copy.deepcopy(case.input["sections"])
    sections["frame_sections"] = [s for s in sections["frame_sections"] if s["name"] != "SEC-B"]
    with pytest.raises(ContractError):
        _run(case, sections=sections)  # C20 (SEC-B) is a subject candidate
    frames = [f for f in case.input["placements"]["frames"] if f["id"] != "C20"]
    assert _run(case, sections=sections, placements={"frames": frames})["subjects"] == []


def test_run_through_the_calc_port(tmp_path: Path) -> None:
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"harness", clock)
    store = ResultStore(Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, ids, clock)
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=FixedClock(1, 1).now(), duration_ms=0)
    case = load_cases("subjects")["subjects-basic"]
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
    assert info.basis_fields == BASIS_FIELDS
    assert {name: sorted(rule.kinds) for name, rule in info.ref_rules.items()} == {n: [k] for n, k in KINDS.items()}
    out = port.run(CALC_ID, args)
    assert isinstance(out, SuccessEnvelope)
    assert out.kind == "harness.footing_subjects/1"
    stored = FootingSubjects.model_validate(store.payload(out.result_id))
    assert stored.draft is True
    assert [s.id for s in stored.subjects] == ["J1", "J2", "J3", "J4"]
    assert stored.trace.calc_id == CALC_ID
    literal = port.run(CALC_ID, args | {"basis": case.input["basis"]})
    assert isinstance(literal, FailureEnvelope)
    assert literal.error.code is ErrorCode.INVALID_ARGUMENT
