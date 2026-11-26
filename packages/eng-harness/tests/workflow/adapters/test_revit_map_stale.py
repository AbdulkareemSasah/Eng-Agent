"""AC29: a stored frame-element map becomes stale after a Revit edit."""

from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from eng_contract.envelope import SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.store import LocationClass, Workspace
from fakes.ports import FakeApprovalPort, FakeInputPort
from pydantic import JsonValue
from workflows.chain import chain

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness.adapters._toolport import ModelBinder
from eng_harness.adapters.revit import revit_allowlist
from eng_harness.basis import StoreBasisPort
from eng_harness.block import Registry
from eng_harness.calcs import REGISTRY
from eng_harness.engine import Engine, EnginePorts, EngineSettings, PermissionMode, RunRequest
from eng_harness.ports import RunClass

from .test_revit_toolport import _SET, _Rig


def test_map_stale_after_edit(tmp_path: Path) -> None:
    async def scenario() -> None:
        rig = _Rig(tmp_path)
        rig.freeze_basis()
        store = rig.store
        provenance = rig._provenance()
        fields: dict[str, JsonValue] = {
            name: {
                "value": 0,
                "unit": "mm",
                "confirmed": True,
                "source": f"engineer:test@{rig.clock.now()}",
                "citation": None,
            }
            for name in ("compare.length_mm", "mapping.offset_x_mm", "mapping.offset_y_mm", "mapping.offset_z_mm")
        }  # Exact coincidence of the synthetic placements, with aligned origins.
        basis = store.put("basis.design_basis/1", {"template": None, "fields": fields}, provenance)
        approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
        calc = HarnessCalcPort(
            REGISTRY, approvals, store, CalcSettings(max_items=100), RunClass.TRIAL, rig.clock, rig.ids
        )
        port = rig.ports.tool_port
        async with rig.ports:
            model, _ = await rig.working_copy()
            binder = cast(ModelBinder, rig.ports.host_port)
            binding = await binder.binding("revit", model, revit_allowlist().descriptor(_SET))
            assert binding.host is not None
            source = provenance.model_copy(update={"host": binding.host})
            payload: dict[str, Any] = store.payload(rig.put_structure())
            structure = store.put("harness.revit_structure/1", payload, source)
            row = payload["elements"][0]
            frame = {"kind": "column", "section": row["type_name"], "i": row["i"], "j": row["j"], "rotation_deg": 0}
            frames = store.put("model.frame_placements/1", {"frames": [{**frame, "id": "F1"}]}, provenance)
            elements = store.put("model.frame_placements/1", {"frames": [{**frame, "id": row["unique_id"]}]}, source)
            mapped = calc.run("harness.frame_element_map", {
                "frames": {"$ref": frames.result_id}, "elements": {"$ref": elements.result_id},
                "structure": {"$ref": structure.result_id}, "basis": {"$ref": basis.result_id},
            })  # fmt: skip
            assert isinstance(mapped, SuccessEnvelope), mapped
            args = rig.set_args(model, structure.result_id, rig.put_sections())
            args["element_ids"] = [{"$ref": f"{mapped.result_id}#/pairs/0"}]
            await port.preview(_SET, args)
            edit = await port.call(_SET, args, op_id="edit", model=model)
            assert isinstance(edit, SuccessEnvelope), edit
            assert binder.revision(binding.host.model_id) == binding.host.model_revision + 1
            workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
            engine = Engine(
                workspace, Registry([chain([(_SET, args)])]),
                EnginePorts(
                    port, rig.ports.host_port, calc, StoreBasisPort(store), FakeApprovalPort(), FakeInputPort(),
                ),
                store, EngineSettings(), rig.clock, rig.ids,
            )  # fmt: skip
            request = RunRequest(
                workflow="chain", input={}, basis_ref=basis.result_id,
                mode=PermissionMode.APPROVE_EACH_WRITE, run_class=RunClass.TRIAL,
            )  # fmt: skip
            with pytest.raises(ContractError) as refused:
                await engine.start(request)
            assert refused.value.detail.code is ErrorCode.REF_STALE
            assert len(rig.calls(_SET)) == 1

    anyio.run(scenario)
