"""Unit and contract tests of `harness.column_demands` (plan 0013 T3; spec 0013 AC6, AC7, §4.4.2)."""

import copy
import math
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.envelope import FailureEnvelope, LiteralInput, Provenance, RefInput, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.params import InputPolicy, ParamModel, validate_input
from eng_contract.records import ResultRecord
from eng_contract.store import LocationClass, ResultStore, Workspace
from pydantic import JsonValue
from structural_codes.pack import Registry

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import CalcInput, InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
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
            assert (caught.value.detail.code, caught.value.detail.field) == (
                ErrorCode.INVALID_ARGUMENT,
                f"basis.fields.{path}",
            )


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


