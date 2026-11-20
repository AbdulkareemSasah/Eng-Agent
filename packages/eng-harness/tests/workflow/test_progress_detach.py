"""A raising TerminalProgress is detached and the run continues (plan 0006 T17; AC19 / engine AC58).

Installed directly as the real engine's only sink: through the production fan-out a failing member is detached by the
fan-out itself and engine AC58 is never reached (that path is T16b).
"""

from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path

import pytest
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.basis import DesignBasis
from eng_contract.store import LocationClass, ResultStore, Workspace
from fakes.ports import FakeApprovalPort, FakeBasisPort, FakeCalcPort, FakeInputPort
from workflows.chain import chain
from workflows.rig import BASIS_REF, START_MS, Host, request, steps

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.block import Registry
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunStatus
from eng_harness.journal import Event, EventType, JournalReader
from eng_harness.ports import LoadedBasis, RunClass
from eng_harness.progress import ExpectedTimes, ProgressRenderer, TerminalProgress

THREE = steps("read_a", "write_b", "read_c")


class _Raising(ProgressRenderer):
    """Raises once the first event is fed."""

    def feed(self, event: Event) -> str:
        raise RuntimeError("renderer defect")


def test_raising_renderer_detached_run_continues(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    clock = FixedClock(START_MS, 1)
    ids = SeededIdSource(b"detach", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    runs = workspace.root / "runs"
    runs.mkdir(parents=True)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    host = Host(ids, clock, runs)
    stream = io.StringIO()
    sink = TerminalProgress(_Raising("plain", ExpectedTimes({})), stream, mode="plain", queue_lines=100)
    bases = {BASIS_REF: LoadedBasis(result_id=BASIS_REF, basis=DesignBasis(template=None, fields={}))}
    ports = EnginePorts(
        tool=host,
        host=host,
        calc=FakeCalcPort(RunClass.PRODUCTION, ()),
        basis=FakeBasisPort(bases),
        approvals=FakeApprovalPort(),
        inputs=FakeInputPort(),
        progress=sink,
    )
    engine = Engine(workspace, Registry([chain(THREE)]), ports, store, EngineSettings(), clock, ids)
    with caplog.at_level(logging.WARNING):
        outcome = asyncio.run(engine.start(request()))
    assert outcome.status is RunStatus.COMPLETED
    reader = JournalReader(runs / outcome.run_id)
    try:
        journal = [e.type for e in reader.events()]
    finally:
        reader.close()
    assert journal[-1] is EventType.RUN_COMPLETED
    assert "renderer defect" in caplog.text
    assert "detached" in caplog.text.lower()
    assert stream.getvalue() == ""  # the raising renderer wrote nothing
