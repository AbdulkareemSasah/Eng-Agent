"""Golden cases of the column-workflow calcs (plan 0013 T2; spec 0013 AC4): one test per file of the data folder."""

import copy
import sys
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
from eng_harness.calcs.column_design.change_set import column_change_set
from eng_harness.calcs.column_design.column_demands import column_demands
from eng_harness.calcs.column_design.column_review import (
    BASIS_FIELDS as REVIEW_BASIS_FIELDS,
)
from eng_harness.calcs.column_design.column_review import (
    CODE_CHECKS,
    ReviewInput,
    column_review,
)
from eng_harness.calcs.column_design.column_select import BASIS_FIELDS, ColumnScope, SelectInput, column_select
from eng_harness.calcs.column_design.section_match import column_section_match
from eng_harness.kinds.column_design import ColumnReview, ColumnSelection
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
    "column-demands": (
        "harness.column_demands",
        {
            "selection": "harness.column_selection/1",
            "forces": "forces.member_end/1",
            "sections": "model.sections/1",
            "layouts": "basis.engineer_input/1",
            "combinations": "basis.engineer_input/1",
            "basis": "basis.design_basis/1",
        },
    ),
    "column-match": (
        "harness.column_section_match",
        {
            "column": "harness.column_selection/1",
            "size_b": "harness.section_size/1",
            "size_h": "harness.section_size/1",
            "size_d": "harness.section_size/1",
            "sections": "model.sections/1",
            "basis": "basis.design_basis/1",
        },
    ),
    "column-review": (
        "harness.column_review",
        {
            "selection": "harness.column_selection/1",
            "host": "harness.host_design_verdicts/1",
            "max_axial_strength": "verdicts.set/1",
            "axial_flexure_uniaxial": "verdicts.set/1",
            "longitudinal_reinforcement_limits": "verdicts.set/1",
            "items": "harness.column_check_items/1",
            "previous": "harness.column_review/1",
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
    trace = TraceBuilder()
    result = definition(input_type.model_validate(case.input), input_meta(case.refs, kinds), trace)
    assert result.model_dump(mode="json") == case.expected
    # AC6: column-demands goldens also pin hand-derived E3-E5 trace steps (values, units, source, uses, formula).
    if stem.startswith("column-demands-"):
        assert case.expected_trace is not None
        built = trace.build(definition, "ab" * 32)
        got = {
            s.name: {"value": s.value, "unit": s.unit, "source": s.source, "uses": list(s.uses), "formula": s.formula}
            for s in built.steps
            if s.source.endswith(" E3") or s.source.endswith(" E4") or s.source.endswith(" E5")
        }
        assert got == case.expected_trace["e3_e5_steps"]


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
    review = REGISTRY["harness.column_review"]
    assert (review.version, review.output_kind, review.verification) == (
        1,
        "harness.column_review/1",
        "draft",
    )
    assert review.method_source == "eng-harness spec 0013 §4.4.3 (R1 to R4); eng-harness spec 0003 §4.9 (S2, S5)"
    assert (column_select, column_demands, column_review, column_section_match, column_change_set) == COLUMN_DESIGN_CALCS
    assert set(COLUMN_DESIGN_KINDS) <= set(HARNESS_KINDS)
    assert BASIS_FIELDS == ("compare.length_mm",)
    assert REVIEW_BASIS_FIELDS == ("report.top_n",)
    assert CODE_CHECKS == (
        ("max_axial_strength", "aci318_14.22_4_2_1.max_axial_strength"),
        ("axial_flexure_uniaxial", "aci318_14.22_4_1_1.axial_flexure_uniaxial"),
        ("longitudinal_reinforcement_limits", "aci318_14.10_6_1_1.longitudinal_reinforcement_limits"),
    )


def test_trace_records_inputs_and_counts() -> None:
    trace = TraceBuilder()
    _select(trace=trace)
    built = trace.build(REGISTRY["harness.column_select"], "ab" * 32)
    assert [(c.name, c.cited.value, c.cited.unit, c.cited.source) for c in built.constants] == [
        ("radix", 2, "1", "IEEE 754 binary64 radix for even-power-of-two scaling before sqrt")
    ]
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


def test_exact_verticality_distinguishes_sub_ulp_offset() -> None:
    # Binary64 rounds 5.0^2 + (2^-26)^2 to 25.0 <= 5.0^2; exact Fraction has d^2 = 25 + 2^-52 > 25 (0013 L2, 0003 P2).
    dx, dy = 5.0, 2.0**-26
    assert dx * dx + dy * dy == 25.0
    frames = [
        {
            "id": "C_sub",
            "kind": "other",
            "section": "C40",
            "i": {"x_mm": 0, "y_mm": 0, "z_mm": 0},
            "j": {"x_mm": dx, "y_mm": dy, "z_mm": 3000},
            "story": "L1",
            "rotation_deg": 0,
        }
    ]
    body = _select(BOUNDARY, scope=_scope(frames=["C_sub"]), frames={"frames": frames}, basis=_basis(value=5.0))
    assert body == {
        "status": "FAIL",
        "columns": [],
        "excluded": [{"frame_id": "C_sub", "reason": "NOT_VERTICAL"}],
        "issues": [],
    }


@pytest.mark.parametrize("dz", [1e155, 1e-200])
def test_extreme_representable_lengths_do_not_overflow_or_underflow(dz: float) -> None:
    frames = [
        {
            "id": "C_ext",
            "kind": "other",
            "section": "C40",
            "i": {"x_mm": 0, "y_mm": 0, "z_mm": 0},
            "j": {"x_mm": 0, "y_mm": 0, "z_mm": dz},
            "story": "L1",
            "rotation_deg": 0,
        }
    ]
    body = _select(BOUNDARY, scope=_scope(frames=["C_ext"]), frames={"frames": frames})
    assert body["status"] == "PASS"
    assert body["columns"][0]["length_mm"] == dz


def test_maximum_finite_length_succeeds() -> None:
    max_dz = sys.float_info.max
    frames = [
        {
            "id": "C_max",
            "kind": "other",
            "section": "C40",
            "i": {"x_mm": 0, "y_mm": 0, "z_mm": 0},
            "j": {"x_mm": 0, "y_mm": 0, "z_mm": max_dz},
            "story": "L1",
            "rotation_deg": 0,
        }
    ]
    body = _select(BOUNDARY, scope=_scope(frames=["C_max"]), frames={"frames": frames})
    assert body["status"] == "PASS"
    assert body["columns"][0]["length_mm"] == max_dz


def test_near_overflow_unrepresentable_length_is_refused_on_frames() -> None:
    # A vertical frame from zi = -5 * 2^968 to zj = 2^1024 - 2^971 has exact length 2^1024 - 3 * 2^968 mm,
    # which exceeds the maximum finite binary64 value (and the round-to-nearest overflow midpoint).
    zi = float(-5 * (2**968))
    zj = sys.float_info.max
    frames = [
        {
            "id": "C_over_midpoint",
            "kind": "other",
            "section": "C40",
            "i": {"x_mm": 0, "y_mm": 0, "z_mm": zi},
            "j": {"x_mm": 0, "y_mm": 0, "z_mm": zj},
            "story": "L1",
            "rotation_deg": 0,
        }
    ]
    with pytest.raises(ContractError) as caught:
        _select(BOUNDARY, scope=_scope(frames=["C_over_midpoint"]), frames={"frames": frames})
    detail = caught.value.detail
    assert (detail.code, detail.field) == (ErrorCode.INVALID_ARGUMENT, "frames")


def test_unrepresentable_length_is_refused_on_frames() -> None:
    frames = [
        {
            "id": "C_over",
            "kind": "other",
            "section": "C40",
            "i": {"x_mm": 0, "y_mm": 0, "z_mm": -1e308},
            "j": {"x_mm": 0, "y_mm": 0, "z_mm": 1e308},
            "story": "L1",
            "rotation_deg": 0,
        }
    ]
    with pytest.raises(ContractError) as caught:
        _select(BOUNDARY, scope=_scope(frames=["C_over"]), frames={"frames": frames})
    detail = caught.value.detail
    assert (detail.code, detail.field) == (ErrorCode.INVALID_ARGUMENT, "frames")


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


# Contract and boundary tests of harness.column_review (spec 0013 4.4.3, AC8; spec 0003 4.4, 4.9).

REVIEW = "column-review-sources"
REVIEW_CHANGES = "column-review-changes"


def _review(
    stem: str = REVIEW,
    trace: TraceBuilder | None = None,
    meta_override: Any = None,
    **changes: Any,
) -> dict[str, Any]:
    case = load_case(FILES[stem])
    raw = copy.deepcopy(case.input) | changes
    for key, val in changes.items():
        if val is None:
            raw.pop(key, None)
    refs = {k: v for k, v in case.refs.items() if k in raw}
    meta = meta_override if meta_override is not None else input_meta(refs, CALCS["column-review"][1])
    return column_review(ReviewInput.model_validate(raw), meta, trace or TraceBuilder()).model_dump(mode="json")


def _review_basis(**field: Any) -> dict[str, Any]:
    base = {"value": 5, "unit": None, "source": "engineer:x@2026-01-01T00:00:00.000Z", "confirmed": True}
    return {"template": None, "fields": {"report.top_n": base | {"citation": None} | field}}


def test_column_review_trace_without_and_with_previous() -> None:
    trace = TraceBuilder()
    _review(REVIEW, trace=trace)
    built = trace.build(REGISTRY["harness.column_review"], "ab" * 32)
    assert built.constants == []
    refs = load_case(FILES[REVIEW]).refs
    inputs = {i.name: (i.value, i.unit, i.ref) for i in built.inputs}
    assert inputs == {
        "report_top_n": (5, None, f"{refs['basis']}#/fields/report.top_n"),
        "selection": (2, None, refs["selection"]),
        "host_verdicts": (2, None, refs["host"]),
        "max_axial_strength": (1, None, refs["max_axial_strength"]),
        "axial_flexure_uniaxial": (1, None, refs["axial_flexure_uniaxial"]),
        "longitudinal_reinforcement_limits": (2, None, refs["longitudinal_reinforcement_limits"]),
        "not_checked": (0, None, refs["items"]),
    }
    steps = {s.name: (s.value, s.source, s.uses) for s in built.steps}
    assert steps == {
        "selected_verdicts": (
            5,
            "spec 0013 4.4.3 R1",
            [
                "selection",
                "host_verdicts",
                "max_axial_strength",
                "axial_flexure_uniaxial",
                "longitudinal_reinforcement_limits",
            ],
        ),
        "member_count": (4, "spec 0013 4.4.3 R2", ["selected_verdicts"]),
        "failing_columns": (0, "spec 0013 4.4.3 R2", ["member_count", "not_checked"]),
        "attention_columns": (0, "spec 0013 4.4.3 R2", ["member_count", "not_checked"]),
        "top_rows": (5, "spec 0013 4.4.3 R3", ["report_top_n", "selected_verdicts"]),
        "change_count": (0, "spec 0013 4.4.3 R4", ["member_count"]),
    }
    assert all(s.formula for s in built.steps)
    assert built.outputs == ["failing_columns", "attention_columns", "top_rows"]

    trace_prev = TraceBuilder()
    _review(REVIEW_CHANGES, trace=trace_prev)
    built_prev = trace_prev.build(REGISTRY["harness.column_review"], "ab" * 32)
    prev_refs = load_case(FILES[REVIEW_CHANGES]).refs
    prev_inputs = {i.name: (i.value, i.ref) for i in built_prev.inputs}
    assert prev_inputs["previous_members"] == (5, prev_refs["previous"])
    prev_steps = {s.name: (s.value, s.uses) for s in built_prev.steps}
    assert prev_steps["change_count"] == (5, ["member_count", "previous_members"])
    assert prev_steps["selected_verdicts"] == (
        5,
        ["selection", "host_verdicts", "max_axial_strength", "longitudinal_reinforcement_limits"],
    )


@pytest.mark.parametrize(
    ("basis", "why"),
    [
        ({"template": None, "fields": {}}, "is missing (no default)"),
        (_review_basis(confirmed=False), "is not confirmed"),
        (_review_basis(unit="mm"), "must have no unit, not mm"),
        (_review_basis(value=0), "must be an integer >= 1"),
        (_review_basis(value=-2), "must be an integer >= 1"),
        (_review_basis(value=True), "must be an integer >= 1"),
        (_review_basis(value=1.5), "must be an integer >= 1"),
        (_review_basis(value="3"), "must be an integer >= 1"),
    ],
)
def test_column_review_basis_field_is_checked(basis: dict[str, Any], why: str) -> None:
    with pytest.raises(ContractError) as caught:
        _review(basis=basis)
    detail = caught.value.detail
    assert (detail.code, detail.field) == (ErrorCode.INVALID_ARGUMENT, "basis.fields.report.top_n")
    assert detail.message == f"basis field report.top_n {why}"
    assert detail.hint == "set and confirm report.top_n in the design basis"


@pytest.mark.parametrize(
    ("stem", "missing_field"),
    [
        (REVIEW, "selection"),
        (REVIEW, "host"),
        (REVIEW, "items"),
        (REVIEW, "basis"),
        (REVIEW, "max_axial_strength"),
        (REVIEW, "axial_flexure_uniaxial"),
        (REVIEW, "longitudinal_reinforcement_limits"),
        (REVIEW_CHANGES, "previous"),
    ],
)
def test_column_review_requires_record_refs(stem: str, missing_field: str) -> None:
    case = load_case(FILES[stem])
    meta = input_meta({k: v for k, v in case.refs.items() if k != missing_field}, CALCS["column-review"][1])
    with pytest.raises(ContractError) as caught:
        _review(stem, meta_override=meta)
    detail = caught.value.detail
    assert (detail.code, detail.field) == (ErrorCode.INVALID_ARGUMENT, missing_field)
    assert detail.message == f"{missing_field} must be a record reference"


def test_column_review_input_validation_refusals() -> None:
    case = load_case(FILES[REVIEW])
    # Duplicate frame_id in selection
    sel = copy.deepcopy(case.input["selection"])
    sel["columns"].append(copy.deepcopy(sel["columns"][0]))
    with pytest.raises(ContractError) as caught:
        _review(selection=sel)
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, "selection")
    assert caught.value.detail.message == "selection contains duplicate frame_id"

    # Host verdict with non-host source
    bad_host = copy.deepcopy(case.input["host"])
    bad_host["verdicts"][0] = copy.deepcopy(case.input["max_axial_strength"]["verdicts"][0])
    bad_host["traces"] = copy.deepcopy(case.input["max_axial_strength"]["traces"])
    with pytest.raises(ContractError) as caught:
        _review(host=bad_host)
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, "host")
    assert caught.value.detail.message == "host verdict 0 must have source host"

    # Code-check verdict set with wrong check_id or source
    bad_axial = copy.deepcopy(case.input["axial_flexure_uniaxial"])
    bad_axial["verdicts"][0] = copy.deepcopy(case.input["max_axial_strength"]["verdicts"][0])
    with pytest.raises(ContractError) as caught:
        _review(axial_flexure_uniaxial=bad_axial)
    assert (caught.value.detail.code, caught.value.detail.field) == (
        ErrorCode.INVALID_ARGUMENT,
        "axial_flexure_uniaxial",
    )
    assert (
        caught.value.detail.message
        == "axial_flexure_uniaxial verdict 0 must be code_pack for aci318_14.22_4_1_1.axial_flexure_uniaxial"
    )

    bad_source = copy.deepcopy(case.input["max_axial_strength"])
    bad_source["verdicts"][0]["source"] = "host"
    bad_source["verdicts"][0]["clause"] = None
    with pytest.raises(ContractError) as caught:
        _review(max_axial_strength=bad_source)
    assert (caught.value.detail.code, caught.value.detail.field) == (
        ErrorCode.INVALID_ARGUMENT,
        "max_axial_strength",
    )


def test_column_review_edge_cases_and_completeness() -> None:
    case = load_case(FILES[REVIEW])
    # Empty selection ignores all verdicts and produces empty columns, members, top
    empty_sel = copy.deepcopy(case.input["selection"])
    empty_sel["columns"] = []
    empty_sel["status"] = "FAIL"
    out_empty = _review(selection=empty_sel)
    assert out_empty["columns"] == []
    assert out_empty["members"] == []
    assert out_empty["top"] == {"n": 0, "of_total": 0, "rows": [], "label": "top 0 of 0 by ratio"}

    # Non-frame subject in host and unselected code_pack verdict are ignored by R1
    host_area = copy.deepcopy(case.input["host"])
    host_area["verdicts"][0]["subject"]["kind"] = "area"
    axial_other = copy.deepcopy(case.input["max_axial_strength"])
    axial_other["verdicts"][0]["subject"]["id"] = "C99"
    out_filtered = _review(host=host_area, max_axial_strength=axial_other)
    assert all(m["check_id"] != "aci318_14.22_4_2_1.max_axial_strength" for m in out_filtered["members"])

    # Incomplete input ref makes complete=False
    base_meta = input_meta({k: v for k, v in case.refs.items() if k in case.input}, CALCS["column-review"][1])
    inc_refs = dict(base_meta.refs)
    inc_refs["host"] = inc_refs["host"].model_copy(update={"complete": False})
    assert _review(meta_override=base_meta.model_copy(update={"refs": inc_refs}))["complete"] is False

    # FAIL member + not_checked keeps code_status=FAIL while status=NEEDS_ENGINEER (in attention, not failing)
    fail_max = copy.deepcopy(case.input["max_axial_strength"])
    fail_max["verdicts"][0]["demand"]["value"] = 2400.0
    fail_max["verdicts"][0]["ratio"] = 1.2
    fail_max["verdicts"][0]["status"] = "FAIL"
    fail_max["counts"] = {"PASS": 0, "FAIL": 1, "NOT_APPLICABLE": 0, "NEEDS_ENGINEER": 0, "ERROR": 0}
    items_nc = copy.deepcopy(case.input["items"])
    items_nc["not_checked"] = [{"frame_id": "C1", "code": "AXES_UNDECLARED", "gap": "CW-G9"}]
    out_nc_fail = _review(max_axial_strength=fail_max, items=items_nc)
    c1 = next(row for row in out_nc_fail["columns"] if row["frame_id"] == "C1")
    assert (c1["status"], c1["code_status"], c1["gaps"]) == ("NEEDS_ENGINEER", "FAIL", ["CW-G9"])
    assert (out_nc_fail["failing"], out_nc_fail["attention"]) == ([], ["C1"])

    # ERROR status and NOT_APPLICABLE-only status
    err_host = copy.deepcopy(case.input["host"])
    err_host["verdicts"][1]["status"] = "ERROR"
    err_host["verdicts"][1]["ratio"] = None
    err_host["counts"] = {"PASS": 1, "FAIL": 0, "NOT_APPLICABLE": 0, "NEEDS_ENGINEER": 0, "ERROR": 1}
    na_max = copy.deepcopy(case.input["max_axial_strength"])
    na_max["verdicts"][0]["status"] = "NOT_APPLICABLE"
    na_max["verdicts"][0]["ratio"] = None
    na_max["counts"] = {"PASS": 0, "FAIL": 0, "NOT_APPLICABLE": 1, "NEEDS_ENGINEER": 0, "ERROR": 0}
    out_na = _review(
        host=err_host,
        max_axial_strength=na_max,
        axial_flexure_uniaxial=None,
        longitudinal_reinforcement_limits=None,
    )
    by_id = {row["frame_id"]: row for row in out_na["columns"]}
    assert (by_id["C1"]["status"], by_id["C1"]["governing"]) == ("NOT_APPLICABLE", None)
    assert (by_id["C2"]["status"], by_id["C2"]["governing"]) == ("ERROR", None)
    assert out_na["attention"] == ["C2"]


def test_column_review_through_calc_port(tmp_path: Path) -> None:
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"harness", clock)
    store = ResultStore(Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, ids, clock)
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=FixedClock(1, 1).now(), duration_ms=0)
    case = load_case(FILES[REVIEW])
    kinds = CALCS["column-review"][1]
    args: dict[str, JsonValue] = {
        name: {"$ref": store.put(kinds[name], payload, producer).result_id} for name, payload in case.input.items()
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
        basis_fields={"harness.column_review": REVIEW_BASIS_FIELDS},
    )
    info = port.describe("harness.column_review")
    assert info.basis_fields == REVIEW_BASIS_FIELDS
    assert {name: sorted(rule.kinds) for name, rule in info.ref_rules.items()} == {n: [k] for n, k in kinds.items()}
    out = port.run("harness.column_review", args)
    assert isinstance(out, SuccessEnvelope), out
    assert out.kind == "harness.column_review/1"
    stored = ColumnReview.model_validate(store.payload(out.result_id))
    assert stored.draft is True
    # Normalize expected governing refs to the newly assigned store result ids for comparison
    id_map = {case.refs[name]: ref["$ref"] for name, ref in args.items() if isinstance(ref, dict)}
    dumped = stored.model_dump(mode="json", include=set(case.expected))
    for col in dumped["columns"]:
        if col["governing"] is not None:
            rid, ptr = col["governing"]["ref"].split("#", 1)
            assert rid in id_map.values()
            col["governing"]["ref"] = next(k for k, v in id_map.items() if v == rid) + "#" + ptr
    assert dumped == case.expected
    literal = port.run("harness.column_review", args | {"basis": case.input["basis"]})
    assert isinstance(literal, FailureEnvelope)
    assert literal.error.code is ErrorCode.INVALID_ARGUMENT
