"""CSI tool saves record the save and carry the post-save revision (plan 0007 T13b; spec 0007 4.10, AC43).

Production `build_ports` wired over the synthetic CSI fake server, as the edit-cycle stand does. A tool save
(`csi_save_model` in place or `as_new_revision`) and `csi_open_revision` record the save on the host port before
storing the result envelope, so `provenance.host.model_revision` equals the next `model_state` revision, no
`MODEL_CHANGED_OUTSIDE` is raised for the harness's own save, writes under the same approval keep their chain, and a
resume after a tool save meets no `host_state_mismatch`.
"""

import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import FailureEnvelope, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode, WarningCode
from fakes.ports import FakeApprovalPort, FakeCalcPort, FakeInputPort
from fakes.sasaah_csi.wiring import Rig, rig
from pydantic import BaseModel, ConfigDict
from workflows.chain import ChainInput, ChainOutput

from eng_harness.adapters._toolport import SettlementError
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


def test_save_result_carries_post_save_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
            assert before.model_id is not None
            assert p.host_port.take_warnings() == []

            real_snapshot = p.tool_port._revisions.snapshot
            boundary: list[tuple[int | None, str | None, str]] = []

            def checked_snapshot(working: Path, target: Path) -> Any:
                rev_before = p.host_port.revision(before.model_id)
                state_before = p.host_port._states.get(before.model_id)
                saved_file = real_snapshot(working, target)
                boundary.append(
                    (rev_before, None if state_before is None else state_before.file_sha256, saved_file.sha256)
                )
                return saved_file

            monkeypatch.setattr(p.tool_port._revisions, "snapshot", checked_snapshot)

            saved_rev = await p.tool_port.call(
                "csi_save_model", {"model": "m", "as_new_revision": True}, op_id="save-rev", model="m"
            )
            assert isinstance(saved_rev, SuccessEnvelope), saved_rev
            assert saved_rev.provenance.host is not None
            saved_file = saved_rev.summary["saved_file"]
            assert isinstance(saved_file, dict)
            assert boundary == [(before.revision + 1, saved_file["sha256"], saved_file["sha256"])]
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

            edited_again = await p.tool_port.call(
                "csi_assign_frame_section",
                {"model": "m", "frame": "F1", "section": "C30"},
                op_id="edit-2",
                model="m",
            )
            assert isinstance(edited_again, SuccessEnvelope), edited_again
            saved_inplace_2 = await p.tool_port.call("csi_save_model", {"model": "m"}, op_id="save-in-2", model="m")
            assert isinstance(saved_inplace_2, SuccessEnvelope), saved_inplace_2
            assert saved_inplace_2.provenance.host is not None
            await p.servers.call(
                "csi",
                "main",
                "csi_assign_frame_section",
                {"target": {"product": "ETABS", "pid": held.pid}, "name": "F1", "section": "C40", "confirm": True},
                CallEffect.WRITE,
            )
            outside_fp = await p.host_port.model_state("m", held.instance_id)
            assert outside_fp.revision == saved_inplace_2.provenance.host.model_revision + 1
            assert p.host_port.take_warnings() == [("m", WarningCode.MODEL_CHANGED_OUTSIDE)]

            reopened = await p.tool_port.call(
                "csi_open_revision",
                {"model": "m", "revision": saved_file["name"]},
                op_id="reopen-1",
                model="m",
            )
            assert isinstance(reopened, SuccessEnvelope), reopened
            assert reopened.provenance.host is not None
            after_reopen = await p.host_port.model_state("m", held.instance_id)
            assert reopened.provenance.host.model_revision == after_reopen.revision == outside_fp.revision + 1
            assert r.store.get(reopened.result_id).producer.host == reopened.provenance.host
            assert p.host_port.take_warnings() == []

            for _ in range(3):  # distinct file bytes from earlier saved revisions of the same model
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


def test_conflicting_model_keys_send_no_write(tmp_path: Path) -> None:
    """Conflicting `model=` and `args['model']` are rejected with `INVALID_ARGUMENT` before any host write."""
    r = rig(tmp_path)

    async def body() -> None:
        async with r.ports() as p:
            opened = await p.tool_port.call("csi_open_model", {"model": "m"}, op_id="open", model="m")
            assert isinstance(opened, SuccessEnvelope), opened
            held = await p.host_port.locate("m")
            assert held is not None
            saved_rev = await p.tool_port.call(
                "csi_save_model", {"model": "m", "as_new_revision": True}, op_id="save-rev", model="m"
            )
            assert isinstance(saved_rev, SuccessEnvelope), saved_rev
            saved_file = saved_rev.summary["saved_file"]
            assert isinstance(saved_file, dict)
            copies_before = sorted(path.name for path in (r.run_dir / "copies").iterdir())
            saves_before = len(r.calls("csi_save_model"))
            opens_before = len(r.calls("csi_open_model"))
            assert saved_rev.provenance.host is not None
            model_id = saved_rev.provenance.host.model_id
            assert p.host_port.revision(model_id) == 1

            for op_id, tool, args in (
                ("bad-in", "csi_save_model", {"model": "other"}),
                ("bad-rev", "csi_save_model", {"model": "other", "as_new_revision": True}),
                ("bad-open", "csi_open_revision", {"model": "other", "revision": saved_file["name"]}),
            ):
                refused = await p.tool_port.call(tool, args, op_id=op_id, model="m")
                assert isinstance(refused, FailureEnvelope), refused
                assert refused.error.code is ErrorCode.INVALID_ARGUMENT
                assert refused.error.field == "model"

            assert len(r.calls("csi_save_model")) == saves_before
            assert len(r.calls("csi_open_model")) == opens_before
            assert sorted(path.name for path in (r.run_dir / "copies").iterdir()) == copies_before
            assert p.host_port.revision(model_id) == 1

            by_args = await p.tool_port.call("csi_save_model", {"model": "m"}, op_id="save-args-only", model=None)
            assert isinstance(by_args, SuccessEnvelope), by_args
            assert by_args.provenance.host is not None
            assert by_args.provenance.host.model_revision == 2
            assert p.host_port.revision(model_id) == 2

    anyio.run(body)


def _seed_control(
    control: Path, *, seed: dict[str, Any] | None = None, faults: list[dict[str, Any]] | None = None
) -> None:
    data = json.loads(control.read_text())
    if seed is not None:
        data.setdefault("seed", {}).update(seed)
    if faults is not None:
        data["faults"] = faults
    control.write_text(json.dumps(data))


def test_settlement_failure_leaves_write_in_flight_and_keeps_host_refusal_ordinary(tmp_path: Path) -> None:
    """Post-save settlement errors escape as `SettlementError` (in flight); host refusals stay ordinary failures."""
    truncated = {"tables": {"Joint Assignments - Restraints": [{"UniqueName": f"J{n}"} for n in range(2001)]}}

    async def body() -> None:
        # 1. Direct port: settlement failure (LIMIT_EXCEEDED) raises SettlementError with cause and stores no envelope.
        direct_rig = rig(tmp_path / "direct")
        _seed_control(direct_rig.control, seed=truncated)
        async with direct_rig.ports() as p:
            opened = await p.tool_port.call("csi_open_model", {"model": "m"}, op_id="open", model="m")
            assert isinstance(opened, SuccessEnvelope), opened
            before_files = set(direct_rig.workspace.results_dir.rglob("*.json"))
            with pytest.raises(SettlementError) as settled:
                await p.tool_port.call("csi_save_model", {"model": "m"}, op_id="save-trunc", model="m")
            assert isinstance(settled.value.__cause__, ContractError)
            assert settled.value.__cause__.detail.code is ErrorCode.LIMIT_EXCEEDED
            after_files = set(direct_rig.workspace.results_dir.rglob("*.json"))
            assert after_files == before_files
            assert len(direct_rig.calls("csi_save_model")) == 1
            assert opened.provenance.host is not None
            assert p.host_port.revision(opened.provenance.host.model_id) == 0

            # Host refusal stays on the ordinary failure path (FailureEnvelope).
            _seed_control(direct_rig.control, faults=[{"fault": "com_worker_recycled", "tool": "csi_save_model"}])
            refused = await p.tool_port.call("csi_save_model", {"model": "m"}, op_id="save-refused", model="m")
            assert isinstance(refused, FailureEnvelope), refused
            assert refused.error.code is ErrorCode.TIMEOUT_NO_EFFECT

        # 2. Engine: settlement failure leaves the write in flight for engineer decision, sends no second save.
        @workflow(
            name="save_only",
            version=1,
            description="Open and save through the tool port.",
            copy_on_open=True,
            min_server_builds={"csi": csi_allowlist().sasaah_commit},
        )
        async def save_only(ctx: Any, inp: ChainInput) -> ChainOutput:
            await ctx.tool("csi_open_model", {"model": "m"})
            saved = await ctx.tool("csi_save_model", {"model": "m"})
            return ChainOutput(refs=[saved.ref.ref])

        engine_rig = rig(tmp_path / "engine-settled")
        inputs = FakeInputPort()
        async with engine_rig.ports() as p:
            orig_call = p.tool_port.call

            async def seed_before_save(tool: str, args: Any, *, op_id: str, model: str | None) -> Any:
                if tool == "csi_save_model":
                    data = json.loads(engine_rig.control.read_text())
                    data["model"]["tables"].update(truncated["tables"])
                    engine_rig.control.write_text(json.dumps(data))
                return await orig_call(tool, args, op_id=op_id, model=model)

            p.tool_port.call = seed_before_save
            outcome = await _engine(engine_rig, p, save_only, inputs=inputs).start(_request(engine_rig, "save_only"))
            assert outcome.status is RunStatus.NEEDS_ENGINEER, outcome
            assert outcome.escalation is not None
            assert outcome.escalation.reason == "needs_reconciliation"
            assert len(inputs.presented) == 1
            assert inputs.presented[0].kind == "engine.in_flight"
            assert "csi_save_model" in inputs.presented[0].title
            assert len(engine_rig.calls("csi_save_model")) == 1
            events = engine_rig.events()
            started = [
                e for e in events if isinstance(e.payload, ev.StepStarted) and e.payload.name == "csi_save_model"
            ]
            assert len(started) == 1
            save_path = started[0].path
            save_events = [
                e
                for e in events
                if isinstance(e.payload, (ev.StepStarted, ev.StepCompleted, ev.StepFailed)) and e.path == save_path
            ]
            assert [e.type for e in save_events] == [EventType.STEP_STARTED]
            assert not any(isinstance(e.payload, ev.ModelSaved) and e.path == save_path for e in events)
            result_tools = [
                engine_rig.store.get(path.stem).producer.tool
                for path in engine_rig.workspace.results_dir.rglob("*.json")
            ]
            assert "sasaah-csi-mcp/csi_save_model" not in result_tools

        # 3. Engine: host refusal closes the step as failed (ordinary failure path, no engineer in-flight decision).
        refused_rig = rig(tmp_path / "engine-refused")
        _seed_control(refused_rig.control, faults=[{"fault": "com_worker_recycled", "tool": "csi_save_model"}])
        refused_inputs = FakeInputPort()
        async with refused_rig.ports() as p:
            failed = await _engine(refused_rig, p, save_only, inputs=refused_inputs).start(
                _request(refused_rig, "save_only")
            )
            assert failed.status is RunStatus.NEEDS_ENGINEER, failed
            assert failed.escalation is not None
            assert failed.escalation.reason == "unhandled_error"
            assert refused_inputs.presented == []
            assert any(isinstance(e.payload, ev.StepFailed) and e.path == save_path for e in refused_rig.events())

    anyio.run(body)
