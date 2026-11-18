"""CSI tool saves record the save and carry the post-save revision (plan 0007 T13b; spec 0007 4.10, AC43).

Production `build_ports` wired over the synthetic CSI fake server, as the edit-cycle stand does. A tool save
(`csi_save_model` in place or `as_new_revision`) and `csi_open_revision` record the save on the host port before
storing the result envelope, so `provenance.host.model_revision` equals the next `model_state` revision, no
`MODEL_CHANGED_OUTSIDE` is raised for the harness's own save, writes under the same approval keep their chain, and a
resume after a tool save meets no `host_state_mismatch`.
"""

from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import SuccessEnvelope
from eng_contract.errors import WarningCode
from fakes.ports import FakeApprovalPort, FakeCalcPort, FakeInputPort
from fakes.sasaah_csi.wiring import Rig, rig
from pydantic import BaseModel, ConfigDict
from workflows.chain import ChainInput, ChainOutput

from eng_harness.adapters.csi import csi_allowlist
from eng_harness.basis import StoreBasisPort
from eng_harness.block import Registry, WorkflowDef, workflow
from eng_harness.ctx import ApprovalKind, Preview, PreviewItem
from eng_harness.engine import Engine, EnginePorts, EngineSettings, PermissionMode, RunRequest, RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalAnswer, InputAnswer, RunClass
from eng_harness.servers import CallEffect


class ContinueInput(BaseModel):
    """Engineer continuation input used to pause the workflow after a tool save."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    note: str


def _engine(
    r: Rig,
    ports: Any,
    flow: WorkflowDef[ChainInput, ChainOutput],
    *,
    approvals: FakeApprovalPort | None = None,
    inputs: FakeInputPort | None = None,
) -> Engine:
    return Engine(
        r.workspace,
        Registry([flow]),
        EnginePorts(
            tool=ports.tool_port,
            host=ports.host_port,
            calc=FakeCalcPort(RunClass.TRIAL, []),
            basis=StoreBasisPort(r.store),
            approvals=approvals or FakeApprovalPort(),
            inputs=inputs or FakeInputPort(),
        ),
        r.store,
        EngineSettings(),
        r.clock,
        r.ids,
    )


def _request(r: Rig, flow_name: str) -> RunRequest:
    return RunRequest(
        workflow=flow_name,
        input={},
        basis_ref=r.basis_ref,
        run_class=RunClass.TRIAL,
        mode=PermissionMode.WORK_ON_COPY,
        run_id=r.run_id,
    )


def test_save_result_carries_post_save_revision(tmp_path: Path) -> None:
    """AC43: tool saves and `csi_open_revision` carry the post-step revision and leave no outside-edit warning."""
    r = rig(tmp_path)

    async def body() -> None:
        async with r.ports() as p:
            opened = await p.tool_port.call("csi_open_model", {"model": "m"}, op_id="open", model="m")
            assert isinstance(opened, SuccessEnvelope), opened
            held = await p.host_port.locate("m")
            assert held is not None
            before = await p.host_port.model_state("m", held.instance_id)
            assert before.revision is not None
            assert p.host_port.take_warnings() == []

            saved_rev = await p.tool_port.call(
                "csi_save_model", {"model": "m", "as_new_revision": True}, op_id="save-rev", model="m"
            )
            assert isinstance(saved_rev, SuccessEnvelope), saved_rev
            assert saved_rev.provenance.host is not None
            after_rev = await p.host_port.model_state("m", held.instance_id)
            assert saved_rev.provenance.host.model_revision == after_rev.revision == before.revision + 1
            assert r.store.get(saved_rev.result_id).producer.host == saved_rev.provenance.host
            assert p.host_port.take_warnings() == []

            edited = await p.tool_port.call(
                "csi_assign_frame_section",
                {"model": "m", "frame": "F1", "section": "C40"},
                op_id="edit-1",
                model="m",
            )
            assert isinstance(edited, SuccessEnvelope), edited

            saved_inplace = await p.tool_port.call("csi_save_model", {"model": "m"}, op_id="save-in", model="m")
            assert isinstance(saved_inplace, SuccessEnvelope), saved_inplace
            assert saved_inplace.provenance.host is not None
            after_inplace = await p.host_port.model_state("m", held.instance_id)
            assert saved_inplace.provenance.host.model_revision == after_inplace.revision == after_rev.revision + 1
            assert r.store.get(saved_inplace.result_id).producer.host == saved_inplace.provenance.host
            assert p.host_port.take_warnings() == []

            saved_file = saved_rev.summary["saved_file"]
            assert isinstance(saved_file, dict)
            reopened = await p.tool_port.call(
                "csi_open_revision",
                {"model": "m", "revision": saved_file["name"]},
                op_id="reopen-1",
                model="m",
            )
            assert isinstance(reopened, SuccessEnvelope), reopened
            assert reopened.provenance.host is not None
            after_reopen = await p.host_port.model_state("m", held.instance_id)
            assert reopened.provenance.host.model_revision == after_reopen.revision == after_inplace.revision + 1
            assert r.store.get(reopened.result_id).producer.host == reopened.provenance.host
            assert p.host_port.take_warnings() == []

            for _ in range(2):  # distinct file bytes from earlier saved revisions of the same model
                await p.servers.call(
                    "csi",
                    "main",
                    "csi_save_model",
                    {"target": {"product": "ETABS", "pid": held.pid}, "confirm": True},
                    CallEffect.WRITE,
                )
            outside = await p.host_port.model_state("m", held.instance_id)
            assert outside.revision is not None
            assert outside.revision > after_reopen.revision
            assert p.host_port.take_warnings() == [("m", WarningCode.MODEL_CHANGED_OUTSIDE)]

    anyio.run(body)


def test_save_then_write_under_one_approval(tmp_path: Path) -> None:
    """AC43: saving `as_new_revision` then writing under one approval completes without `ApprovalVoid`."""
    r = rig(tmp_path)

    @workflow(
        name="save_then_write",
        version=1,
        description="Approve a revision save and a write together, then run both.",
        copy_on_open=True,
        min_server_builds={"csi": csi_allowlist().sasaah_commit},
    )
    async def save_then_write(ctx: Any, inp: ChainInput) -> ChainOutput:
        await ctx.tool("csi_open_model", {"model": "m"})
        state = await ctx.tool("csi_read_model_state", {"model": "m"})
        preview = Preview(
            items=(
                PreviewItem(id="revision", label="Save revision", refs=(state.ref,)),
                PreviewItem(id="a1", label="Assign F1", refs=(state.ref,)),
            ),
            models=("m",),
            diff_ref=None,
        )
        approval = await ctx.approve("Apply edit cycle", preview, kind=ApprovalKind.CHANGE_SET)
        saved = await ctx.tool(
            "csi_save_model", {"model": "m", "as_new_revision": True}, under=approval, item="revision"
        )
        edited = await ctx.tool(
            "csi_assign_frame_section", {"model": "m", "frame": "F1", "section": "C40"}, under=approval, item="a1"
        )
        return ChainOutput(refs=[saved.ref.ref, edited.ref.ref])

    async def body() -> None:
        approvals = FakeApprovalPort()
        async with r.ports() as p:
            engine = _engine(r, p, save_then_write, approvals=approvals)
            paused = await engine.start(_request(r, "save_then_write"))
            assert paused.status is RunStatus.PAUSED, paused
            shown = approvals.presented[-1]
            approvals.script(
                shown.request_id,
                ApprovalAnswer(
                    request_id=shown.request_id,
                    shown_sha256=shown.shown_sha256,
                    decision="approve",
                    by="engineer:test",
                ),
            )
            outcome = await engine.resume(r.run_id)
            assert outcome.status is RunStatus.COMPLETED, outcome
            events = r.events()
            assert not any(e.type is EventType.STEP_FAILED for e in events)
            revisions = [
                e.payload for e in events if isinstance(e.payload, ev.ModelSaved) and e.payload.role == "revision"
            ]
            assert len(revisions) == 1
            assert revisions[0].revision == p.host_port.revision(revisions[0].model_id) == 1
            assert isinstance(outcome.output, ChainOutput)
            assert len(outcome.output.refs) == 2
            saved_host = r.store.get(outcome.output.refs[0]).producer.host
            assert saved_host is not None
            assert saved_host.model_revision == revisions[0].revision
            assert p.host_port.take_warnings() == []

    anyio.run(body)


@pytest.mark.parametrize("as_new_revision", [True, False])
def test_resume_after_tool_save_has_no_mismatch(tmp_path: Path, as_new_revision: bool) -> None:
    """AC43: a pause after a CSI tool save resumes without `host_state_mismatch`."""
    r = rig(tmp_path)

    @workflow(
        name="save_then_pause",
        version=1,
        description="Save through the tool port, pause on ask, then resume.",
        copy_on_open=True,
        min_server_builds={"csi": csi_allowlist().sasaah_commit},
    )
    async def save_then_pause(ctx: Any, inp: ChainInput) -> ChainOutput:
        await ctx.tool("csi_open_model", {"model": "m"})
        saved = await ctx.tool("csi_save_model", {"model": "m", "as_new_revision": as_new_revision})
        await ctx.ask(ContinueInput, title="Continue after save")
        return ChainOutput(refs=[saved.ref.ref])

    async def body() -> None:
        inputs = FakeInputPort()
        async with r.ports() as p:
            paused = await _engine(r, p, save_then_pause, inputs=inputs).start(_request(r, "save_then_pause"))
            assert paused.status is RunStatus.PAUSED, paused
        asked = inputs.presented[-1]
        resumed_inputs = FakeInputPort()
        resumed_inputs.script(
            asked.request_id,
            InputAnswer(
                request_id=asked.request_id,
                shown_sha256=asked.fields_schema_sha256,
                values={"note": "continue"},
                by="engineer:test",
            ),
        )
        async with r.ports() as resumed_ports:
            done = await _engine(r, resumed_ports, save_then_pause, inputs=resumed_inputs).resume(r.run_id)
            assert done.status is RunStatus.COMPLETED, done
            assert all(req.kind != "engine.host_state" for req in resumed_inputs.presented)
            assert not any(e.type is EventType.RUN_ESCALATED for e in r.events())

    anyio.run(body)
