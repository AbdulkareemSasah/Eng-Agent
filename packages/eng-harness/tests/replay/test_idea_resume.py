"""Spec 0014 AC18, AC20 and Q14: cut the engine after a real synthetic host write."""

import hashlib
import multiprocessing
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import patch

import anyio
import pytest
from fakes.ports import FakeInputPort
from mcp.types import CallToolResult
from workflow.adapters.test_idea_loads import _SYNTHETIC_MAP
from workflow.test_idea_cycle import GET_LOADS, MODEL, REST_CALC, SET_LOADS, IdeaCycle

from eng_harness.adapters.idea import _loads
from eng_harness.engine import RunStatus
from eng_harness.journal import _events as ev
from eng_harness.servers import CallEffect

_CUT_EXIT = 23


def _crash_worker(root: Path, route: str, run_id: str, cut: str) -> None:
    rig = IdeaCycle(root, route, run_id)

    async def run() -> None:
        async with rig.ports() as ports:
            send = ports.servers.call

            async def cut_after_apply(
                server: str, role: str, tool: str, args: Mapping[str, Any], effect: CallEffect
            ) -> CallToolResult:
                reply = await send(server, role, tool, args, effect)
                if tool == cut and not reply.is_error:
                    os._exit(_CUT_EXIT)  # Host applied the write, but the adapter has not consumed the reply.
                return reply

            with patch.object(ports.servers, "call", cut_after_apply):
                outcome = await rig.start(ports)
            raise AssertionError(f"engine never reached {cut}: {outcome}")

    with patch.object(_loads, "load_shipped_map", lambda: _loads.load_map_file(_SYNTHETIC_MAP)):
        anyio.run(run)


@pytest.mark.parametrize(("route", "cut"), [("native", SET_LOADS), ("rest", REST_CALC)])
def test_crash_matrix(tmp_path: Path, route: str, cut: str) -> None:
    rig = IdeaCycle(tmp_path, route)
    original = rig.original.read_bytes()
    worker = multiprocessing.get_context("spawn").Process(target=_crash_worker, args=(tmp_path, route, rig.run_id, cut))
    worker.start()
    try:
        worker.join(timeout=120)
        assert worker.exitcode == _CUT_EXIT
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=10)
        worker.close()

    events = rig.events()
    (started,) = [e for e in events if isinstance(e.payload, ev.StepStarted) and e.payload.name == cut]
    assert isinstance(started.payload, ev.StepStarted)
    op_id = started.payload.op_id
    assert not any(e.path == started.path and isinstance(e.payload, ev.StepCompleted) for e in events)
    assert rig.calls().count(cut) == 1
    inputs = FakeInputPort()

    async def resume() -> None:
        async with rig.ports() as fresh:
            assert fresh.host_port.model_files(MODEL) == (rig.copy,)
            if route == "native":
                (bound,) = [
                    e.payload for e in events if isinstance(e.payload, ev.ModelBound) and e.payload.model_key == MODEL
                ]
                held = await fresh.host_port.locate(MODEL)
                assert held is not None
                assert held.instance_id == bound.instance_id
                state = await fresh.host_port.model_state(MODEL, held.instance_id)
                assert state.loaded
                (read,) = [e for e in events if isinstance(e.payload, ev.StepStarted) and e.payload.name == GET_LOADS]
                (recorded,) = [
                    e.payload.result for e in events if isinstance(e.payload, ev.StepCompleted) and e.path == read.path
                ]
                assert recorded is not None
                assert state.file_sha256 == rig.store.payload(recorded.ref)["file_sha256"]
                assert state.file_sha256 == hashlib.sha256(original).hexdigest()
                (destination,) = set(rig.run.rglob("*.ideaCon")) - {rig.copy}
                applied_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
            with patch.object(fresh.servers, "call", wraps=fresh.servers.call) as calls:
                outcome = await rig.engine(fresh, inputs).resume(rig.run_id)
            journal = rig.events()
            assert rig.calls().count(cut) == 1
            assert len([e for e in journal if e.path == started.path and isinstance(e.payload, ev.StepStarted)]) == 1
            reconciled = [
                e.payload for e in journal if isinstance(e.payload, ev.StepReconciled) and e.path == started.path
            ]
            if route == "native":
                assert outcome.status is RunStatus.COMPLETED, outcome
                assert not inputs.presented
                (applied,) = reconciled
                assert (applied.op_id, applied.outcome, applied.decided_by) == (op_id, "applied", "adapter")
                assert applied.result is not None
                assert rig.store.get(applied.result.ref).kind == "harness.idea_loads/1"
                assert rig.store.payload(applied.result.ref)["file_sha256"] == applied_hash
                assert fresh.host_port.model_files(MODEL) == (destination,)
                assert any(
                    args[2] == GET_LOADS and args[3]["path"] == str(destination) for args, _ in calls.await_args_list
                )
            else:
                assert outcome.status is RunStatus.NEEDS_ENGINEER, outcome
                assert outcome.escalation is not None
                assert outcome.escalation.reason == "needs_reconciliation"
                assert "unknown" in outcome.escalation.detail
                assert not reconciled
                (request,) = inputs.presented
                assert request.kind == "engine.in_flight"
                assert cut in request.title
        assert rig.original.read_bytes() == rig.copy.read_bytes() == original

    with patch.object(_loads, "load_shipped_map", lambda: _loads.load_map_file(_SYNTHETIC_MAP)):
        anyio.run(resume)
