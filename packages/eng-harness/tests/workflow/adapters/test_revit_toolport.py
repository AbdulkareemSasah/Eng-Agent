"""Assembled Revit ports against the synthetic MCP host (plan 0011 T14b; spec 0011 §4.8, §4.12).

Phase 1, tests first: `build_ports` gains the Revit dispatch, `RevitHostPort` gains `binding()` and
`revision()` with its `check_model` wiring, and `adapters/revit/_toolport.py` carries the write tool
port. None exists yet, so every test fails on the missing feature. Fake-host workflow tests: real
engine ports over real synthetic-server processes (POSIX; Linux CI). Written against the IDEA port
test of plan 0014 T9a and the CSI wiring tests.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Envelope, FailureEnvelope, Provenance, RefInput, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.refs import RefRule, resolve_ref
from eng_contract.store import LocationClass, ResultStore, Workspace
from eng_contract.units import convert
from mcp.types import CallToolResult
from pydantic import JsonValue

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters import build_ports
from eng_harness.adapters._toolport import ModelBinder
from eng_harness.adapters.revit import revit_allowlist
from eng_harness.adapters.revit._session_ops import RevitHostPort
from eng_harness.journal import EventType, JournalWriter
from eng_harness.servers import CallEffect, ServersConfig

from . import _revit_edit_helpers as helpers

_SET = "revit_set_element_parameter_values"
_SET_TYPE = "revit_set_type_parameter_values"
_SET_GUID = "revit_set_parameter_value_by_guid"
_DUPLICATE = "revit_duplicate_family_type"
_CHANGE_TYPE = "revit_change_element_type"
_DETAILS = "revit_get_element_details"
_METADATA = "revit_get_model_metadata"
_WRITE_RESULT = "harness.revit_write_result/1"
_RUN_OUTPUT = RefRule(kinds=frozenset({"harness.run_output/1"}))
# Synthetic engineer inputs, never product defaults (the CSI wiring rig says the same).
_TOLERANCE = 0.001
_VALUE_MM = 450.0
_NEW_TYPE_NAME = "C450x450"
_SHA = "a" * 64
# Journal RUN_STARTED header (mirrors tests/fixtures/report_run.HEADER so the file stays self-contained).
_HEADER: dict[str, Any] = {
    "run_id": "run_x", "workflow": "w", "block": {"name": "b", "version": "1", "code_sha256": _SHA},
    "input_sha256": _SHA, "mode": "work_on_copy", "run_class": "trial",
    "engine_version": "1", "contract_version": "eng-contract/1", "settings_sha256": _SHA, "servers": [],
    "always_ask": [],
}  # fmt: skip


class _Rig:
    """Assembled Revit ports over real synthetic-server processes, with a result store and journal."""

    def __init__(
        self,
        root: Path,
        *,
        faults: list[dict[str, Any]] | None = None,
        seed: Mapping[str, Any] | None = None,
        write_timeout_s: int | None = None,
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.control = root / "control.json"
        self.run = root / "run"
        self.run.mkdir(exist_ok=True)
        config = helpers.revit_config(root, self.control, seed=seed, faults=faults)
        if write_timeout_s is not None:
            config = _short_write_timeout(config, write_timeout_s)
        self.clock = FixedClock(1_700_000_000_000, 1)
        self.ids = SeededIdSource(b"revit-toolport", self.clock)
        workspace = Workspace(root=root / "ws", classification=LocationClass.LOCAL)
        self.store: ResultStore = ResultStore(workspace, HARNESS_KINDS, self.ids, self.clock)
        self.original = root / "original.rvt"
        if not self.original.exists():
            self.original.write_bytes(b"synthetic revit model")
        self.launcher = helpers.RecordingLauncher()
        # Fails with ConfigError while the Revit dispatch is missing (the feature under test).
        self.ports = build_ports(
            config,
            workspace,
            self.store,
            self.run,
            self.clock,
            self.ids,
            files={"m": self.original},
            lock_dir=root / "locks",
            launcher=self.launcher,
        )

    def freeze_basis(self) -> None:
        """Frozen synthetic engineer basis: the read-back tolerance behind a RUN_STARTED header."""
        provenance = self._provenance()
        fields: dict[str, JsonValue] = {
            "checks.readback_relative_tolerance_ratio": {
                "value": _TOLERANCE,
                "unit": "1",
                "source": f"engineer:test@{self.clock.now()}",
                "confirmed": True,
                "citation": None,
            }
        }
        basis = self.store.put("basis.design_basis/1", {"template": None, "fields": fields}, provenance)
        inputs = self.store.put("harness.run_input/1", {"value": {}}, provenance)
        writer = JournalWriter(self.run, self.store, self.clock, self.ids)
        try:
            writer.append(
                EventType.RUN_STARTED,
                {
                    **_HEADER,
                    "run_id": self.run.name,
                    "input_ref": inputs.result_id,
                    "basis_ref": basis.result_id,
                },
            )
        finally:
            writer.close()

    def _provenance(self) -> Provenance:
        return Provenance(
            tool="test/revit-toolport", tool_version="1", inputs={}, started_at=self.clock.now(), duration_ms=0
        )

    def put_structure(self, *, unique_id: str = "col-3001") -> str:
        """`harness.revit_structure/1` mirroring the default fake seed (element 3001, type 2001)."""
        role_values: dict[str, JsonValue] = {
            "section_b": {"value": 304.8, "unit": "mm"},
            "section_h": {"value": 304.8, "unit": "mm"},
        }
        row: JsonValue = {
            "unique_id": unique_id,
            "element_id": 3001,
            "category": "column",
            "family": helpers.FAMILY,
            "type_id": 2001,
            "type_name": "C300x300",
            "level_id": 100,
            "level_name": "Level 1",
            "location_kind": "curve",
            "i": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0},
            "j": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 3000.0},
            "rotation_deg": None,
            "parameters": role_values,
        }
        types: JsonValue = [
            {
                "type_id": 2001,
                "family": helpers.FAMILY,
                "name": "C300x300",
                "instance_ids": [3001],
                "parameters": role_values,
            }
        ]
        record = self.store.put("harness.revit_structure/1", {"elements": [row], "types": types}, self._provenance())
        return record.result_id

    def put_sections(self) -> str:
        """`model.sections/1` holding the length the value references below resolve to."""
        payload: dict[str, JsonValue] = {
            "frame_sections": [
                {
                    "name": "S1",
                    "material": "M1",
                    "shape": {"type": "rectangular", "b_mm": _VALUE_MM, "h_mm": 500.0},
                }
            ],
            "area_sections": [],
        }
        return self.store.put("model.sections/1", payload, self._provenance()).result_id

    def set_args(self, model: str, structure: str, sections: str) -> dict[str, JsonValue]:
        """Caller arguments of an instance length write (§4.8): row and length references, literal name."""
        return {
            "model": model,
            "element_ids": [{"$ref": f"{structure}#/elements/0"}],
            "parameter_name": "b",
            "value_mm": {"$ref": f"{sections}#/frame_sections/0/shape/b_mm"},
        }

    async def working_copy(self) -> tuple[str, Path]:
        model = await self.ports.host_port.working_copy("m", self.run / "copies")
        return model, self.ports.host_port.model_files(model)[0]

    def calls(self, tool: str) -> list[dict[str, Any]]:
        """Control-log calls of `tool`; this client awaits each call in turn, so the log is ordered."""
        data = json.loads(self.control.read_text(encoding="utf-8"))
        logged = data.get("calls", [])
        assert isinstance(logged, list)
        return [entry for entry in logged if isinstance(entry, dict) and entry.get("tool") == tool]

    def payload(self, envelope: Envelope | None, kind: str) -> dict[str, Any]:
        assert isinstance(envelope, SuccessEnvelope), envelope
        assert envelope.kind == kind
        stored: dict[str, Any] = self.store.payload(envelope.result_id)
        return stored

    def ref_value(self, ref: str) -> Any:
        return resolve_ref(ref, _RUN_OUTPUT, self.store, lambda _: None).value

    def ledger_entry(self, op_id: str) -> dict[str, Any]:
        """The durable pre-send entry of `op_id` as raw JSON (the Revit target is adapter-specific)."""
        ledger = self.run / "adapter" / "ops.jsonl"
        entries = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        found = [item for item in entries if item["op_id"] == op_id]
        assert len(found) == 1
        assert isinstance(found[0], dict)
        return found[0]

    def observe_write(
        self, monkeypatch: pytest.MonkeyPatch, tool: str, op_id: str, args: dict[str, JsonValue], *, bound: Path
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """Capture each send of `tool` after asserting its pre-send evidence is already durable (§4.12)."""
        seen: list[tuple[dict[str, Any], dict[str, Any]]] = []
        send = self.ports.servers.call

        async def call(
            server: str,
            role: str,
            name: str,
            arguments: Mapping[str, Any],
            effect: CallEffect,
        ) -> CallToolResult:
            if name == tool:
                entry = self.ledger_entry(op_id)
                assert entry["tool"] == tool
                assert entry["args_sha256"] == payload_sha256(args)
                values = _target_values(entry["target"])
                assert helpers.PIPE in values
                assert str(bound) in values
                ref = entry["pre_image_ref"]
                assert isinstance(ref, str)
                assert ref.endswith("#/value/observed")
                sent = self.ref_value(ref.removesuffix("/observed") + "/sent")
                assert sent == dict(arguments)
                seen.append((entry, dict(arguments)))
            return await send(server, role, name, arguments, effect)

        monkeypatch.setattr(self.ports.servers, "call", call)
        return seen


def _target_values(node: Any) -> list[Any]:
    """Every scalar of a ledger target, whatever keys the adapter-specific target uses."""
    if isinstance(node, dict):
        return [leaf for value in node.values() for leaf in _target_values(value)]
    if isinstance(node, list):
        return [leaf for item in node for leaf in _target_values(item)]
    return [node]


def _short_write_timeout(config: ServersConfig, timeout_s: int) -> ServersConfig:
    """Write-role timeout below the fault's withhold delay (pattern of test_revit_reconcile)."""
    section = config.servers["revit"]
    roles = dict(section.roles)
    roles["write"] = roles["write"].model_copy(update={"call_timeout_s": timeout_s})
    return config.model_copy(
        update={
            "servers": {
                **config.servers,
                "revit": section.model_copy(update={"roles": roles, "client_grace_s": 2}),
            }
        }
    )


def test_build_ports_dispatches_revit(tmp_path: Path) -> None:
    """§4.12 ports table: `build_ports` assembles the Revit ports; describe, binder, reconcile support."""

    async def body() -> None:
        rig = _Rig(tmp_path / "dispatch")
        port = rig.ports.tool_port
        async with rig.ports:
            read = await port.describe(_DETAILS)
            assert (read.name, read.effect, read.host_key, read.attended) == (_DETAILS, "read", "revit", False)
            setter = await port.describe(_SET)
            assert (setter.name, setter.effect, setter.host_key) == (_SET, "write", "revit")
            assert setter.attended is True
            assert setter.model_param == "model"
            assert "value_mm" in setter.engineering_params
            assign = await port.describe(_CHANGE_TYPE)
            assert (assign.effect, assign.host_key, assign.attended) == ("write", "revit", True)
            assert assign.engineering_params == ()
            for tool in ("revit_switch_target", "revit_batch_execute"):
                with pytest.raises(ContractError) as raised:
                    await port.describe(tool)
                assert raised.value.detail.code is ErrorCode.INVALID_ARGUMENT
                assert raised.value.detail.field == "tool"
            for tool in (_SET, _SET_TYPE, _SET_GUID, _DUPLICATE, _CHANGE_TYPE):
                assert port.supports_reconcile(tool) is True
            for tool in (_DETAILS, _METADATA):
                assert port.supports_reconcile(tool) is False
            binder = cast(ModelBinder, rig.ports.host_port)
            descriptor = revit_allowlist().descriptor(_SET)
            with pytest.raises(ContractError) as missing:
                await binder.binding("revit", "m@copy", descriptor)
            assert missing.value.detail.code is ErrorCode.PRECONDITION_FAILED
            assert missing.value.detail.precondition is Precondition.model_open
            with pytest.raises(ContractError):
                await binder.binding("other", "m@copy", descriptor)
            assert binder.revision("mdl_" + "0" * 26) is None
            model, copy = await rig.working_copy()
            assert model == "m@copy"
            bound = await binder.binding("revit", model, descriptor)
            assert bound.target.product == "revit"
            assert bound.target.pid in {process.pid for process in rig.launcher.started}
            assert bound.host is not None
            assert bound.host.program == "revit"
            assert bound.host.version == "2026"
            host = cast(RevitHostPort, rig.ports.host_port)
            assert bound.host.model_id == host.identity_store.resolve(copy).model_id
            assert (await binder.binding("revit", None, descriptor)).host == bound.host
            held = await rig.ports.host_port.locate(model)
            assert held is not None
            assert held.pid is None
            assert rig.ports.host_port.model_files(model) == (copy,)

    anyio.run(body)


def test_attended_write_preview_call_and_read_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC12, AC14, AC17, AC18, §4.8 caller shape and §4.12 evidence: preview, attended call, read-back, R7."""

    async def body() -> None:
        rig = _Rig(tmp_path / "main")
        rig.freeze_basis()
        port = rig.ports.tool_port
        structure = rig.put_structure()
        sections = rig.put_sections()
        async with rig.ports:
            early: dict[str, JsonValue] = rig.set_args("m@copy", structure, sections)
            with pytest.raises(ContractError) as closed:
                await port.preview(_SET, early)
            assert closed.value.detail.precondition is Precondition.model_open
            model, copy = await rig.working_copy()
            args = rig.set_args(model, structure, sections)
            preview = await port.preview(_SET, args)
            assert len(preview.items) == 1
            item = preview.items[0]
            assert item.id == _SET
            assert model in item.label
            assert preview.diff_ref is None
            assert len(preview.models) == 1
            target = preview.models[0]
            assert (target if isinstance(target, str) else target.model_key) == model
            assert len(item.refs) == 2
            canonical: dict[str, Any] = rig.store.payload(item.refs[0].ref)
            assert canonical["value"]["model"] == model
            assert canonical["value"]["parameter_name"] == "b"
            pre = item.refs[1].ref
            assert pre.endswith("#/value/observed")
            before = rig.ref_value(pre)["by_target"]["3001"]["b"]
            assert before == pytest.approx(convert(helpers.B_FT, "ft", "mm"))
            assert rig.calls(_SET) == []
            assert not (rig.run / "adapter" / "ops.jsonl").exists()
            # A length needs value_mm; value is refused (scalar length validation, §4.8).
            literal_value: dict[str, JsonValue] = {**args, "value": "450", "value_type": "double"}
            del literal_value["value_mm"]
            failed = await port.call(_SET, literal_value, op_id="op-literal-value", model=model)
            assert isinstance(failed, FailureEnvelope)
            assert failed.error.code is ErrorCode.INVALID_ARGUMENT
            # An engineering quantity as a literal is refused (references required).
            literal_mm: dict[str, JsonValue] = {**args, "value_mm": _VALUE_MM}
            failed = await port.call(_SET, literal_mm, op_id="op-literal-mm", model=model)
            assert isinstance(failed, FailureEnvelope)
            assert failed.error.code is ErrorCode.INVALID_ARGUMENT
            # An element reference of the wrong kind is refused (row selection, §4.8).
            wrong_kind: dict[str, JsonValue] = {**args, "element_ids": [{"$ref": f"{sections}#/frame_sections/0"}]}
            failed = await port.call(_SET, wrong_kind, op_id="op-wrong-kind", model=model)
            assert isinstance(failed, FailureEnvelope)
            assert failed.error.code is ErrorCode.REF_KIND_MISMATCH
            # An element reference to a missing result is refused.
            missing: dict[str, JsonValue] = {
                **args,
                "element_ids": [{"$ref": "res_00000000000000000000000000#/elements/0"}],
            }
            failed = await port.call(_SET, missing, op_id="op-missing-ref", model=model)
            assert isinstance(failed, FailureEnvelope)
            assert failed.error.code is ErrorCode.REF_NOT_FOUND
            # AC12: a mismatched uniqueId is CONFLICT and no write is sent.
            impostor = rig.put_structure(unique_id="col-impostor")
            mismatch: dict[str, JsonValue] = {**args, "element_ids": [{"$ref": f"{impostor}#/elements/0"}]}
            failed = await port.call(_SET, mismatch, op_id="op-mismatch", model=model)
            assert isinstance(failed, FailureEnvelope)
            assert failed.error.code is ErrorCode.CONFLICT
            assert rig.calls(_SET) == []
            # The attended call: host mapping, pre-send evidence, stored write result.
            writes = rig.observe_write(monkeypatch, _SET, "op-set-b", args, bound=copy)
            answer = await port.call(_SET, args, op_id="op-set-b", model=model)
            assert isinstance(answer, SuccessEnvelope), answer
            assert answer.kind == _WRITE_RESULT
            written = rig.payload(answer, _WRITE_RESULT)
            assert written["tool"] == _SET
            assert written["op_id"] == "op-set-b"
            targets = written["targets"]
            assert isinstance(targets, list)
            assert targets
            first = targets[0]
            assert isinstance(first, dict)
            assert first["element_id"] == 3001
            assert len(writes) == 1
            wire = writes[0][1]
            mapping = {key: wire[key] for key in ("elementIds", "parameterName", "value", "valueType")}
            assert mapping == {"elementIds": [3001], "parameterName": "b", "value": "450.0", "valueType": "double"}
            assert "confirm" not in wire
            record = rig.store.get(answer.result_id)
            value_input = record.producer.inputs["value_mm"]
            assert isinstance(value_input, RefInput)
            assert value_input.ref == f"{sections}#/frame_sections/0/shape/b_mm"
            back = await port.read_back(_SET, args)
            seen = rig.payload(back, "harness.run_output/1")["value"]["observed"]["by_target"]["3001"]["b"]
            assert seen == pytest.approx(_VALUE_MM)
            # R7 new-type flow (spec 0013 R7, Q11): duplicate, assign, then set values.
            dup_args: dict[str, JsonValue] = {
                "model": model,
                "source_type_id": {"$ref": f"{structure}#/types/0/type_id"},
                "new_type_name": _NEW_TYPE_NAME,
            }
            dup_writes = rig.observe_write(monkeypatch, _DUPLICATE, "op-dup", dup_args, bound=copy)
            duplicated = await port.call(_DUPLICATE, dup_args, op_id="op-dup", model=model)
            assert isinstance(duplicated, SuccessEnvelope), duplicated
            dup_payload = rig.payload(duplicated, _WRITE_RESULT)
            new_type = dup_payload["targets"][0]["type_id"]
            assert isinstance(new_type, int)
            assert len(dup_writes) == 1
            dup_wire = dup_writes[0][1]
            assert {key: dup_wire[key] for key in ("source_type_id", "new_type_name")} == {
                "source_type_id": "2001",
                "new_type_name": _NEW_TYPE_NAME,
            }
            assert "type_parameter_overrides" not in dup_wire
            type_ref: dict[str, JsonValue] = {"$ref": f"{duplicated.result_id}#/targets/0/type_id"}
            assign_args: dict[str, JsonValue] = {
                "model": model,
                "element_ids": [{"$ref": f"{structure}#/elements/0"}],
                "type_id": type_ref,
            }
            assign_writes = rig.observe_write(monkeypatch, _CHANGE_TYPE, "op-assign", assign_args, bound=copy)
            assigned = await port.call(_CHANGE_TYPE, assign_args, op_id="op-assign", model=model)
            assert isinstance(assigned, SuccessEnvelope), assigned
            assert len(assign_writes) == 1
            assign_wire = assign_writes[0][1]
            assert assign_wire["elementIds"] == [3001]
            assert assign_wire["typeId"] == new_type
            type_args: dict[str, JsonValue] = {
                "model": model,
                "type_ids": [type_ref],
                "expected_instances": [],
                "parameter_name": "b",
                "value_mm": {"$ref": f"{sections}#/frame_sections/0/shape/b_mm"},
            }
            failed = await port.call(_SET_TYPE, type_args, op_id="op-empty-expected", model=model)
            assert isinstance(failed, FailureEnvelope)
            assert failed.error.code is ErrorCode.INVALID_ARGUMENT
            type_args["expected_instances"] = [3001, 3002]
            failed = await port.call(_SET_TYPE, type_args, op_id="op-wrong-expected", model=model)
            assert isinstance(failed, FailureEnvelope)
            assert failed.error.code is ErrorCode.CONFLICT
            assert rig.calls(_SET_TYPE) == []
            type_args["expected_instances"] = [3001]
            type_writes = rig.observe_write(monkeypatch, _SET_TYPE, "op-set-type", type_args, bound=copy)
            typed = await port.call(_SET_TYPE, type_args, op_id="op-set-type", model=model)
            assert isinstance(typed, SuccessEnvelope), typed
            assert len(type_writes) == 1
            type_wire = type_writes[0][1]
            assert {key: type_wire[key] for key in ("parameterName", "value", "valueType", "typeIds")} == {
                "parameterName": "b",
                "value": "450.0",
                "valueType": "double",
                "typeIds": [new_type],
            }
            assert "expected_instances" not in type_wire
            typed_back = await port.read_back(_SET_TYPE, type_args)
            typed_seen = rig.payload(typed_back, "harness.run_output/1")["value"]["observed"]
            assert typed_seen["by_target"][str(new_type)]["b"] == pytest.approx(_VALUE_MM)

        waiting = _Rig(tmp_path / "active", faults=[{"fault": "other_document_active", "tool": _SET}])
        waiting.freeze_basis()
        async with waiting.ports:
            # AC13: the first write flips the active document at the host; the second is refused pre-send.
            w_model, _ = await waiting.working_copy()
            w_args = waiting.set_args(w_model, waiting.put_structure(), waiting.put_sections())
            first = await waiting.ports.tool_port.call(_SET, w_args, op_id="op-first", model=w_model)
            assert isinstance(first, FailureEnvelope)
            assert first.error.code is ErrorCode.INVALID_ARGUMENT
            second = await waiting.ports.tool_port.call(_SET, w_args, op_id="op-second", model=w_model)
            assert isinstance(second, FailureEnvelope)
            assert second.error.code is ErrorCode.PRECONDITION_FAILED
            assert second.error.precondition is Precondition.model_open
            assert len(waiting.calls(_SET)) == 1

        declined_rig = _Rig(tmp_path / "declined", faults=[{"fault": "dialog_declined", "tool": _SET}])
        declined_rig.freeze_basis()
        async with declined_rig.ports:
            # AC18: a declined dialog is CONFIRMATION_REQUIRED, certain, never retried, ledgered pre-send.
            d_model, _ = await declined_rig.working_copy()
            d_args = declined_rig.set_args(d_model, declined_rig.put_structure(), declined_rig.put_sections())
            refused = await declined_rig.ports.tool_port.call(_SET, d_args, op_id="op-declined", model=d_model)
            assert isinstance(refused, FailureEnvelope)
            assert refused.error.code is ErrorCode.CONFIRMATION_REQUIRED
            assert "declined in Revit" in refused.error.message
            assert refused.error.retryable is False
            assert len(declined_rig.calls(_SET)) == 1
            assert declined_rig.ledger_entry("op-declined")["tool"] == _SET

    anyio.run(body)


def test_check_model_and_read_units_through_host_port(tmp_path: Path) -> None:
    """AC19 and §4.6: the host port checks tool-port writes with the frozen tolerance; units declared."""

    async def body() -> None:
        rig = _Rig(tmp_path / "clean")
        rig.freeze_basis()
        async with rig.ports:
            model, _ = await rig.working_copy()
            args = rig.set_args(model, rig.put_structure(), rig.put_sections())
            answer = await rig.ports.tool_port.call(_SET, args, op_id="op-check", model=model)
            assert isinstance(answer, SuccessEnvelope), answer
            check = await rig.ports.host_port.check_model(model)
            report = rig.payload(check, "issues.model_check/1")
            assert report["summary"]["clean"] is True
            codes = {(issue["severity"], issue["code"]) for issue in report["issues"]}
            assert ("info", "MODEL_UNSAVED") in codes
            assert not [code for (severity, code) in codes if severity == "error"]
            following = await rig.ports.host_port.check_model(model)
            cleared = rig.payload(following, "issues.model_check/1")
            assert cleared["summary"]["clean"] is True
            assert {(issue["severity"], issue["code"]) for issue in cleared["issues"]} == {("info", "MODEL_UNSAVED")}
            held = await rig.ports.host_port.locate(model)
            assert held is not None
            units = await rig.ports.host_port.read_units(model, held.instance_id)
            assert (units.loaded, units.ok, units.present, units.expected) == (
                True,
                True,
                "revit_schema/1",
                "revit_schema/1",
            )
            absent = await rig.ports.host_port.read_units(model, "inst_" + "0" * 26)
            assert (absent.loaded, absent.ok, absent.present, absent.expected) == (
                False,
                True,
                None,
                "revit_schema/1",
            )

        faulty = _Rig(tmp_path / "unchecked", faults=[{"fault": "commit_unchecked", "tool": _SET}])
        faulty.freeze_basis()
        async with faulty.ports:
            f_model, _ = await faulty.working_copy()
            f_args = faulty.set_args(f_model, faulty.put_structure(), faulty.put_sections())
            applied = await faulty.ports.tool_port.call(_SET, f_args, op_id="op-unchecked", model=f_model)
            assert isinstance(applied, SuccessEnvelope), applied
            found = faulty.payload(await faulty.ports.host_port.check_model(f_model), "issues.model_check/1")
            assert found["summary"]["clean"] is False
            assert ("error", "READBACK_MISMATCH") in {(issue["severity"], issue["code"]) for issue in found["issues"]}

        bare = _Rig(tmp_path / "bare")
        async with bare.ports:
            # No frozen basis supplies no tolerance: quantities are READBACK_UNAVAILABLE, never defaulted.
            b_model, _ = await bare.working_copy()
            b_args = bare.set_args(b_model, bare.put_structure(), bare.put_sections())
            written = await bare.ports.tool_port.call(_SET, b_args, op_id="op-bare", model=b_model)
            assert isinstance(written, SuccessEnvelope), written
            missing = bare.payload(await bare.ports.host_port.check_model(b_model), "issues.model_check/1")
            assert ("error", "READBACK_UNAVAILABLE") in {
                (issue["severity"], issue["code"]) for issue in missing["issues"]
            }

    anyio.run(body)


def test_reconcile_lost_write_through_tool_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC20, §4.10 and §4.12 (Q10): a lost write reconciles applied from the persisted request."""

    async def body() -> None:
        rig = _Rig(
            tmp_path / "lost",
            faults=[{"fault": "retry_token_consumed", "tool": _SET, "seconds": 20.0}],
            write_timeout_s=8,
        )
        rig.freeze_basis()
        port = rig.ports.tool_port
        async with rig.ports:
            model, copy = await rig.working_copy()
            args = rig.set_args(model, rig.put_structure(), rig.put_sections())
            writes = rig.observe_write(monkeypatch, _SET, "op-lost", args, bound=copy)
            lost = await port.call(_SET, args, op_id="op-lost", model=model)
            assert isinstance(lost, FailureEnvelope), lost
            assert lost.error.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
            assert lost.error.op_id == "op-lost"
            assert len(writes) == 1
            assert port.supports_reconcile(_SET) is True
            tampered: dict[str, JsonValue] = {**args, "parameter_name": "h"}
            changed = await port.reconcile(_SET, tampered, "op-lost")
            assert changed.outcome == "unknown"
            assert len(rig.calls(_SET)) == 1
            decision = await port.reconcile(_SET, args, "op-lost")
            assert decision.outcome == "applied"
            assert decision.missing == ()
            assert len(decision.evidence) == 1
            stored: dict[str, Any] = rig.store.payload(decision.evidence[0].ref)
            assert stored["value"]["requested"] == {"b": _VALUE_MM}
            assert stored["value"]["observed"]["3001"]["b"] == pytest.approx(_VALUE_MM)
            assert stored["value"]["pre_image_known"] is True
            assert len(rig.calls(_SET)) == 1
            repeat = await port.call(_SET, args, op_id="op-after", model=model)
            assert isinstance(repeat, SuccessEnvelope), repeat

    anyio.run(body)
