"""Run header of a run on the phase-1 runtime (spec 0009 AC49 (6); plan 0009 T10a).

The real engine and the real cascade, wired as spec 0006 4.2.2 wires them: the cascade is built with the runtime's
`model` and `llm`, and the port's summary is the runtime's.
"""

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

from eng_contract.store import Workspace
from fakes.ports import FakeBasisPort, FakeCalcPort
from pydantic import JsonValue
from workflows.chain import chain
from workflows.rig import make_rig, request, steps

from eng_harness.block import Registry
from eng_harness.decisions import Cascade, LabelStore
from eng_harness.decisions._points import PointRegistry
from eng_harness.decisions._policy import DecisionSettings, ShadowRelease
from eng_harness.decisions.interfaces import DecisionAnswer, DecisionCall, PendingAnswer
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunStatus, rule_guard
from eng_harness.providers import DecisionRuntime, assemble_decision_runtime, load_providers_config

KEY_REF = "-".join(("ref", "secret", "name"))
TABLES = {
    "decision": {
        "base_url": "https://endpoint-host.example.test/v1", "model": "m", "model_version": "v1",
        "key_ref": KEY_REF, "request_timeout_ms": 1500,
    },
    "llm": {
        "base_url": "https://endpoint-host.example.test/v1", "model": "n", "model_version": "v2",
        "key_ref": KEY_REF, "request_timeout_ms": 20000, "max_output_tokens": 64,
    },
}  # fmt: skip


class RuntimePort:
    """The decision port the CLI builds: the cascade decides, the runtime's summary goes to the run header."""

    def __init__(self, cascade: Cascade, runtime: DecisionRuntime) -> None:
        self._cascade, self._runtime = cascade, runtime

    async def decide(self, call: DecisionCall) -> DecisionAnswer | PendingAnswer:
        return await self._cascade.decide(call)

    async def decide_many(self, calls: Sequence[DecisionCall]) -> list[DecisionAnswer | PendingAnswer]:
        return await self._cascade.decide_many(calls)

    def runtime_summary(self) -> Mapping[str, JsonValue]:
        return self._runtime.summary


def test_run_header_records_phase1_summary(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    release = ShadowRelease(point_version=1, basis="owner", record="owner_1")
    settings = DecisionSettings(shadow_released={"pick_action": release})
    workspace: Workspace = rig.workspace
    runtime = assemble_decision_runtime(load_providers_config(TABLES), settings, workspace, {})
    cascade = Cascade(
        PointRegistry([]), settings, LabelStore(workspace.root, settings, rig.clock, rig.ids),
        clock=rig.clock, monotonic=lambda: 0.0, rule_guard=rule_guard, model=runtime.model, llm=runtime.llm,
    )  # fmt: skip
    ports = EnginePorts(
        tool=rig.host, host=rig.host, calc=FakeCalcPort(rig.run_class, rig.calc_infos),
        basis=FakeBasisPort(rig.bases), approvals=rig.approvals, inputs=rig.inputs,
        decision=RuntimePort(cascade, runtime),
    )  # fmt: skip
    engine = Engine(
        workspace, Registry([chain(steps("read_a"))]), ports, rig.store, EngineSettings(), rig.clock, rig.ids
    )
    outcome = asyncio.run(engine.start(request()))
    assert outcome.status is RunStatus.COMPLETED
    header = rig.header(outcome.run_id)
    assert header.decision_runtime == dict(runtime.summary)
    providers = header.decision_runtime["providers"]
    assert isinstance(providers, list)
    assert [p.get("status") if isinstance(p, dict) else None for p in providers] == ["not_implemented"] * 2
    assert header.decision_runtime["dropped_releases"] == [{"point": "pick_action", "reason": "PR-G1"}]
    journal = b"".join(
        path.read_bytes() for path in (workspace.root / "runs" / outcome.run_id).rglob("*") if path.is_file()
    )
    for needle in (KEY_REF, "endpoint-host", "owner_1"):
        assert needle.encode() not in journal
