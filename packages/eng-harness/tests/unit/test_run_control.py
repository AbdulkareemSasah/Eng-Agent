"""The stop check between steps (plan 0001 T18, amendment B-412; spec 0001 4.8 RunControlPort row, 4.4.2 `run_paused`).

A true `stop_requested` pauses the run with `run_paused`, reason `stop_requested`, before the next step starts; the
steps already recorded stay as they are and a resume without a stop request finishes the run.
"""

import asyncio
from pathlib import Path

from fakes.ports import FakeBasisPort, FakeCalcPort, FakeRunControl
from workflows.chain import chain
from workflows.rig import Rig, make_rig, request, steps

from eng_harness.block import Registry
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev


class StopAfter(FakeRunControl):
    """Asks for a stop once the host has had `calls` calls; records the run ids it was asked about."""

    def __init__(self, rig: Rig, calls: int | None) -> None:
        super().__init__()
        self._rig, self._calls = rig, calls
        self.asked: list[str] = []

    def stop_requested(self, run_id: str) -> bool:
        self.asked.append(run_id)
        return self._calls is not None and len(self._rig.host.ledger) >= self._calls


def _engine(rig: Rig, control: FakeRunControl | None) -> Engine:
    ports = EnginePorts(
        tool=rig.host, host=rig.host, calc=FakeCalcPort(rig.run_class, rig.calc_infos),
        basis=FakeBasisPort(rig.bases), approvals=rig.approvals, inputs=rig.inputs, run_control=control,
    )  # fmt: skip
    registry = Registry([chain(steps("read_a", "write_b", "read_c"))])
    return Engine(rig.workspace, registry, ports, rig.store, EngineSettings(), rig.clock, rig.ids)


def test_stop_requested_pauses_between_steps(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    control = StopAfter(rig, 1)
    outcome = asyncio.run(_engine(rig, control).start(request()))
    assert outcome.status is RunStatus.PAUSED
    assert outcome.pending == ()
    assert [e.tool for e in rig.host.ledger] == ["read_a"]  # the step that ran stays done; the next one never starts
    events = rig.events(outcome.run_id)
    paused = events[-1].payload
    assert isinstance(paused, ev.RunPaused)
    assert (events[-1].type, paused.reason, paused.request_ids) == (EventType.RUN_PAUSED, "stop_requested", [])
    assert set(control.asked) == {outcome.run_id}
    # a resume with no stop request replays the first step from the journal and runs the other two
    control = StopAfter(rig, None)
    done = asyncio.run(_engine(rig, control).resume(outcome.run_id))
    assert done.status is RunStatus.COMPLETED
    assert [e.tool for e in rig.host.ledger] == ["read_a", "write_b", "read_c"]
    # a stop that is already requested pauses a new run before its first step; no port means no check
    rig = make_rig(tmp_path / "early")
    early = asyncio.run(_engine(rig, StopAfter(rig, 0)).start(request()))
    assert (early.status, rig.host.ledger) == (RunStatus.PAUSED, [])
    rig = make_rig(tmp_path / "none")
    assert asyncio.run(_engine(rig, None).start(request())).status is RunStatus.COMPLETED
