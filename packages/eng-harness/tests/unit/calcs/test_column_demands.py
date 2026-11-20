"""Unit and contract tests of `harness.column_demands` (plan 0013 T3; spec 0013 AC6, AC7, §4.4.2)."""

import copy
import math
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.envelope import FailureEnvelope, LiteralInput, Provenance, RefInput, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.params import InputPolicy, ParamModel, validate_input
from eng_contract.records import ResultRecord
from eng_contract.store import LocationClass, ResultStore, Workspace
from pydantic import JsonValue, ValidationError
from structural_codes.pack import Registry

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import CalcInput, InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.column_design.column_demands import (
    BASIS_FIELDS,
    ColumnLayout,
    DemandsInput,
    _to_finite_float,
    column_demands,
)
from eng_harness.errors import NotImplementedGap
from eng_harness.ports import RunClass

CALC_ID = "harness.column_demands"
MAX_AXIAL_ID = "aci318_14.22_4_2_1.max_axial_strength"
AXIAL_FLEXURE_ID = "aci318_14.22_4_1_1.axial_flexure_uniaxial"
REINF_LIMITS_ID = "aci318_14.10_6_1_1.longitudinal_reinforcement_limits"
BASIS_PATHS = (
    "materials.concrete_fc_MPa",
    "materials.rebar_fy_MPa",
    "columns.effective_length_factor_ratio",
    "limits.ratio_limit_ratio",
)
SPEC_FIELD_NAMES = {
    MAX_AXIAL_ID: {
        "Pu_kN",
        "b_mm",
        "h_mm",
        "Ast_mm2",
        "fc_MPa",
        "fy_MPa",
        "transverse_kind",
        "k_factor",
        "lu_mm",
        "ratio_limit",
    },
    AXIAL_FLEXURE_ID: {
        "Pu_kN",
        "Mu_kNm",
        "Mu_other_kNm",
        "b_mm",
        "h_mm",
        "d_prime_mm",
        "n_bars_b",
        "n_bars_h",
        "A_bar_mm2",
        "fc_MPa",
        "fy_MPa",
        "transverse_kind",
        "k_factor",
        "lu_mm",
        "ratio_limit",
    },
    REINF_LIMITS_ID: {"Ag_mm2", "Ast_mm2", "ratio_limit"},
}
_START_MS = 1_767_225_600_000
_DIGEST = "ab" * 32
_SRC = "engineer:trial@2026-11-01T00:00:00.000Z"


class _RawSourceStore(ResultStore):
    """Result store that counts `put` calls and can serve raw unvalidated records for refusal tests."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.puts = 0
        self._raw_records: dict[str, tuple[ResultRecord, dict[str, JsonValue]]] = {}

    def put(self, *args: Any, **kwargs: Any) -> ResultRecord:
        self.puts += 1
        return super().put(*args, **kwargs)

    def inject_raw(self, result_id: str, record: ResultRecord, payload: dict[str, JsonValue]) -> None:
        self._raw_records[result_id] = (record, payload)

    def get(self, result_id: str) -> ResultRecord:
        if result_id in self._raw_records:
            return self._raw_records[result_id][0]
        return super().get(result_id)

    def payload(self, result_id: str) -> dict[str, JsonValue]:
        if result_id in self._raw_records:
            return self._raw_records[result_id][1]
        return super().payload(result_id)


def _basis(**overrides: dict[str, Any] | None) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "materials.concrete_fc_MPa": {
            "value": 30.0,
            "unit": "MPa",
            "source": _SRC,
            "confirmed": True,
            "citation": None,
        },
        "materials.rebar_fy_MPa": {"value": 420.0, "unit": "MPa", "source": _SRC, "confirmed": True, "citation": None},
        "columns.effective_length_factor_ratio": {
            "value": 1.0,
            "unit": "1",
            "source": _SRC,
            "confirmed": True,
            "citation": None,
        },
        "limits.ratio_limit_ratio": {"value": 1.0, "unit": "1", "source": _SRC, "confirmed": True, "citation": None},
    }
    for key, value in overrides.items():
        if value is None:
            fields.pop(key, None)
        else:
            fields[key] = value
    return {"template": None, "fields": fields}


def _selection(columns: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "calc": {"id": "harness.column_select", "version": 1, "content_sha256": _DIGEST, "status": "draft"},
        "draft": True,
        "trace": {
            "calc_id": "harness.column_select",
            "calc_version": "1",
            "content_sha256": _DIGEST,
            "inputs": [],
            "constants": [],
            "steps": [],
            "outputs": [],
        },
        "status": "PASS",
        "columns": columns,
        "excluded": [],
        "issues": [],
    }


def _base_inputs() -> dict[str, Any]:
    return {
        "selection": _selection(
            [
                {
                    "frame_id": "C1",
                    "section": "C40",
                    "shape": "rectangular",
                    "material": "C30",
                    "story": "L1",
                    "length_mm": 3000.0,
                },
                {
                    "frame_id": "C2",
                    "section": "C40x60",
                    "shape": "rectangular",
                    "material": "C30",
                    "story": "L1",
                    "length_mm": 3200.0,
                },
            ]
        ),
        "forces": {
            "sign_convention": "host_local/1",
            "rows": [
                {
                    "member": "C1",
                    "case": {"case": "ULS1", "case_type": "load_combination", "step": None},
                    "end": "i",
                    "station_mm": 0.0,
                    "P_kN": -900.0,
                    "V2_kN": 0.0,
                    "V3_kN": 0.0,
                    "T_kNm": 0.0,
                    "M2_kNm": 0.0,
                    "M3_kNm": 40.0,
                },
                {
                    "member": "C2",
                    "case": {"case": "ULS1", "case_type": "load_combination", "step": None},
                    "end": "i",
                    "station_mm": 0.0,
                    "P_kN": -1100.0,
                    "V2_kN": 0.0,
                    "V3_kN": 0.0,
                    "T_kNm": 0.0,
                    "M2_kNm": 0.0,
                    "M3_kNm": 50.0,
                },
            ],
        },
        "sections": {
            "frame_sections": [
                {"name": "C40", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400.0, "h_mm": 400.0}},
                {"name": "C40x60", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400.0, "h_mm": 600.0}},
            ],
            "area_sections": [],
        },
        "layouts": {
            "sections": [
                {
                    "section": "C40",
                    "transverse_kind": "tied",
                    "n_bars_b": 3,
                    "n_bars_h": 3,
                    "A_bar": {"source": "input", "value": 500.0, "unit": "mm2"},
                    "d_prime": {"source": "input", "value": 50.0, "unit": "mm"},
                },
                {
                    "section": "C40x60",
                    "transverse_kind": "tied",
                    "n_bars_b": 3,
                    "n_bars_h": 4,
                    "A_bar": {"source": "input", "value": 500.0, "unit": "mm2"},
                    "d_prime": {"source": "input", "value": 60.0, "unit": "mm"},
                },
            ]
        },
        "combinations": ["ULS1"],
        "basis": _basis(),
    }


def _meta() -> InputMeta:
    kinds = {
        "selection": "harness.column_selection/1",
        "forces": "forces.member_end/1",
        "sections": "model.sections/1",
        "layouts": "basis.engineer_input/1",
        "combinations": "basis.engineer_input/1",
        "basis": "basis.design_basis/1",
    }
    return InputMeta(
        refs={
            name: RefMeta(
                result_id=f"res_01KCD{'0' * 20}{idx}",
                ref=f"res_01KCD{'0' * 20}{idx}",
                kind=kind,
                complete=True,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="fixture_tool",
            )
            for idx, (name, kind) in enumerate(kinds.items(), 1)
        }
    )


def _run_direct(inputs: dict[str, Any]) -> dict[str, Any]:
    definition = REGISTRY[CALC_ID]
    input_type = cast(type[CalcInput], definition.input_type)
    return definition(input_type.model_validate(inputs), _meta(), TraceBuilder()).model_dump(mode="json")


def _setup_port(
    tmp_path: Path, raw_inputs: dict[str, Any]
) -> tuple[HarnessCalcPort, _RawSourceStore, dict[str, JsonValue], str]:
    clock = FixedClock(_START_MS, 1)
    ids = SeededIdSource(b"harness", clock)
    ws = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    store = _RawSourceStore(ws, HARNESS_KINDS, ids, clock)
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=clock.now(), duration_ms=0)
    who: dict[str, JsonValue] = {"unit": None, "entered_by": "engineer", "entered_at": "2026-11-01T00:00:00.000Z"}

    sel_id = store.put("harness.column_selection/1", raw_inputs["selection"], producer).result_id
    forces_id = store.put("forces.member_end/1", raw_inputs["forces"], producer).result_id
    sec_id = store.put("model.sections/1", raw_inputs["sections"], producer).result_id
    layouts_id = store.put(
        "basis.engineer_input/1",
        {"step": "column_design.layout", "fields": {"layout": {"value": raw_inputs["layouts"]} | who}},
        producer,
    ).result_id
    scope_id = store.put(
        "basis.engineer_input/1",
        {
            "step": "column_design.scope",
            "fields": {
                "scope": {
                    "value": {
                        "frames": ["C1", "C2"],
                        "combinations": raw_inputs["combinations"],
                        "special_seismic": False,
                    }
                }
                | who
            },
        },
        producer,
    ).result_id
    basis_id = store.put("basis.design_basis/1", raw_inputs["basis"], producer).result_id
    store.puts = 0

    args: dict[str, JsonValue] = {
        "selection": {"$ref": sel_id},
        "forces": {"$ref": forces_id},
        "sections": {"$ref": sec_id},
        "layouts": {"$ref": f"{layouts_id}#/fields/layout/value"},
        "combinations": {"$ref": f"{scope_id}#/fields/scope/value/combinations"},
        "basis": {"$ref": basis_id},
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
        basis_fields={CALC_ID: BASIS_PATHS},
    )
    return port, store, args, basis_id


def test_refusals(tmp_path: Path) -> None:
    """AC7: non-host_local/1 sign_convention and missing/unconfirmed basis give INVALID_ARGUMENT."""
    definition = REGISTRY[CALC_ID]
    assert definition.id == CALC_ID

    raw = _base_inputs()
    port, store, args, _ = _setup_port(tmp_path / "sign", raw)
    bad_forces_id = "res_01KCD000000000000000000099"
    valid_forces_ref = cast(dict[str, str], args["forces"])["$ref"]
    good_record = store.get(valid_forces_ref)
    bad_record = good_record.model_copy(update={"result_id": bad_forces_id, "payload": None})
    bad_payload = copy.deepcopy(raw["forces"])
    bad_payload["sign_convention"] = "global"
    store.inject_raw(bad_forces_id, bad_record, bad_payload)

    res = port.run(CALC_ID, args | {"forces": {"$ref": bad_forces_id}})
    assert isinstance(res, FailureEnvelope)
    assert res.error.code is ErrorCode.INVALID_ARGUMENT
    assert res.error.field == "forces.sign_convention"
    assert store.puts == 0

    for path in BASIS_PATHS:
        for mode in ("missing", "unconfirmed"):
            mutated = _base_inputs()
            if mode == "missing":
                mutated["basis"] = _basis(**{path: None})
            else:
                field = copy.deepcopy(mutated["basis"]["fields"][path])
                field["confirmed"] = False
                mutated["basis"] = _basis(**{path: field})
            sub_port, sub_store, sub_args, _ = _setup_port(tmp_path / f"{path}_{mode}", mutated)
            out = sub_port.run(CALC_ID, sub_args)
            assert isinstance(out, FailureEnvelope), (path, mode)
            assert out.error.code is ErrorCode.INVALID_ARGUMENT
            assert out.error.field == f"basis.fields.{path}"
            assert sub_store.puts == 0

            with pytest.raises(ContractError) as caught:
                _run_direct(mutated)
            detail = caught.value.detail
            why = "is missing (no default)" if mode == "missing" else "is not confirmed"
            assert (detail.code, detail.field) == (ErrorCode.INVALID_ARGUMENT, f"basis.fields.{path}")
            # Spec 0013 §4.4.2 / B-578: refuse missing or unconfirmed §4.7 A fields; exact why-text and hint.
            assert detail.message == f"basis field {path} {why}"
            assert detail.hint == f"set and confirm {path} in the design basis"


def test_axes_undeclared() -> None:
    """AC7: non-symmetric rectangular sections (b != h or unequal bar counts) get AXES_UNDECLARED (CW-G9)."""
    non_sym = _base_inputs()
    out = _run_direct(non_sym)
    assert [item["subject"]["id"] for item in out["items"][MAX_AXIAL_ID]] == ["C1", "C2"]
    assert [item["subject"]["id"] for item in out["items"][AXIAL_FLEXURE_ID]] == ["C1"]
    assert [item["subject"]["id"] for item in out["items"][REINF_LIMITS_ID]] == ["C1", "C2"]
    assert out["not_checked"] == [{"frame_id": "C2", "code": "AXES_UNDECLARED", "gap": "CW-G9"}]

    unequal_bars = _base_inputs()
    unequal_bars["selection"]["columns"] = [unequal_bars["selection"]["columns"][0]]
    unequal_bars["forces"]["rows"] = [unequal_bars["forces"]["rows"][0]]
    unequal_bars["layouts"]["sections"][0]["n_bars_b"] = 4
    out_bars = _run_direct(unequal_bars)
    assert [item["subject"]["id"] for item in out_bars["items"][MAX_AXIAL_ID]] == ["C1"]
    assert out_bars["items"][AXIAL_FLEXURE_ID] == []
    assert [item["subject"]["id"] for item in out_bars["items"][REINF_LIMITS_ID]] == ["C1"]
    assert out_bars["not_checked"] == [{"frame_id": "C1", "code": "AXES_UNDECLARED", "gap": "CW-G9"}]


def test_m2_only_symmetric_puts_sole_moment_in_mu() -> None:
    """AC6 / E3 (B-596, OQ-Q98): on a symmetric section, M2-only puts |M2| in Mu and Mu_other = 0."""
    # Hand derivation (spec 0013 §4.4.2 E3 as amended by B-596):
    # square C1, b=h=400, n_bars_b=n_bars_h=3 (symmetric); one row P=-800, M2=-15, M3=0.
    # |M3|=0 and |M2|=15 != 0 => Mu = |M2| = 15.0, Mu_other = 0 (not the fixed Mu=|M3|, Mu_other=|M2| map).
    m2_only = _base_inputs()
    m2_only["selection"]["columns"] = [m2_only["selection"]["columns"][0]]
    m2_only["forces"]["rows"] = [
        {
            "member": "C1",
            "case": {"case": "ULS1", "case_type": "load_combination", "step": None},
            "end": "j",
            "station_mm": 3000.0,
            "P_kN": -800.0,
            "V2_kN": 0.0,
            "V3_kN": 0.0,
            "T_kNm": 0.0,
            "M2_kNm": -15.0,
            "M3_kNm": 0.0,
        }
    ]
    m2_only["sections"]["frame_sections"] = [m2_only["sections"]["frame_sections"][0]]
    m2_only["layouts"]["sections"] = [m2_only["layouts"]["sections"][0]]
    out = _run_direct(m2_only)
    items = out["items"][AXIAL_FLEXURE_ID]
    assert len(items) == 1
    assert items[0]["inputs"]["Mu_kNm"] == 15.0
    assert items[0]["inputs"]["Mu_other_kNm"] == 0.0
    assert items[0]["inputs"]["Pu_kN"] == 800.0
    assert out["not_checked"] == []


def test_items_validate_against_checks(tmp_path: Path) -> None:
    """Plan 0013 T3: every emitted item validates against its aci318_14 CheckInputs model under require_refs=True."""
    port, store, args, basis_id = _setup_port(tmp_path, _base_inputs())
    envelope = port.run(CALC_ID, args)
    assert isinstance(envelope, SuccessEnvelope), envelope
    payload = store.payload(envelope.result_id)
    raw_items = cast(dict[str, list[dict[str, Any]]], payload["items"])

    pack_registry = Registry.discover()
    for check_id, spec_names in SPEC_FIELD_NAMES.items():
        check = pack_registry.get(check_id)
        inputs_cls = check.inputs
        assert isinstance(inputs_cls, type)
        assert issubclass(inputs_cls, ParamModel)
        model_fields = set(inputs_cls.model_fields)
        required_fields = {name for name, info in inputs_cls.model_fields.items() if info.is_required()}
        items = raw_items[check_id]
        assert isinstance(items, list), check_id
        assert items, check_id
        for item in items:
            item_inputs = cast(dict[str, Any], item["inputs"])
            emitted_names = set(item_inputs)
            assert required_fields <= emitted_names, (check_id, required_fields - emitted_names)
            assert emitted_names <= model_fields, (check_id, emitted_names - model_fields)
            assert emitted_names == spec_names, (check_id, emitted_names ^ spec_names)
            validated = validate_input(
                inputs_cls,
                item_inputs,
                source=store,
                current_revision=lambda _: None,
                policy=InputPolicy(require_refs=True),
            )
            ratio_prov = validated.inputs["ratio_limit"]
            assert isinstance(ratio_prov, RefInput)
            assert ratio_prov.ref == f"{basis_id}#/fields/limits.ratio_limit_ratio/value"
            if check_id != REINF_LIMITS_ID:
                for ref_name, basis_path in (
                    ("fc_MPa", "materials.concrete_fc_MPa"),
                    ("fy_MPa", "materials.rebar_fy_MPa"),
                    ("k_factor", "columns.effective_length_factor_ratio"),
                ):
                    prov = validated.inputs[ref_name]
                    assert isinstance(prov, RefInput)
                    assert prov.ref == f"{basis_id}#/fields/{basis_path}/value"
            for name, prov in validated.inputs.items():
                if name not in {"fc_MPa", "fy_MPa", "k_factor", "ratio_limit"}:
                    assert isinstance(prov, LiteralInput), (check_id, name)


def test_registration_describe_and_trace(tmp_path: Path) -> None:
    """Registration metadata, describe ref rules, and E3-E5 trace steps matching every emitted literal."""
    definition = REGISTRY[CALC_ID]
    assert definition is column_demands
    assert (definition.version, definition.output_kind, definition.verification) == (
        1,
        "harness.column_check_items/1",
        "draft",
    )
    assert definition.method_source == "eng-harness spec 0013 §4.4.2 (E1 to E6)"
    assert BASIS_FIELDS == BASIS_PATHS

    port, _, _, _ = _setup_port(tmp_path, _base_inputs())
    info = port.describe(CALC_ID)
    assert info.basis_fields == BASIS_PATHS
    assert {name: sorted(rule.kinds) for name, rule in info.ref_rules.items()} == {
        "selection": ["harness.column_selection/1"],
        "forces": ["forces.member_end/1"],
        "sections": ["model.sections/1"],
        "layouts": ["basis.engineer_input/1"],
        "combinations": ["basis.engineer_input/1"],
        "basis": ["basis.design_basis/1"],
    }

    trace = TraceBuilder()
    meta = _meta()
    out = column_demands(DemandsInput.model_validate(_base_inputs()), meta, trace).model_dump(mode="json")
    built = trace.build(definition, _DIGEST)
    assert [(c.name, c.cited.value, c.cited.unit) for c in built.constants] == [
        ("c_half", 2, "1"),
        ("c_corner", 4, "1"),
    ]
    basis_id = meta.refs["basis"].result_id
    inputs = {i.name: (i.value, i.unit, i.ref) for i in built.inputs}
    assert inputs == {
        "selection": (2, None, meta.refs["selection"].result_id),
        "forces": (2, None, meta.refs["forces"].result_id),
        "sections": (2, None, meta.refs["sections"].result_id),
        "layouts": (2, None, meta.refs["layouts"].result_id),
        "combinations": (1, None, meta.refs["combinations"].result_id),
        "materials_concrete_fc_MPa": (30.0, "MPa", f"{basis_id}#/fields/materials.concrete_fc_MPa"),
        "materials_rebar_fy_MPa": (420.0, "MPa", f"{basis_id}#/fields/materials.rebar_fy_MPa"),
        "columns_effective_length_factor_ratio": (
            1.0,
            "1",
            f"{basis_id}#/fields/columns.effective_length_factor_ratio",
        ),
        "limits_ratio_limit_ratio": (1.0, "1", f"{basis_id}#/fields/limits.ratio_limit_ratio"),
    }
    steps = {s.name: (s.value, s.unit, s.source) for s in built.steps}
    assert steps["col_0_b_mm"] == (400.0, "mm", "spec 0013 4.4.2 E5")
    assert steps["col_0_Ag_mm2"] == (160000.0, "mm2", "spec 0013 4.4.2 E5")
    assert steps["col_0_Ast_mm2"] == (4000.0, "mm2", "spec 0013 4.4.2 E5")
    assert steps["col_0_lu_mm"] == (3000.0, "mm", "spec 0013 4.4.2 E4")
    assert steps["col_0_transverse_kind"] == ("tied", None, "spec 0013 4.4.2 E5")
    assert steps["col_0_row_0_Pu_kN"] == (900.0, "kN", "spec 0013 4.4.2 E3")
    assert steps["col_0_row_0_Mu_kNm"] == (40.0, "kN.m", "spec 0013 4.4.2 E3")
    assert steps["col_0_row_0_Mu_other_kNm"] == (0.0, "kN.m", "spec 0013 4.4.2 E3")
    assert steps["max_axial_strength_items"] == (2, None, "spec 0013 4.4.2 E2, E6")
    assert steps["axial_flexure_uniaxial_items"] == (1, None, "spec 0013 4.4.2 E3, E6")
    assert steps["longitudinal_reinforcement_limits_items"] == (2, None, "spec 0013 4.4.2 E5, E6")
    assert steps["not_checked"] == (1, None, "spec 0013 4.4.2 E2, E3, E6")
    assert built.outputs == [
        "max_axial_strength_items",
        "axial_flexure_uniaxial_items",
        "longitudinal_reinforcement_limits_items",
        "not_checked",
    ]
    step_values = {s.name: s.value for s in built.steps}
    af_item = out["items"][AXIAL_FLEXURE_ID][0]["inputs"]
    for key, val in af_item.items():
        if not isinstance(val, dict):
            col_step = step_values.get(f"col_0_{key}")
            row_step = step_values.get(f"col_0_row_0_{key}")
            assert val in (col_step, row_step), key


@pytest.mark.parametrize(
    ("bad_value", "fragment"),
    [
        ("30", "is not a finite number"),
        (True, "is not a finite number"),
        (0.0, "must be positive"),
        (-5.0, "must be positive"),
    ],
)
def test_basis_value_bounds_and_types(bad_value: Any, fragment: str) -> None:
    """Every §4.7 A basis field refuses non-numeric, boolean, zero and negative values."""
    for path in BASIS_PATHS:
        mutated = _base_inputs()
        field = copy.deepcopy(mutated["basis"]["fields"][path])
        field["value"] = bad_value
        mutated["basis"] = _basis(**{path: field})
        with pytest.raises(ContractError) as caught:
            _run_direct(mutated)
        detail = caught.value.detail
        assert (detail.code, detail.field) == (ErrorCode.INVALID_ARGUMENT, f"basis.fields.{path}")
        assert detail.message == f"basis field {path} {fragment}"
        assert detail.hint == f"set and confirm {path} in the design basis"


def test_layout_basis_values_conversion_and_errors() -> None:
    """Layout BasisValue fields resolve to literals (never $ref), trace once, and validate units/bounds."""
    data = _base_inputs()
    # Two columns sharing C40 layout with BasisValue A_bar (cm2) and d_prime (cm).
    data["selection"]["columns"] = [
        data["selection"]["columns"][0],
        data["selection"]["columns"][0] | {"frame_id": "C3"},
    ]
    data["forces"]["rows"] = [
        data["forces"]["rows"][0],
        data["forces"]["rows"][0] | {"member": "C3"},
    ]
    data["layouts"]["sections"] = [
        {
            "section": "C40",
            "transverse_kind": "tied",
            "n_bars_b": 3,
            "n_bars_h": 3,
            "A_bar": {"source": "basis", "path": "rebar.bar_area_cm2"},
            "d_prime": {"source": "basis", "path": "durability.cover_cm"},
        }
    ]
    data["basis"] = _basis(
        **{
            "rebar.bar_area_cm2": {"value": 4.5, "unit": "cm2", "source": _SRC, "confirmed": True, "citation": None},
            "durability.cover_cm": {"value": 5.0, "unit": "cm", "source": _SRC, "confirmed": True, "citation": None},
        }
    )
    trace = TraceBuilder()
    out = column_demands(DemandsInput.model_validate(data), _meta(), trace).model_dump(mode="json")
    af_inputs = out["items"][AXIAL_FLEXURE_ID][0]["inputs"]
    assert af_inputs["A_bar_mm2"] == 450.0
    assert af_inputs["d_prime_mm"] == 50.0
    assert type(af_inputs["A_bar_mm2"]) is float
    assert out["items"][MAX_AXIAL_ID][0]["inputs"]["Ast_mm2"] == 3600.0
    built = trace.build(REGISTRY[CALC_ID], _DIGEST)
    # Injective encoding: `_` -> `_u`, then `.` -> `_d` (review r2; `rebar.bar_area_cm2`).
    assert [i.name for i in built.inputs].count("basis_in_rebar_dbar_uarea_ucm2") == 1
    a_bar_input = next(i for i in built.inputs if i.name == "basis_in_rebar_dbar_uarea_ucm2")
    assert a_bar_input.unit == "cm2"
    cover_input = next(i for i in built.inputs if i.name == "basis_in_durability_dcover_ucm")
    assert cover_input.unit == "cm"
    a_bar_step = next(s for s in built.steps if s.name == "col_0_A_bar_mm2")
    assert list(a_bar_step.uses) == ["basis_in_rebar_dbar_uarea_ucm2"]

    # Missing/unconfirmed, wrong unit, non-numeric, and non-positive basis values in layout.
    missing = copy.deepcopy(data)
    missing["basis"] = _basis(
        **{"durability.cover_cm": {"value": 5.0, "unit": "cm", "source": _SRC, "confirmed": True, "citation": None}}
    )
    with pytest.raises(ContractError) as err_miss:
        _run_direct(missing)
    miss = err_miss.value.detail
    assert (miss.code, miss.field) == (ErrorCode.INVALID_ARGUMENT, "basis.fields.rebar.bar_area_cm2")
    assert miss.message == "basis field rebar.bar_area_cm2 is missing or not confirmed"
    assert miss.hint == "set and confirm rebar.bar_area_cm2 in the design basis"

    unconf = copy.deepcopy(data)
    unconf["basis"]["fields"]["rebar.bar_area_cm2"]["confirmed"] = False
    with pytest.raises(ContractError) as err_unconf:
        _run_direct(unconf)
    un = err_unconf.value.detail
    assert (un.code, un.field) == (ErrorCode.INVALID_ARGUMENT, "basis.fields.rebar.bar_area_cm2")
    assert un.message == "basis field rebar.bar_area_cm2 is missing or not confirmed"
    assert un.hint == "set and confirm rebar.bar_area_cm2 in the design basis"

    wrong_unit = copy.deepcopy(data)
    wrong_unit["basis"]["fields"]["rebar.bar_area_cm2"]["unit"] = "mm"
    with pytest.raises(ContractError) as err_unit:
        _run_direct(wrong_unit)
    unit_err = err_unit.value.detail
    assert (unit_err.code, unit_err.field) == (ErrorCode.UNIT_MISMATCH, "basis.fields.rebar.bar_area_cm2")
    assert unit_err.message == "basis field rebar.bar_area_cm2 must convert to mm2"
    assert unit_err.expected == {"unit": "mm2"}
    assert unit_err.received == "mm"
    assert unit_err.hint == "set and confirm rebar.bar_area_cm2 in the design basis"

    non_num = copy.deepcopy(data)
    non_num["basis"]["fields"]["rebar.bar_area_cm2"]["value"] = "4.5"
    with pytest.raises(ContractError) as err_num:
        _run_direct(non_num)
    num = err_num.value.detail
    assert (num.code, num.field) == (ErrorCode.INVALID_ARGUMENT, "basis.fields.rebar.bar_area_cm2")
    assert num.message == "basis field rebar.bar_area_cm2 is not a finite number"
    assert num.hint == "set and confirm rebar.bar_area_cm2 in the design basis"

    non_pos = copy.deepcopy(data)
    non_pos["basis"]["fields"]["rebar.bar_area_cm2"]["value"] = 0.0
    with pytest.raises(ContractError) as err_pos:
        _run_direct(non_pos)
    pos = err_pos.value.detail
    assert (pos.code, pos.field) == (ErrorCode.OUT_OF_RANGE, "basis.fields.rebar.bar_area_cm2")
    assert pos.message == "basis field rebar.bar_area_cm2 must be positive"
    assert pos.received == 0.0
    assert pos.hint == "set and confirm rebar.bar_area_cm2 in the design basis"


def test_layout_input_bounds_overflow_and_duplicate_sections() -> None:
    """Layout literal bounds, binary64 overflow/underflow, and duplicate sections are refused."""
    for bad in (0.0, -10.0):
        data = _base_inputs()
        data["layouts"]["sections"][0]["A_bar"]["value"] = bad
        with pytest.raises(ContractError) as caught:
            _run_direct(data)
        detail = caught.value.detail
        assert (detail.code, detail.field) == (ErrorCode.OUT_OF_RANGE, "layouts")
        assert detail.message == "layout value must be positive"
        assert detail.expected == {"exclusive_min": 0, "unit": "mm2"}
        assert detail.received == bad

    over = _base_inputs()
    over["sections"]["frame_sections"][0]["shape"] = {"type": "rectangular", "b_mm": 1e308, "h_mm": 1e308}
    with pytest.raises(ContractError) as err_over:
        _run_direct(over)
    over_detail = err_over.value.detail
    assert (over_detail.code, over_detail.field) == (ErrorCode.OUT_OF_RANGE, "layouts")
    assert over_detail.message == "gross area of C1 exceeds binary64 range"

    under = _base_inputs()
    under["layouts"]["sections"][0]["A_bar"]["value"] = 1e-325
    with pytest.raises(ContractError) as err_under:
        _run_direct(under)
    under_detail = err_under.value.detail
    assert (under_detail.code, under_detail.field) == (ErrorCode.OUT_OF_RANGE, "layouts")
    assert under_detail.message == "layout value must be positive"

    dup = _base_inputs()
    dup["layouts"]["sections"].append(copy.deepcopy(dup["layouts"]["sections"][0]))
    with pytest.raises(ValidationError, match="duplicate section"):
        ColumnLayout.model_validate(dup["layouts"])


def test_to_finite_float_refuses_zero_underflow_and_overflow() -> None:
    """§4.4.2 E5 layout quantities must be positive finite binary64 floats (helper of column_demands)."""
    with pytest.raises(ContractError) as zero_err:
        _to_finite_float(Fraction(0), "bar area of C1")
    zero = zero_err.value.detail
    assert (zero.code, zero.field) == (ErrorCode.OUT_OF_RANGE, "layouts")
    assert zero.message == "bar area of C1 cannot be represented as a positive float"

    with pytest.raises(ContractError) as tiny_err:
        _to_finite_float(Fraction(1, 10**400), "bar area of C1")
    tiny = tiny_err.value.detail
    assert (tiny.code, tiny.field) == (ErrorCode.OUT_OF_RANGE, "layouts")
    assert tiny.message == "bar area of C1 cannot be represented as a positive float"

    with pytest.raises(ContractError) as huge_err:
        _to_finite_float(Fraction(10**400), "gross area of C1")
    huge = huge_err.value.detail
    assert (huge.code, huge.field) == (ErrorCode.OUT_OF_RANGE, "layouts")
    assert huge.message == "gross area of C1 exceeds binary64 range"


def test_missing_refs_sections_spiral_sorting_and_zero_sign() -> None:
    """Missing refs, missing sections, spiral gap, -0.0 normalization, empty selection, and sorting."""
    inp = DemandsInput.model_validate(_base_inputs())
    full_meta = _meta()
    for missing_name in ("selection", "forces", "sections", "layouts", "combinations", "basis"):
        trimmed = InputMeta(refs={k: v for k, v in full_meta.refs.items() if k != missing_name})
        with pytest.raises(ContractError) as caught:
            column_demands(inp, trimmed, TraceBuilder())
        assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, missing_name)
        assert caught.value.detail.message == f"input {missing_name} must be a record reference"

    no_sec = _base_inputs()
    no_sec["sections"]["frame_sections"] = [no_sec["sections"]["frame_sections"][1]]
    with pytest.raises(ContractError) as err_sec:
        _run_direct(no_sec)
    assert (err_sec.value.detail.code, err_sec.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, "sections")

    spiral = _base_inputs()
    spiral["layouts"]["sections"][0]["transverse_kind"] = "spiral"
    with pytest.raises(NotImplementedGap) as err_spiral:
        _run_direct(spiral)
    assert err_spiral.value.evidence == ("CK Q4",)

    # Unsorted columns, -0.0 axial, multiple stations & envelope steps, plus both AXES_UNDECLARED and FORCES_MISSING.
    combo = _base_inputs()
    combo["combinations"] = ["ULS1", "ULS2"]
    combo["selection"]["columns"] = list(reversed(combo["selection"]["columns"]))
    combo["forces"]["rows"] = [
        {
            "member": "C1",
            "case": {"case": "ULS1", "case_type": "load_combination", "step": "Min"},
            "end": "j",
            "station_mm": 3000.0,
            "P_kN": -0.0,
            "V2_kN": 0.0,
            "V3_kN": 0.0,
            "T_kNm": 0.0,
            "M2_kNm": -0.0,
            "M3_kNm": -0.0,
        },
        {
            "member": "C1",
            "case": {"case": "ULS1", "case_type": "load_combination", "step": "Max"},
            "end": "j",
            "station_mm": 3000.0,
            "P_kN": -100.0,
            "V2_kN": 0.0,
            "V3_kN": 0.0,
            "T_kNm": 0.0,
            "M2_kNm": 0.0,
            "M3_kNm": 10.0,
        },
        {
            "member": "C1",
            "case": {"case": "ULS2", "case_type": "load_combination", "step": None},
            "end": "i",
            "station_mm": 0.0,
            "P_kN": -200.0,
            "V2_kN": 0.0,
            "V3_kN": 0.0,
            "T_kNm": 0.0,
            "M2_kNm": 0.0,
            "M3_kNm": 15.0,
        },
    ]
    out_combo = _run_direct(combo)
    ma_items = out_combo["items"][MAX_AXIAL_ID]
    got_ma = [
        (i["subject"]["id"], i["subject"]["case"], i["subject"]["station_mm"], i["inputs"]["Pu_kN"]) for i in ma_items
    ]
    assert got_ma == [
        ("C1", "ULS1", 3000.0, 100.0),
        ("C1", "ULS1", 3000.0, 0.0),
        ("C1", "ULS2", 0.0, 200.0),
    ]
    zero_pu = ma_items[1]["inputs"]["Pu_kN"]
    assert math.copysign(1.0, zero_pu) == 1.0
    assert out_combo["not_checked"] == [
        {"frame_id": "C2", "code": "AXES_UNDECLARED", "gap": "CW-G9"},
        {"frame_id": "C2", "code": "FORCES_MISSING", "gap": None},
    ]

    empty = _base_inputs()
    empty["selection"] = _selection([])
    empty["selection"]["status"] = "FAIL"
    out_empty = _run_direct(empty)
    assert out_empty == {
        "items": {MAX_AXIAL_ID: [], AXIAL_FLEXURE_ID: [], REINF_LIMITS_ID: []},
        "not_checked": [],
    }


def test_ratio_limit_above_contract_default_is_refused(tmp_path: Path) -> None:
    """limits.ratio_limit_ratio above Verdict.ratio_limit default is INVALID_ARGUMENT with zero writes."""
    from eng_contract.verdicts import Verdict

    ceiling = Verdict.model_fields["ratio_limit"].default
    assert isinstance(ceiling, float)
    above = ceiling + 0.0001
    mutated = _base_inputs()
    field = copy.deepcopy(mutated["basis"]["fields"]["limits.ratio_limit_ratio"])
    field["value"] = above
    mutated["basis"] = _basis(**{"limits.ratio_limit_ratio": field})

    with pytest.raises(ContractError) as caught:
        _run_direct(mutated)
    detail = caught.value.detail
    assert (detail.code, detail.field) == (ErrorCode.INVALID_ARGUMENT, "basis.fields.limits.ratio_limit_ratio")
    assert detail.message == "basis field limits.ratio_limit_ratio must not exceed the contract default"
    assert detail.hint == "set and confirm limits.ratio_limit_ratio in the design basis"

    port, store, args, _ = _setup_port(tmp_path, mutated)
    out = port.run(CALC_ID, args)
    assert isinstance(out, FailureEnvelope)
    assert out.error.code is ErrorCode.INVALID_ARGUMENT
    assert out.error.field == "basis.fields.limits.ratio_limit_ratio"
    assert store.puts == 0


def test_layout_basis_path_does_not_collide_with_trace_step(tmp_path: Path) -> None:
    """A layout basis path such as col_0.d_prime_mm keeps a reserved input name and the conversion step."""
    data = _base_inputs()
    data["selection"]["columns"] = [data["selection"]["columns"][0]]
    data["forces"]["rows"] = [data["forces"]["rows"][0]]
    data["layouts"]["sections"] = [
        {
            "section": "C40",
            "transverse_kind": "tied",
            "n_bars_b": 3,
            "n_bars_h": 3,
            "A_bar": {"source": "input", "value": 500.0, "unit": "mm2"},
            "d_prime": {"source": "basis", "path": "col_0.d_prime_mm"},
        }
    ]
    data["basis"] = _basis(
        **{
            "col_0.d_prime_mm": {
                "value": 50.0,
                "unit": "mm",
                "source": _SRC,
                "confirmed": True,
                "citation": None,
            }
        }
    )
    port, store, args, basis_id = _setup_port(tmp_path, data)
    out = port.run(CALC_ID, args)
    assert isinstance(out, SuccessEnvelope), out
    payload = store.payload(out.result_id)
    trace = cast(dict[str, Any], payload["trace"])
    input_names = {row["name"] for row in cast(list[dict[str, Any]], trace["inputs"])}
    step_names = {row["name"] for row in cast(list[dict[str, Any]], trace["steps"])}
    # Injective encoding of `col_0.d_prime_mm`: `_` -> `_u`, then `.` -> `_d`.
    assert "basis_in_col_u0_dd_uprime_umm" in input_names
    assert "col_0_d_prime_mm" in step_names
    basis_in = next(
        row for row in cast(list[dict[str, Any]], trace["inputs"]) if row["name"] == "basis_in_col_u0_dd_uprime_umm"
    )
    assert basis_in["ref"] == f"{basis_id}#/fields/col_0.d_prime_mm"
    assert basis_in["value"] == 50.0
    step = next(row for row in cast(list[dict[str, Any]], trace["steps"]) if row["name"] == "col_0_d_prime_mm")
    assert step["value"] == 50.0
    assert "basis_in_col_u0_dd_uprime_umm" in step["uses"]


def test_layout_basis_paths_with_underscore_and_dot_do_not_collide(tmp_path: Path) -> None:
    """`layout.values.bar` and `layout_values.bar` keep distinct basis_in_* names (injective `_u` then `_d`)."""
    data = _base_inputs()
    data["selection"]["columns"] = [data["selection"]["columns"][0]]
    data["forces"]["rows"] = [data["forces"]["rows"][0]]
    data["layouts"]["sections"] = [
        {
            "section": "C40",
            "transverse_kind": "tied",
            "n_bars_b": 3,
            "n_bars_h": 3,
            "A_bar": {"source": "basis", "path": "layout.values.bar"},
            "d_prime": {"source": "basis", "path": "layout_values.bar"},
        }
    ]
    data["basis"] = _basis(
        **{
            "layout.values.bar": {
                "value": 500.0,
                "unit": "mm2",
                "source": _SRC,
                "confirmed": True,
                "citation": None,
            },
            "layout_values.bar": {
                "value": 50.0,
                "unit": "mm",
                "source": _SRC,
                "confirmed": True,
                "citation": None,
            },
        }
    )
    port, store, args, basis_id = _setup_port(tmp_path, data)
    out = port.run(CALC_ID, args)
    assert isinstance(out, SuccessEnvelope), out
    payload = store.payload(out.result_id)
    af_inputs = cast(dict[str, list[dict[str, Any]]], payload["items"])[AXIAL_FLEXURE_ID][0]["inputs"]
    # Hand: A_bar already in mm2; d_prime already in mm (no unit scale).
    assert af_inputs["A_bar_mm2"] == 500.0
    assert af_inputs["d_prime_mm"] == 50.0

    trace = cast(dict[str, Any], payload["trace"])
    inputs_by_name = {row["name"]: row for row in cast(list[dict[str, Any]], trace["inputs"])}
    # layout.values.bar -> basis_in_layout_dvalues_dbar; layout_values.bar -> basis_in_layout_uvalues_dbar.
    bar_name = "basis_in_layout_dvalues_dbar"
    cover_name = "basis_in_layout_uvalues_dbar"
    assert bar_name in inputs_by_name
    assert cover_name in inputs_by_name
    assert bar_name != cover_name
    assert inputs_by_name[bar_name]["ref"] == f"{basis_id}#/fields/layout.values.bar"
    assert inputs_by_name[bar_name]["value"] == 500.0
    assert inputs_by_name[cover_name]["ref"] == f"{basis_id}#/fields/layout_values.bar"
    assert inputs_by_name[cover_name]["value"] == 50.0

    steps_by_name = {row["name"]: row for row in cast(list[dict[str, Any]], trace["steps"])}
    a_bar_step = steps_by_name["col_0_A_bar_mm2"]
    d_prime_step = steps_by_name["col_0_d_prime_mm"]
    assert a_bar_step["value"] == 500.0
    assert list(a_bar_step["uses"]) == [bar_name]
    assert d_prime_step["value"] == 50.0
    assert list(d_prime_step["uses"]) == [cover_name]
