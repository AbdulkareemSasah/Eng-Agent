"""The worker process of the crash matrix (plan 0001 T19, spec 0001 AC30): a mixed test workflow that dies on cue.

Test double; never shipped. `run_worker` starts the workflow in a process of its own and ends it with `os._exit` at one
crash point: through a recording `ProgressSink` whose `emit` exits on a target event (the first three points, spec
4.10) or through the fake host's call wrapper, which exits right after a call returns (`after_effect`). The host keeps a
ledger file in the test's workspace, so the process that resumes the run, and the comparison, see every call the dead
process applied; the fake host's own ledger is lost with the process.
"""

import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eng_contract.envelope import SuccessEnvelope
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore
from fakes.ports import ENVELOPE, FakeBasisPort, FakeCalcPort
from pydantic import JsonValue
from workflows.ctx_flows import change_set, flow
from workflows.rig import START_MS, Host, Rig, Spy, make_rig, request

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.block import BlockDef, Registry
from eng_harness.engine import Engine, EnginePorts, EngineSettings
from eng_harness.journal import Event
from eng_harness.ports import Reconciliation

CRASH_EXIT = 77
"""The exit code of a worker that reached its crash point."""
HOUR_MS = 3_600_000
LEDGER = "host-ledger.jsonl"


@dataclass(frozen=True)
class Crash:
    """Where a worker dies: after the journal event `seq` is delivered to the sink, or after host call number `call`."""

    point: str
    seq: int | None = None
    call: int | None = None


class CrashSink:
    """A `ProgressSink` that ends the process once the event at the target sequence number has been committed."""

    def __init__(self, crash: Crash | None) -> None:
        """Watch for `crash`; none never exits."""
        self._crash = crash

    def emit(self, event: Event) -> None:
        """Exit on the target event."""
        if self._crash is not None and self._crash.seq == event.seq:
            os._exit(CRASH_EXIT)


class LedgerHost(Host):
    """The rig's fake host with a ledger file, reconciliation from that file, and a crash right after a call."""

    def __init__(
        self, ids: SeededIdSource, clock: FixedClock, runs_dir: Path, ledger: Path, crash: Crash | None
    ) -> None:
        """Keep the ledger in `ledger`; `crash` with a `call` number ends the process after that call returns."""
        super().__init__(ids, clock, runs_dir)
        self.ledger_file, self._crash, self._calls = ledger, crash, 0

    async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> ENVELOPE:
        """Call the fake host, note the call in the ledger file and, at the crash point, exit instead of returning."""
        before = dict(self.models)
        result = await super().call(tool, args, op_id=op_id, model=model)
        self.models.update(before)  # a write leaves no trace on the model: its identity is the same in every process
        effect = (await self.describe(tool)).effect
        entry = {
            "tool": tool,
            "args": dict(args),
            "op_id": op_id,
            "model": model,
            "effect": effect,
            "ok": result.ok,
            "result": result.model_dump(mode="json"),
        }
        with self.ledger_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
        self._calls += 1
        if self._crash is not None and self._crash.call == self._calls:
            os._exit(CRASH_EXIT)
        return result

    async def reconcile(self, tool: str, args: Mapping[str, JsonValue], op_id: str) -> Reconciliation:
        """`applied` with the result of the call the ledger file holds under `op_id`, else `not_applied`."""
        for entry in read_ledger(self.ledger_file):
            if entry["op_id"] == op_id and entry["ok"]:  # the host answers with the result of the call it applied
                return Reconciliation(outcome="applied", result=SuccessEnvelope.model_validate(entry["result"]))
        return Reconciliation(outcome="not_applied")


def read_ledger(path: Path) -> list[dict[str, Any]]:
    """The calls that reached the host, in order, across every process of the run."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def worker_rig(root: Path, generation: int, crash: Crash | None) -> Rig:
    """The rig of one process: the same workspace and model identities every time, new ids and times per `generation`.

    A resuming process must not draw the identifiers the dead one drew, so each generation has its own id source and
    clock. The fake host keeps the first generation's identities, so the models are the same in every process.
    """
    rig = make_rig(root)
    clock = FixedClock(START_MS + generation * HOUR_MS, 1)
    ids = SeededIdSource(f"generation-{generation}".encode(), clock)
    first_clock = FixedClock(START_MS, 1)
    first_ids = SeededIdSource(b"harness", first_clock)
    rig.clock, rig.ids = clock, ids
    rig.store = ResultStore(rig.workspace, HARNESS_KINDS, ids, clock)
    rig.host = LedgerHost(first_ids, first_clock, rig.workspace.root / "runs", root / LEDGER, crash)
    return rig


def mixed(rig: Rig) -> BlockDef[Any, Any]:
    """A workflow with a read, a write, a parallel pair (a read and a write), an approval, a write and a read."""
    shown = change_set(rig, "i1")

    async def body(ctx: Any) -> list[str]:
        out = []
        for tool, args in (("read_a", {"n": 0}), ("write_b", {"n": 1, "model": "m1"})):
            out.append(f"{tool}:{(await ctx.tool(tool, args)).summary}")
        pair = await ctx.parallel(ctx.tool("read_c", {"n": 2}), ctx.tool("write_b", {"n": 3, "model": "m2"}))
        out.extend(f"{r.tool}:{r.summary}" for r in pair)
        await ctx.approve("Apply", shown)
        for tool, args in (("write_b", {"n": 4, "model": "m1"}), ("read_a", {"n": 5})):
            out.append(f"{tool}:{(await ctx.tool(tool, args)).summary}")
        return out

    return flow(body, name="mixed")


def build_engine(rig: Rig, crash: Crash | None) -> Engine:
    """An engine over the rig, with the crashing sink as its progress port."""
    ports = EnginePorts(
        tool=Spy("tool", rig.host, rig.log),
        host=Spy("host", rig.host, rig.log),
        calc=Spy("calc", FakeCalcPort(rig.run_class, rig.calc_infos), rig.log),
        basis=Spy("basis", FakeBasisPort(rig.bases), rig.log),
        approvals=Spy("approvals", rig.approvals, rig.log),
        inputs=Spy("inputs", rig.inputs, rig.log),
        progress=CrashSink(crash),
    )
    return Engine(rig.workspace, Registry([mixed(rig)]), ports, rig.store, EngineSettings(), rig.clock, rig.ids)


def run_worker(root: str, crash: Crash | None) -> None:
    """The process body: start the mixed workflow; it ends at `crash`, or normally when there is none."""
    rig = worker_rig(Path(root), 0, crash)
    asyncio.run(build_engine(rig, crash).start(request("mixed")))
    assert crash is None, "the worker passed its crash point"
