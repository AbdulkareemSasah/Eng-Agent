"""AC22: cut the engine around Revit dispatch, then resume against the persisted fake document."""

import json
import multiprocessing
import os
import traceback
from contextlib import closing
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import anyio
import pytest
from eng_contract.envelope import FailureEnvelope
from eng_contract.ids import SeededIdSource
from eng_contract.refs import Ref, parse_ref
from eng_contract.store import LocationClass, Workspace
from eng_contract.units import convert
from fakes.ports import FakeApprovalPort, FakeCalcPort, FakeInputPort
from workflow.adapters import _revit_edit_helpers as fake
from workflow.adapters.test_revit_toolport import _DUPLICATE, _SET, _VALUE_MM, _Rig, _short_write_timeout
from workflows.chain import Step, chain

from eng_harness.adapters import _RevitRunHostPort, _RevitRunToolPort, build_ports
from eng_harness.adapters.revit._session_ops import RevitHostPort
from eng_harness.basis import StoreBasisPort
from eng_harness.block import Registry
from eng_harness.engine import Engine, EnginePorts, EngineSettings, PermissionMode, RunRequest, RunStatus
from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalAnswer, ApprovalRequest, HostLease, RunClass
from eng_harness.servers import ServersConfig

_CRASHED = 71
_DETAIL_CHARS = 1500


class _Approve(FakeApprovalPort):
    async def present(self, request: ApprovalRequest) -> None:
        await super().present(request)
        self.script(request.request_id, ApprovalAnswer(
            request_id=request.request_id, shown_sha256=request.shown_sha256, decision="approve", by="engineer:test"
        ))  # fmt: skip


async def _run(
    rig: _Rig, config: ServersConfig, request: RunRequest, steps: list[Step], cut: str | None, before: bool
) -> tuple[RunStatus, list[str]]:
    workspace = Workspace(root=rig.root / "ws", classification=LocationClass.LOCAL)
    assert request.run_id is not None
    run_dir = workspace.root / "runs" / request.run_id  # created by the engine: a start refuses an existing folder
    ports = build_ports(
        config, workspace, rig.store, run_dir, rig.clock, rig.ids,
        files={"m": rig.original}, lock_dir=rig.root / "locks", launcher=fake.RecordingLauncher(),
    )  # fmt: skip
    send = ports.servers.call
    call = ports.tool_port.call
    tool_port = ports.tool_port
    host_port = ports.host_port
    assert isinstance(tool_port, _RevitRunToolPort)
    assert isinstance(host_port, _RevitRunHostPort)
    acquire = host_port.acquire
    reconcile = tool_port.reconcile
    inputs = FakeInputPort()

    async def acquire_with_working_copy(host_key: str) -> HostLease:
        lease = await acquire(host_key)
        try:
            # In approve_each_write, the fixture supplies the working copy once the run exists and owns the host.
            assert run_dir.is_dir()
            assert await host_port.working_copy("m", run_dir / "copies") == "m@copy"
        except BaseException:
            await host_port.release(lease)
            raise
        return lease

    async def reconcile_and_check(tool: str, args: Any, op_id: str) -> Any:
        entry = tool_port._revit_ledger.find(op_id)
        assert entry is not None
        assert entry.pre_image_ref is not None
        record_id, _ = parse_ref(entry.pre_image_ref)
        original = rig.store.get(record_id).producer.host
        assert original is not None
        before = host_port.revision(original.model_id)
        result = await reconcile(tool, args, op_id)
        after = host_port.revision(original.model_id)
        if result.outcome == "applied":
            assert after == original.model_revision + 1
        else:
            assert after == before == original.model_revision
        return result

    async def dispatch(server: str, role: str, tool: str, *args: Any, **kwargs: Any) -> Any:
        if tool in {_SET, _DUPLICATE}:
            if before and tool == cut:
                os._exit(_CRASHED)
            with (rig.root / "dispatches").open("a", encoding="utf-8") as log:
                log.write(tool + "\n")
        return await send(server, role, tool, *args, **kwargs)

    async def call_then_cut(tool: str, *args: Any, **kwargs: Any) -> Any:
        result = await call(tool, *args, **kwargs)
        if tool == cut:
            os._exit(_CRASHED)
        return result

    patch = pytest.MonkeyPatch()
    patch.setattr(ports.servers, "call", dispatch)
    patch.setattr(ports.tool_port, "call", call_then_cut)
    patch.setattr(tool_port, "reconcile", reconcile_and_check)
    if cut is not None:
        patch.setattr(host_port, "acquire", acquire_with_working_copy)
    engine = Engine(
        workspace, Registry([chain(steps)]),
        EnginePorts(ports.tool_port, ports.host_port, FakeCalcPort(RunClass.TRIAL, []),
                    StoreBasisPort(rig.store), _Approve(), inputs),
        rig.store, EngineSettings(), rig.clock, rig.ids,
    )  # fmt: skip
    try:
        async with ports:
            if cut is not None:
                assert not run_dir.exists()
                result = await engine.start(request)
                raise AssertionError(f"engine stopped before the cut at {cut}: {result}")
            result = await engine.resume(request.run_id)
    except BaseException:
        # The forked engine's failure reaches the parent's assertion message through this file.
        (rig.root / "child-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        patch.undo()
    return result.status, [item.kind for item in inputs.presented]


@pytest.mark.parametrize(
    ("fault", "applied", "cut", "outcome"),
    [
        ("before_dispatch", False, _SET, "not_applied"),
        ("lost_pipe", True, _SET, "applied"),
        ("lost_pipe", False, _SET, "not_applied"),
        ("retry_token_consumed", True, _SET, "applied"),
        ("retry_duplicate", True, _SET, "applied"),
        ("dialog_unanswered", False, _SET, "unknown"),
        ("reply", True, _DUPLICATE, "applied"),
    ],
)
def test_crash_matrix(tmp_path: Path, fault: str, applied: bool, cut: str, outcome: str) -> None:
    faults = (
        []
        if fault in {"before_dispatch", "reply"}
        else [{"fault": fault, "tool": cut, "applied": applied, "seconds": 20.0}]
    )
    rig = _Rig(tmp_path)
    config = _short_write_timeout(fake.revit_config(tmp_path, rig.control, faults=faults), 8)
    rig.freeze_basis()
    with closing(JournalReader(rig.run)) as reader:
        header = reader.events()[0].payload
    assert isinstance(header, ev.RunHeader)
    structure = rig.put_structure()
    duplicate: dict[str, Any] = {
        "model": "m@copy",
        "source_type_id": {"$ref": f"{structure}#/types/0/type_id"},
        "new_type_name": "Replay type",
    }
    set_args: dict[str, Any] = rig.set_args("m@copy", structure, rig.put_sections())
    set_args["value_mm"] = Ref.model_validate(set_args["value_mm"])  # invariant 2: an engineering quantity is a Ref
    steps = [(_SET, set_args), (_DUPLICATE, duplicate)]
    request = RunRequest(
        workflow="chain", input={}, basis_ref=header.basis_ref, mode=PermissionMode.APPROVE_EACH_WRITE,
        run_class=RunClass.TRIAL, run_id=f"run_{rig.ids.new_ulid()}",
    )  # fmt: skip
    worker = multiprocessing.get_context("fork").Process(
        target=anyio.run, args=(_run, rig, config, request, steps, cut, fault == "before_dispatch")
    )
    worker.start()
    try:
        worker.join(timeout=120)
        failure = tmp_path / "child-error.txt"
        detail = failure.read_text(encoding="utf-8")[-_DETAIL_CHARS:] if failure.is_file() else "no traceback"
        assert worker.exitcode == _CRASHED, f"engine did not reach the crash point: {detail}"
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join()
        worker.close()
    data = json.loads(rig.control.read_text(encoding="utf-8"))
    assert data["faults"] == [], "the selected fake fault must have fired before the cut"
    (width,) = [p for p in data["model"]["elements"][0]["parameters"] if p["name"] == "b"]
    assert width["rawValue"] == pytest.approx(convert(_VALUE_MM, "mm", "ft") if applied else fake.B_FT)
    if outcome == "unknown":
        # The unanswered modal also blocks the parameter read used by reconciliation (§4.10).
        data["faults"].append({"fault": "lost_pipe", "tool": "revit_get_element_parameters", "seconds": 20.0})
        rig.control.write_text(json.dumps(data), encoding="utf-8")
    rig.ids = SeededIdSource(b"revit-resume", rig.clock)
    status, requests = anyio.run(_run, rig, config, request, steps, None, False)
    with closing(JournalReader(tmp_path / "ws" / "runs" / str(request.run_id))) as reader:
        events = reader.events()
    starts = [e for e in events if isinstance(e.payload, ev.StepStarted) and e.payload.name in {_SET, _DUPLICATE}]
    first = next(e for e in starts if isinstance(e.payload, ev.StepStarted) and e.payload.name == cut)
    assert isinstance(first.payload, ev.StepStarted)
    reconciled = [e.payload for e in events if isinstance(e.payload, ev.StepReconciled)]
    log = (tmp_path / "dispatches").read_text(encoding="utf-8").splitlines()
    if outcome == "unknown":
        assert status is RunStatus.NEEDS_ENGINEER
        assert requests == ["engine.in_flight"]
        assert len(starts) == 1
        assert reconciled == []
        assert log == [_SET]
        return
    assert status is RunStatus.COMPLETED, requests
    assert [e.payload.name for e in starts if isinstance(e.payload, ev.StepStarted)] == (
        [_SET, _SET, _DUPLICATE] if outcome == "not_applied" else [_SET, _DUPLICATE]
    )
    (decision,) = reconciled
    assert (decision.op_id, decision.outcome, decision.decided_by) == (first.payload.op_id, outcome, "adapter")
    if outcome == "not_applied":
        retry = starts[1]
        assert isinstance(retry.payload, ev.StepStarted)
        assert (retry.path, retry.attempt) == (first.path, 2)
        assert retry.payload.op_id != first.payload.op_id
    assert log == ([_SET, _SET, _DUPLICATE] if fault == "lost_pipe" and not applied else [_SET, _DUPLICATE])
    model = json.loads(rig.control.read_text(encoding="utf-8"))["model"]
    assert sum(row["name"] == duplicate["new_type_name"] for row in model["types"]) == 1
    for start in starts:
        assert any(
            e.path == start.path
            and e.attempt == start.attempt
            and isinstance(e.payload, (ev.StepCompleted, ev.StepReconciled))
            for e in events
        )


def test_reconcile_applied_twice_advances_revision_once(tmp_path: Path) -> None:
    async def exercise() -> None:
        rig = _Rig(
            tmp_path, faults=[{"fault": "retry_token_consumed", "tool": _SET, "seconds": 20.0}], write_timeout_s=8
        )
        rig.freeze_basis()
        tool = rig.ports.tool_port
        host = rig.ports.host_port
        assert isinstance(host, _RevitRunHostPort)
        async with rig.ports:
            key, document = await rig.working_copy()
            original = host.identity_store.resolve(document)
            args = rig.set_args(key, rig.put_structure(), rig.put_sections())
            op_id = "lost-reply"
            assert isinstance(await tool.call(_SET, args, op_id=op_id, model=key), FailureEnvelope)
            for _ in range(2):
                assert (await tool.reconcile(_SET, args, op_id)).outcome == "applied"
                assert host.revision(original.model_id) == original.revision + 1
            assert rig.calls(_SET) == []

    anyio.run(exercise)


def test_load_revit_bindings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def exercise() -> None:
        rig = _Rig(tmp_path)
        host = rig.ports.host_port
        assert isinstance(host, _RevitRunHostPort)
        path = host._binding_path
        folder = rig.run / "copies"
        document = folder / rig.original.name
        key = "m@copy"
        monkeypatch.setattr(RevitHostPort, "_open_model", AsyncMock(return_value={
            "path": str(document), "is_workshared": False, "local_file_created": False,
        }))  # fmt: skip
        monkeypatch.setattr(RevitHostPort, "_document_loaded", AsyncMock(return_value=True))

        assert not path.exists()
        assert await host.locate(key) is None
        assert await host.working_copy("m", folder) == key
        instance = await host.locate(key)
        assert instance is not None
        restored = _Rig(tmp_path).ports.host_port
        assert restored.model_files(key) == (document,)
        assert await restored.locate(key) == instance

        saved = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**saved, "pipe_name": "different-pipe"}), encoding="utf-8")
        assert await _Rig(tmp_path).ports.host_port.locate(key) is None
        saved["models"][key]["document"] = str(folder / "missing.rvt")
        path.write_text(json.dumps(saved), encoding="utf-8")
        assert await _Rig(tmp_path).ports.host_port.locate(key) is None
        path.write_text("{invalid", encoding="utf-8")
        assert await _Rig(tmp_path).ports.host_port.locate(key) is None

    anyio.run(exercise)
