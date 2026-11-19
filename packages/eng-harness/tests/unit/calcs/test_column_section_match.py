"""Contract of harness.column_section_match: sizes must be harness.section_size/1 references (spec 0013 AC9)."""

from pathlib import Path
from typing import Any

import pytest
from eng_contract.envelope import FailureEnvelope, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.params import InputPolicy, validate_input
from eng_contract.records import ResultRecord
from eng_contract.store import LocationClass, ResultStore, Workspace
from pydantic import JsonValue

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import CalcInput, InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.kinds.column_design import ColumnMatch
from eng_harness.ports import RunClass

CALC_ID = "harness.column_section_match"
SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"


class _NoStore:
    """A record source that holds nothing: literal inputs never reach it."""

    def get(self, result_id: str) -> ResultRecord:
        raise AssertionError(result_id)

    def payload(self, result_id: str) -> dict[str, Any]:
        raise AssertionError(result_id)


def _basis(value: float = 5) -> dict[str, Any]:
    return {
        "template": None,
        "fields": {
            "compare.length_mm": {
                "value": value,
                "unit": "mm",
                "source": SRC,
                "confirmed": True,
                "citation": None,
            }
        },
    }


def _column(*, frame_id: str = "C1", shape: str = "rectangular", material: str = "C30") -> dict[str, Any]:
    return {
        "frame_id": frame_id,
        "section": "C30x30",
        "shape": shape,
        "material": material,
        "story": "L1",
        "length_mm": 3000.0,
    }


def _qty(value: float, unit: str = "mm") -> dict[str, Any]:
    return {"value": value, "unit": unit}


def _size_record(value: float, multiple: int) -> dict[str, JsonValue]:
    return {
        "required": {"value": value, "unit": "mm"},
        "increment": {"value": 50.0, "unit": "mm"},
        "multiple": multiple,
        "size": {"value": value, "unit": "mm"},
        "status": "PASS",
        "calc": {
            "id": "harness.section_round",
            "version": 1,
            "content_sha256": "a" * 64,
            "status": "draft",
        },
        "draft": True,
        "trace": {
            "calc_id": "harness.section_round",
            "calc_version": "1",
            "content_sha256": "a" * 64,
            "inputs": [],
            "constants": [],
            "steps": [
                {
                    "name": "size",
                    "value": value,
                    "unit": "mm",
                    "formula": "n x i",
                    "source": "0003 4.10 N2",
                    "uses": [],
                }
            ],
            "outputs": ["size"],
        },
    }


def _sections(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"frame_sections": list(rows), "area_sections": []}


def _meta(*names: str) -> InputMeta:
    fields = names or ("column", "size_b", "size_h", "sections", "basis")
    kinds = {
        "column": "harness.column_selection/1",
        "size_b": "harness.section_size/1",
        "size_h": "harness.section_size/1",
        "size_d": "harness.section_size/1",
        "sections": "model.sections/1",
        "basis": "basis.design_basis/1",
    }
    return InputMeta(
        refs={
            name: RefMeta(
                result_id=f"res_01KCC00000000000000000000{i}",
                ref=(
                    f"res_01KCC00000000000000000000{i}#/size"
                    if name in {"size_b", "size_h", "size_d"}
                    else f"res_01KCC00000000000000000000{i}"
                ),
                kind=kinds[name],
                complete=True,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="fixture_tool",
            )
            for i, name in enumerate(fields, start=1)
        }
    )


def _input_type() -> type[CalcInput]:
    input_type = REGISTRY[CALC_ID].input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    return input_type


def _run(meta: InputMeta | None = None, trace: TraceBuilder | None = None, **changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "column": _column(),
        "size_b": _qty(400.0),
        "size_h": _qty(600.0),
        "sections": _sections(
            {"name": "C40x60", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 600}}
        ),
        "basis": _basis(),
    }
    raw.update(changes)
    used_meta = meta if meta is not None else _meta("column", "size_b", "size_h", "sections", "basis")
    return REGISTRY[CALC_ID](_input_type().model_validate(raw), used_meta, trace or TraceBuilder()).model_dump(
        mode="json"
    )


def test_size_must_be_rounding_result(tmp_path: Path) -> None:
    """AC9: sizes are accepted only as harness.section_size/1 references; any literal is INVALID_ARGUMENT."""
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"match", clock)
    store = ResultStore(Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, ids, clock)
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=FixedClock(1, 1).now(), duration_ms=0)
    selection_payload: dict[str, JsonValue] = {
        "status": "PASS",
        "columns": [_column(), _column(frame_id="C2", shape="circular", material="C35")],
        "excluded": [],
        "issues": [],
        "calc": {"id": "harness.column_select", "version": 1, "content_sha256": "b" * 64, "status": "draft"},
        "draft": True,
        "trace": {
            "calc_id": "harness.column_select",
            "calc_version": "1",
            "content_sha256": "b" * 64,
            "inputs": [],
            "constants": [],
            "steps": [
                {
                    "name": "status",
                    "value": "PASS",
                    "unit": None,
                    "formula": "PASS",
                    "source": "0013 4.4.1",
                    "uses": [],
                }
            ],
            "outputs": ["status"],
        },
    }
    sel_id = store.put("harness.column_selection/1", selection_payload, producer).result_id
    sec_id = store.put(
        "model.sections/1",
        _sections(
            {"name": "C40x60", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 600}},
            {"name": "C50", "material": "C35", "shape": {"type": "circular", "D_mm": 500}},
        ),
        producer,
    ).result_id
    basis_id = store.put("basis.design_basis/1", _basis(), producer).result_id
    sb_id = store.put("harness.section_size/1", _size_record(400.0, 8), producer).result_id
    sh_id = store.put("harness.section_size/1", _size_record(600.0, 12), producer).result_id
    sd_id = store.put("harness.section_size/1", _size_record(500.0, 10), producer).result_id
    other_id = store.put(
        "basis.engineer_input/1",
        {
            "step": "column_cycle.proposal",
            "fields": {
                "b": {
                    "value": {"value": 400.0, "unit": "mm"},
                    "unit": "mm",
                    "entered_by": "x",
                    "entered_at": "2026-01-01T00:00:00.000Z",
                }
            },
        },
        producer,
    ).result_id
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(
        REGISTRY,
        approvals,
        store,
        CalcSettings(max_items=1000),
        RunClass.TRIAL,
        clock,
        ids,
        basis_fields={"harness.column_section_match": ("compare.length_mm",)},
    )
    info = port.describe(CALC_ID)
    assert {name: sorted(rule.kinds) for name, rule in info.ref_rules.items()} == {
        "column": ["harness.column_selection/1"],
        "size_b": ["harness.section_size/1"],
        "size_h": ["harness.section_size/1"],
        "size_d": ["harness.section_size/1"],
        "sections": ["model.sections/1"],
        "basis": ["basis.design_basis/1"],
    }
    assert {name: rule.unit for name, rule in info.ref_rules.items() if name.startswith("size_")} == {
        "size_b": "mm",
        "size_h": "mm",
        "size_d": "mm",
    }

    rect_args: dict[str, JsonValue] = {
        "column": {"$ref": f"{sel_id}#/columns/0"},
        "size_b": {"$ref": f"{sb_id}#/size"},
        "size_h": {"$ref": f"{sh_id}#/size"},
        "sections": {"$ref": sec_id},
        "basis": {"$ref": basis_id},
    }
    out = port.run(CALC_ID, rect_args)
    assert isinstance(out, SuccessEnvelope), out
    stored = ColumnMatch.model_validate(store.payload(out.result_id))
    assert (stored.status, stored.section, stored.names) == ("matched", "C40x60", ["C40x60"])
    assert {i.name: i.ref for i in stored.trace.inputs} == {
        "column": sel_id,
        "frame_sections": sec_id,
        "compare_length_mm": f"{basis_id}#/fields/compare.length_mm",
        "size_b_mm": f"{sb_id}#/size",
        "size_h_mm": f"{sh_id}#/size",
    }
    assert {sb_id, sh_id} <= set(store.get(out.result_id).parents)

    circ_args: dict[str, JsonValue] = {
        "column": {"$ref": f"{sel_id}#/columns/1"},
        "size_d": {"$ref": f"{sd_id}#/size"},
        "sections": {"$ref": sec_id},
        "basis": {"$ref": basis_id},
    }
    circ_out = port.run(CALC_ID, circ_args)
    assert isinstance(circ_out, SuccessEnvelope), circ_out
    circ_stored = ColumnMatch.model_validate(store.payload(circ_out.result_id))
    assert (circ_stored.status, circ_stored.section) == ("matched", "C50")
    assert {i.name: i.ref for i in circ_stored.trace.inputs}["size_D_mm"] == f"{sd_id}#/size"

    full_body: dict[str, JsonValue] = {
        "required": {"value": 300.0, "unit": "mm"},
        "increment": {"value": 50.0, "unit": "mm"},
        "multiple": 6,
        "size": {"value": 300.0, "unit": "mm"},
        "status": "PASS",
    }
    bad_rect: tuple[tuple[str, JsonValue], ...] = (
        ("size_b", {"value": 400.0, "unit": "mm"}),
        ("size_h", {"value": 600.0, "unit": "mm"}),
        ("size_b", full_body),
        ("size_b", {"$ref": sb_id}),
    )
    for field, value in bad_rect:
        bad = port.run(CALC_ID, rect_args | {field: value})
        assert isinstance(bad, FailureEnvelope)
        assert (bad.error.code, bad.error.field) == (ErrorCode.INVALID_ARGUMENT, field)

    bad_circ_cases: tuple[tuple[str, JsonValue], ...] = (
        ("size_d", {"value": 500.0, "unit": "mm"}),
        ("size_d", full_body),
    )
    for field, value in bad_circ_cases:
        bad_circ = port.run(CALC_ID, circ_args | {field: value})
        assert isinstance(bad_circ, FailureEnvelope)
        assert (bad_circ.error.code, bad_circ.error.field) == (ErrorCode.INVALID_ARGUMENT, field)

    wrong_kind = port.run(CALC_ID, rect_args | {"size_b": {"$ref": f"{other_id}#/fields/b/value"}})
    assert isinstance(wrong_kind, FailureEnvelope)
    assert (wrong_kind.error.code, wrong_kind.error.field) == (ErrorCode.REF_KIND_MISMATCH, "size_b")


def test_just_beyond_tolerance_is_not_a_candidate() -> None:
    """M1 exclusive of differences above compare.length_mm: |406 - 400| = 6 > 5."""
    body = _run(
        sections=_sections(
            {"name": "C406x600", "material": "C30", "shape": {"type": "rectangular", "b_mm": 406, "h_mm": 600}}
        )
    )
    assert body == {"status": "no_section_in_model", "section": None, "names": []}


def test_zero_tolerance_requires_exact_dimensions() -> None:
    body = _run(
        basis=_basis(0),
        sections=_sections(
            {"name": "C405x600", "material": "C30", "shape": {"type": "rectangular", "b_mm": 405, "h_mm": 600}},
            {"name": "C40x60", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 600}},
        ),
    )
    assert body == {"status": "matched", "section": "C40x60", "names": ["C40x60"]}


def test_other_shape_column_has_no_candidates() -> None:
    body = _run(column=_column(shape="other"))
    assert body["status"] == "no_section_in_model"
    assert body["names"] == []


@pytest.mark.parametrize("missing", ["column", "sections", "basis", "size_b", "size_h"])
def test_missing_record_refs_are_refused(missing: str) -> None:
    present = tuple(n for n in ("column", "size_b", "size_h", "sections", "basis") if n != missing)
    with pytest.raises(ContractError) as caught:
        _run(meta=_meta(*present))
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, missing)


def test_missing_circular_size_ref_is_refused() -> None:
    raw = {
        "column": _column(shape="circular"),
        "size_d": _qty(500.0),
        "sections": _sections({"name": "C50", "material": "C30", "shape": {"type": "circular", "D_mm": 500}}),
        "basis": _basis(),
    }
    with pytest.raises(ContractError) as caught:
        REGISTRY[CALC_ID](_input_type().model_validate(raw), _meta("column", "sections", "basis"), TraceBuilder())
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, "size_d")


@pytest.mark.parametrize(
    "sizes",
    [
        {},
        {"size_b": _qty(400.0)},
        {"size_h": _qty(600.0)},
        {"size_b": _qty(400.0), "size_d": _qty(500.0)},
        {"size_b": _qty(400.0), "size_h": _qty(600.0), "size_d": _qty(500.0)},
    ],
)
def test_invalid_size_combinations_are_refused(sizes: dict[str, Any]) -> None:
    raw: dict[str, Any] = {
        "column": _column(),
        **sizes,
        "sections": _sections(
            {"name": "C40x60", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 600}}
        ),
        "basis": _basis(),
    }
    with pytest.raises(ContractError) as caught:
        validate_input(
            _input_type(),
            raw,
            source=_NoStore(),
            current_revision=lambda _: None,
            policy=InputPolicy(require_refs=False),
        )
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT


def test_shape_and_size_disagreement_is_refused() -> None:
    with pytest.raises(ContractError) as rect_caught:
        _run(
            meta=_meta("column", "size_d", "sections", "basis"),
            column=_column(shape="rectangular"),
            size_b=None,
            size_h=None,
            size_d=_qty(500.0),
        )
    assert (rect_caught.value.detail.code, rect_caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, "size_b")

    with pytest.raises(ContractError) as circ_caught:
        _run(column=_column(shape="circular"))
    assert (circ_caught.value.detail.code, circ_caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, "size_d")


def test_trace_records_inputs_and_steps() -> None:
    trace = TraceBuilder()
    _run(trace=trace)
    built = trace.build(REGISTRY[CALC_ID], "ab" * 32)
    meta = _meta("column", "size_b", "size_h", "sections", "basis")
    inputs = {i.name: (i.value, i.unit, i.ref) for i in built.inputs}
    assert inputs == {
        "column": ("C1", None, meta.refs["column"].result_id),
        "frame_sections": (1, None, meta.refs["sections"].result_id),
        "compare_length_mm": (5.0, "mm", f"{meta.refs['basis'].result_id}#/fields/compare.length_mm"),
        "size_b_mm": (400.0, "mm", meta.refs["size_b"].ref),
        "size_h_mm": (600.0, "mm", meta.refs["size_h"].ref),
    }
    steps = {s.name: (s.value, s.source, s.uses) for s in built.steps}
    assert steps == {
        "candidates": (1, "spec 0013 4.4.4 M1", []),
        "status": ("matched", "spec 0013 4.4.4 M2", []),
        "section": ("C40x60", "spec 0013 4.4.4 M2", ["candidates"]),
        "names": (1, "spec 0013 4.4.4 M2", ["candidates"]),
    }
    assert built.outputs == ["status", "section", "names"]


def test_size_pointer_must_be_size(tmp_path: Path) -> None:
    """B-580 / AC9: size_b, size_h and size_d must point at /size; #/required and #/increment are refused.

    On a harness.section_size/1 record whose required differs from size, a reference to #/required (or
    #/increment) would otherwise match on the unrounded dimension while a rebuilt trace pointed at #/size.
    """
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"sizeptr", clock)
    store = ResultStore(Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, ids, clock)
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=FixedClock(1, 1).now(), duration_ms=0)
    selection_payload: dict[str, JsonValue] = {
        "status": "PASS",
        "columns": [_column(), _column(frame_id="C2", shape="circular", material="C35")],
        "excluded": [],
        "issues": [],
        "calc": {"id": "harness.column_select", "version": 1, "content_sha256": "b" * 64, "status": "draft"},
        "draft": True,
        "trace": {
            "calc_id": "harness.column_select",
            "calc_version": "1",
            "content_sha256": "b" * 64,
            "inputs": [],
            "constants": [],
            "steps": [
                {
                    "name": "status",
                    "value": "PASS",
                    "unit": None,
                    "formula": "PASS",
                    "source": "0013 4.4.1",
                    "uses": [],
                }
            ],
            "outputs": ["status"],
        },
    }
    sel_id = store.put("harness.column_selection/1", selection_payload, producer).result_id
    sec_id = store.put(
        "model.sections/1",
        _sections(
            {"name": "C40x60", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 600}},
            {"name": "C50", "material": "C35", "shape": {"type": "circular", "D_mm": 500}},
        ),
        producer,
    ).result_id
    basis_id = store.put("basis.design_basis/1", _basis(), producer).result_id
    # required=375, size=400 (8 x 50); required differs from size so a wrong pointer changes the matched value.
    size_b = store.put(
        "harness.section_size/1",
        {
            "required": {"value": 375.0, "unit": "mm"},
            "increment": {"value": 50.0, "unit": "mm"},
            "multiple": 8,
            "size": {"value": 400.0, "unit": "mm"},
            "status": "PASS",
            "calc": {"id": "harness.section_round", "version": 1, "content_sha256": "a" * 64, "status": "draft"},
            "draft": True,
            "trace": {
                "calc_id": "harness.section_round",
                "calc_version": "1",
                "content_sha256": "a" * 64,
                "inputs": [],
                "constants": [],
                "steps": [
                    {
                        "name": "size",
                        "value": 400.0,
                        "unit": "mm",
                        "formula": "n x i",
                        "source": "0003 4.10 N2",
                        "uses": [],
                    }
                ],
                "outputs": ["size"],
            },
        },
        producer,
    ).result_id
    size_h = store.put(
        "harness.section_size/1",
        {
            "required": {"value": 575.0, "unit": "mm"},
            "increment": {"value": 50.0, "unit": "mm"},
            "multiple": 12,
            "size": {"value": 600.0, "unit": "mm"},
            "status": "PASS",
            "calc": {"id": "harness.section_round", "version": 1, "content_sha256": "a" * 64, "status": "draft"},
            "draft": True,
            "trace": {
                "calc_id": "harness.section_round",
                "calc_version": "1",
                "content_sha256": "a" * 64,
                "inputs": [],
                "constants": [],
                "steps": [
                    {
                        "name": "size",
                        "value": 600.0,
                        "unit": "mm",
                        "formula": "n x i",
                        "source": "0003 4.10 N2",
                        "uses": [],
                    }
                ],
                "outputs": ["size"],
            },
        },
        producer,
    ).result_id
    size_d = store.put(
        "harness.section_size/1",
        {
            "required": {"value": 475.0, "unit": "mm"},
            "increment": {"value": 50.0, "unit": "mm"},
            "multiple": 10,
            "size": {"value": 500.0, "unit": "mm"},
            "status": "PASS",
            "calc": {"id": "harness.section_round", "version": 1, "content_sha256": "a" * 64, "status": "draft"},
            "draft": True,
            "trace": {
                "calc_id": "harness.section_round",
                "calc_version": "1",
                "content_sha256": "a" * 64,
                "inputs": [],
                "constants": [],
                "steps": [
                    {
                        "name": "size",
                        "value": 500.0,
                        "unit": "mm",
                        "formula": "n x i",
                        "source": "0003 4.10 N2",
                        "uses": [],
                    }
                ],
                "outputs": ["size"],
            },
        },
        producer,
    ).result_id
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(
        REGISTRY,
        approvals,
        store,
        CalcSettings(max_items=1000),
        RunClass.TRIAL,
        clock,
        ids,
        basis_fields={"harness.column_section_match": ("compare.length_mm",)},
    )
    rect_ok: dict[str, JsonValue] = {
        "column": {"$ref": f"{sel_id}#/columns/0"},
        "size_b": {"$ref": f"{size_b}#/size"},
        "size_h": {"$ref": f"{size_h}#/size"},
        "sections": {"$ref": sec_id},
        "basis": {"$ref": basis_id},
    }
    ok = port.run(CALC_ID, rect_ok)
    assert isinstance(ok, SuccessEnvelope), ok
    stored = ColumnMatch.model_validate(store.payload(ok.result_id))
    assert (stored.status, stored.section) == ("matched", "C40x60")
    assert {i.name: i.ref for i in stored.trace.inputs}["size_b_mm"] == f"{size_b}#/size"
    assert {i.name: i.ref for i in stored.trace.inputs}["size_h_mm"] == f"{size_h}#/size"

    for field, rid, pointer in (
        ("size_b", size_b, "/required"),
        ("size_b", size_b, "/increment"),
        ("size_h", size_h, "/required"),
        ("size_h", size_h, "/increment"),
    ):
        bad = port.run(CALC_ID, rect_ok | {field: {"$ref": f"{rid}#{pointer}"}})
        assert isinstance(bad, FailureEnvelope), (field, pointer, bad)
        assert (bad.error.code, bad.error.field) == (ErrorCode.INVALID_ARGUMENT, field)

    circ_ok: dict[str, JsonValue] = {
        "column": {"$ref": f"{sel_id}#/columns/1"},
        "size_d": {"$ref": f"{size_d}#/size"},
        "sections": {"$ref": sec_id},
        "basis": {"$ref": basis_id},
    }
    circ = port.run(CALC_ID, circ_ok)
    assert isinstance(circ, SuccessEnvelope), circ
    assert ColumnMatch.model_validate(store.payload(circ.result_id)).section == "C50"
    for pointer in ("/required", "/increment"):
        bad_d = port.run(CALC_ID, circ_ok | {"size_d": {"$ref": f"{size_d}#{pointer}"}})
        assert isinstance(bad_d, FailureEnvelope), pointer
        assert (bad_d.error.code, bad_d.error.field) == (ErrorCode.INVALID_ARGUMENT, "size_d")
