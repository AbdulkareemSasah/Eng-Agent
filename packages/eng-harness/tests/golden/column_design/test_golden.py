"""Golden cases of the column-workflow calcs (plan 0013 T2; spec 0013 AC4): one test per file of the data folder."""

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
from eng_harness.calc import CalcInput, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.column_design import COLUMN_DESIGN_CALCS, COLUMN_DESIGN_KINDS
from eng_harness.calcs.column_design.column_select import BASIS_FIELDS, ColumnScope, SelectInput, column_select
from eng_harness.kinds.column_design import ColumnSelection
from eng_harness.ports import RunClass

from . import golden_files, input_meta, load_case

CALCS = {
    "column-select": (
        "harness.column_select",
        {
            "scope": "basis.engineer_input/1",
            "frames": "model.frame_placements/1",
            "sections": "model.sections/1",
            "basis": "basis.design_basis/1",
        },
    ),
}
"""Per file prefix: the calc id and the record kind of each referenced input field."""
FILES = golden_files()


def _calc_of(stem: str) -> tuple[str, dict[str, str]]:
    return next(entry for prefix, entry in CALCS.items() if stem.startswith(f"{prefix}-"))


@pytest.mark.parametrize("stem", sorted(FILES))
def test_case(stem: str) -> None:
    case = load_case(FILES[stem])
    calc_id, kinds = _calc_of(stem)
    definition = REGISTRY[calc_id]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    result = definition(input_type.model_validate(case.input), input_meta(case.refs, kinds), TraceBuilder())
    assert result.model_dump(mode="json") == case.expected


# Contract and boundary tests of harness.column_select (spec 0013 4.4.1, AC4; spec 0003 4.2, 4.4).

SELECT = "column-select-names"
BOUNDARY = "column-select-vertical-boundary"


def _select(stem: str = SELECT, trace: TraceBuilder | None = None, **changes: Any) -> dict[str, Any]:
    case = load_case(FILES[stem])
    raw = copy.deepcopy(case.input) | changes
    meta = input_meta(case.refs, CALCS["column-select"][1])
    return column_select(SelectInput.model_validate(raw), meta, trace or TraceBuilder()).model_dump(mode="json")


def _basis(**field: Any) -> dict[str, Any]:
    base = {"value": 5, "unit": "mm", "source": "engineer:x@2026-01-01T00:00:00.000Z", "confirmed": True}
    return {"template": None, "fields": {"compare.length_mm": base | {"citation": None} | field}}


def _scope(**fields: Any) -> dict[str, Any]:
    return {"combinations": ["ULS1"], "special_seismic": False} | fields


def _frames(stem: str = SELECT) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = copy.deepcopy(load_case(FILES[stem]).input["frames"]["frames"])
    return frames


def _ids(rows: list[dict[str, Any]]) -> list[str]:
    return [row["frame_id"] for row in rows]


def test_registration_and_kinds() -> None:
    definition = REGISTRY["harness.column_select"]
    assert (definition.version, definition.output_kind, definition.verification) == (
        1,
        "harness.column_selection/1",
        "draft",
    )
    assert definition.method_source == "eng-harness spec 0013 §4.4.1 (L1 to L3); eng-harness spec 0003 §4.11 P2"
    assert (column_select,) == COLUMN_DESIGN_CALCS
    assert set(COLUMN_DESIGN_KINDS) <= set(HARNESS_KINDS)
    assert BASIS_FIELDS == ("compare.length_mm",)


def test_trace_records_inputs_and_counts() -> None:
    trace = TraceBuilder()
    _select(trace=trace)
    built = trace.build(REGISTRY["harness.column_select"], "ab" * 32)
    refs = load_case(FILES[SELECT]).refs
    inputs = {i.name: (i.value, i.unit, i.ref) for i in built.inputs}
    assert inputs == {
        "scope": (4, None, refs["scope"]),
        "frames": (5, None, refs["frames"]),
        "frame_sections": (4, None, refs["sections"]),
        "compare_length_mm": (5.0, "mm", f"{refs['basis']}#/fields/compare.length_mm"),
    }
    steps = {s.name: (s.value, s.source, s.uses) for s in built.steps}
    assert steps == {
        "in_scope": (4, "spec 0013 4.4.1 L1", ["scope", "frames"]),
        "issues": (0, "spec 0013 4.4.1 L1", ["scope", "frames", "frame_sections"]),
        "columns": (3, "spec 0013 4.4.1 L2", ["in_scope", "compare_length_mm"]),
        "excluded": (1, "spec 0013 4.4.1 L2", ["in_scope", "columns"]),
        "status": ("PASS", "spec 0013 4.4.1 L1 to L3", ["issues", "columns"]),
    }
    assert all(s.formula for s in built.steps)
    assert built.outputs == ["status", "columns", "excluded", "issues"]
    story = TraceBuilder()
    _select("column-select-story-section", trace=story)
    built = story.build(REGISTRY["harness.column_select"], "ab" * 32)
    assert next(i.value for i in built.inputs if i.name == "scope") == 3  # one story and two sections


@pytest.mark.parametrize(
    ("basis", "why"),
    [
        ({"template": None, "fields": {}}, "is missing (no default)"),
        (_basis(confirmed=False), "is not confirmed"),
        (_basis(value="5"), "must be a number >= 0"),
        (_basis(value=True), "must be a number >= 0"),
        (_basis(value=-0.5), "must be a number >= 0"),
    ],
)
def test_basis_field_is_checked(basis: dict[str, Any], why: str) -> None:
    with pytest.raises(ContractError) as caught:
        _select(basis=basis)
    detail = caught.value.detail
    assert (detail.code, detail.field) == (ErrorCode.INVALID_ARGUMENT, "basis.fields.compare.length_mm")
    assert detail.message == f"basis field compare.length_mm {why}"
    assert detail.hint == "set and confirm compare.length_mm in the design basis"


def test_zero_tolerance_keeps_only_exactly_vertical_frames() -> None:
    frames = _frames(BOUNDARY)
    frames[0]["j"] |= {"x_mm": 0, "y_mm": 0}  # C_in made exactly vertical
    body = _select(BOUNDARY, basis=_basis(value=0), frames={"frames": frames})
    assert _ids(body["columns"]) == ["C_in"]
    assert _ids(body["excluded"]) == ["C_at", "C_neg"]
    assert body["columns"][0]["length_mm"] == 3000.0


def test_fractional_tolerance_is_compared_exactly() -> None:
    below = _select(BOUNDARY, basis=_basis(value=4.999))
    assert _ids(below["columns"]) == ["C_in"]  # d^2 = 25 > 4.999^2 = 24.990001; C_in d^2 = 5
    assert _ids(below["excluded"]) == ["C_at", "C_neg"]
    assert _ids(_select(BOUNDARY, basis=_basis(value=5.0))["columns"]) == ["C_at", "C_in", "C_neg"]


def test_all_excluded_is_a_failed_selection_without_issue() -> None:
    body = _select(scope=_scope(frames=["B1"]))
    assert body == {
        "status": "FAIL",
        "columns": [],
        "excluded": [{"frame_id": "B1", "reason": "NOT_VERTICAL"}],
        "issues": [],
    }


def test_unknown_story_and_section_are_issues() -> None:
    body = _select(scope=_scope(select={"stories": ["L9", "L1", "L0"], "sections": ["NOPE", "C40"]}))
    assert body["issues"] == [
        {"code": "UNKNOWN_SECTION", "name": "NOPE"},
        {"code": "UNKNOWN_STORY", "name": "L0"},
        {"code": "UNKNOWN_STORY", "name": "L9"},
    ]
    assert body["status"] == "FAIL"
    assert _ids(body["columns"]) == ["C1"]


def test_selection_by_one_filter() -> None:
    by_section = _select(scope=_scope(select={"sections": ["C40"]}))
    assert _ids(by_section["columns"]) == ["C1", "C4"]
    by_story = _select(scope=_scope(select={"stories": ["L2"]}))
    assert _ids(by_story["columns"]) == ["C3", "C4"]
    assert by_story["status"] == by_section["status"] == "PASS"


def test_repeated_names_count_once() -> None:
    body = _select(scope=_scope(frames=["C1", "C1", "X", "X"]))
    assert _ids(body["columns"]) == ["C1"]
    assert body["issues"] == [{"code": "UNKNOWN_FRAME", "name": "X"}]


def test_unknown_section_of_a_column_is_refused() -> None:
    case = load_case(FILES[SELECT])
    rows = case.input["sections"]["frame_sections"]
    sections = {"frame_sections": [s for s in rows if s["name"] != "C50"], "area_sections": []}
    with pytest.raises(ContractError) as caught:
        _select(sections=sections)
    detail = caught.value.detail
    assert (detail.code, detail.field) == (ErrorCode.INVALID_ARGUMENT, "sections")
    assert detail.message == "section C50 of column C2 is not in the sections"
    sections = {"frame_sections": [s for s in rows if s["name"] != "B30"], "area_sections": []}
    assert _select(sections=sections)["excluded"] == [{"frame_id": "B1", "reason": "NOT_VERTICAL"}]


def test_column_without_story_is_refused() -> None:
    frames = _frames()
    frames[0]["story"] = None
    with pytest.raises(ContractError) as caught:
        _select(frames={"frames": frames})
    detail = caught.value.detail
    assert (detail.code, detail.field, detail.message) == (
        ErrorCode.INVALID_ARGUMENT,
        "frames",
        "column C1 has no story",
    )


@pytest.mark.parametrize(
    "scope",
    [
        _scope(),
        _scope(frames=["C1"], select={"stories": ["L1"]}),
        _scope(select={}),
        _scope(frames=[]),
        _scope(select={"stories": []}),
        _scope(frames=["C1"], combinations=[]),
        _scope(frames=["C1"], special_seismic="no"),
        _scope(frames=["C1"], extra=1),
    ],
)
def test_scope_shape_is_checked(scope: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ColumnScope.model_validate(scope)


def test_run_through_the_calc_port(tmp_path: Path) -> None:
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"harness", clock)
    store = ResultStore(Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, ids, clock)
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=FixedClock(1, 1).now(), duration_ms=0)
    case = load_case(FILES[SELECT])
    kinds = CALCS["column-select"][1]
    args: dict[str, JsonValue] = {
        name: {"$ref": store.put(kind, case.input[name], producer).result_id}
        for name, kind in kinds.items()
        if name != "scope"
    }
    who: dict[str, JsonValue] = {"unit": None, "entered_by": "x", "entered_at": "2026-01-01T00:00:00.000Z"}
    answer: dict[str, JsonValue] = {
        "step": "column_cycle.scope",
        "fields": {"scope": {"value": case.input["scope"]} | who},
    }
    args["scope"] = {"$ref": store.put(kinds["scope"], answer, producer).result_id + "#/fields/scope/value"}
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(
        REGISTRY,
        approvals,
        store,
        CalcSettings(max_items=1000),
        RunClass.TRIAL,
        clock,
        ids,
        basis_fields={"harness.column_select": BASIS_FIELDS},
    )
    info = port.describe("harness.column_select")
    assert info.basis_fields == BASIS_FIELDS
    assert {name: sorted(rule.kinds) for name, rule in info.ref_rules.items()} == {n: [k] for n, k in kinds.items()}
    out = port.run("harness.column_select", args)
    assert isinstance(out, SuccessEnvelope), out
    assert out.kind == "harness.column_selection/1"
    stored = ColumnSelection.model_validate(store.payload(out.result_id))
    assert stored.draft is True
    assert stored.model_dump(mode="json", include={"status", "columns", "excluded", "issues"}) == case.expected
    literal = port.run("harness.column_select", args | {"basis": case.input["basis"]})
    assert isinstance(literal, FailureEnvelope)
    assert literal.error.code is ErrorCode.INVALID_ARGUMENT
