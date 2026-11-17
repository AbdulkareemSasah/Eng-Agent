"""Engine overhead per step with a real SQLite journal (plan 0001 T18; spec 0001 AC60, 11 section 10).

1,000 write steps run through a fake ToolPort that returns at once, with a recording ProgressSink and a FakeRunControl
in `EnginePorts`, so the overhead includes the sink delivery and the stop check between steps. The overhead of a step
is the time around `ctx.tool` minus the time of the tool's own call, as S-10 measured it. The test prints p50, p95 and
p99, and the time of a resume that replays the same 1,000 steps. It also runs in the Windows CI job.
"""

import asyncio
import math
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ErrorCode
from fakes.ports import ENVELOPE, FakeBasisPort, FakeCalcPort, FakeRunControl, failure
from workflows.ctx_flows import flow
from workflows.rig import make_rig, request

from eng_harness.block import Registry
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunStatus
from eng_harness.journal import Event

STEPS = 1000
LIMIT_MS = 20.0  # 11 section 10: under 20 ms at p95
WARM = 50


class _Sink:
    """The recording ProgressSink of the benchmark."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]  # nearest rank, as S-10


def test_engine_overhead_p95(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rig = make_rig(tmp_path)
    inner: list[int] = []
    over: list[float] = []
    call = rig.host.call

    async def timed(tool: str, args: Mapping[str, Any], *, op_id: str, model: str | None) -> ENVELOPE:
        start = time.perf_counter_ns()
        try:
            return await call(tool, args, op_id=op_id, model=model)
        finally:
            inner.append(time.perf_counter_ns() - start)

    monkeypatch.setattr(rig.host, "call", timed)

    async def body(ctx: Any) -> list[str]:
        for n in range(STEPS + WARM):
            began = time.perf_counter_ns()
            await ctx.tool("write_b", {"n": n, "model": "m1"})
            total = time.perf_counter_ns() - began
            if n >= WARM and len(over) < STEPS:  # a resume replays the steps and measures nothing
                over.append((total - inner[-1]) / 1e6)
        await ctx.tool("read_c", {"n": 0})  # fails once, so that a resume has the steps above to replay
        return []

    sink, control = _Sink(), FakeRunControl()
    ports = EnginePorts(
        tool=rig.host, host=rig.host, calc=FakeCalcPort(rig.run_class, rig.calc_infos), basis=FakeBasisPort(rig.bases),
        approvals=rig.approvals, inputs=rig.inputs, progress=sink, run_control=control,
    )  # fmt: skip
    engine = Engine(rig.workspace, Registry([flow(body)]), ports, rig.store, EngineSettings(), rig.clock, rig.ids)
    rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))
    stopped = asyncio.run(engine.start(request()))
    assert stopped.status is RunStatus.NEEDS_ENGINEER  # the 1,000 write steps ran; the read after them failed
    assert len(over) == STEPS
    assert len(sink.events) > STEPS  # the sink saw the events of the steps
    began = time.perf_counter()
    assert asyncio.run(engine.resume(stopped.run_id)).status is RunStatus.COMPLETED
    replay_s = time.perf_counter() - began
    p50, p95, p99 = (_percentile(over, p) for p in (50, 95, 99))
    line = f"engine overhead per write step over {STEPS} steps: p50 {p50:.3f} ms, p95 {p95:.3f} ms, p99 {p99:.3f} ms"
    with capsys.disabled():
        sys.stdout.write(f"\n{line}\nresume that replays {STEPS + WARM} steps: {replay_s * 1000:.1f} ms\n")
    assert p95 < LIMIT_MS
