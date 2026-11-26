"""Spec 0014 AC20: real Engine and assembled IDEA ports against the synthetic server."""

import hashlib
import json
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import anyio
import pytest
from eng_contract.envelope import Provenance
from eng_contract.ids import SystemClock, SystemIdSource
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.store import LocationClass, ResultStore, Workspace
from fakes.ports import FakeApprovalPort, FakeCalcPort, FakeInputPort
from fakes.sasaah_idea.test_server import make_ideacon
from pydantic import BaseModel, JsonValue
from workflows.chain import ChainOutput

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters import AdapterPorts, build_ports
from eng_harness.adapters.idea import _loads, idea_allowlist
from eng_harness.basis import StoreBasisPort
from eng_harness.block import Registry, workflow
from eng_harness.engine import Engine, EnginePorts, EngineSettings, PermissionMode, RunOutcome, RunRequest, RunStatus
from eng_harness.journal import Event, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.kinds.idea import IDEA_KINDS, IdeaLoads
from eng_harness.ports import ApprovalAnswer, ApprovalRequest, RunClass, ServerCheck
from workflow.adapters.test_idea_calculate import _DESIGN_CODE, _idea_config
from workflow.adapters.test_idea_loads import _SYNTHETIC_MAP, _TOLERANCE, _plan

SET_LOADS = "idea_native_set_loads"
REST_CALC = "idea_calculate"
GET_LOADS = "idea_native_get_loads"
MODEL = "joint@copy"
NATIVE = (GET_LOADS, SET_LOADS, "idea_native_calculate")
REST = ("idea_open_project", "idea_list_connections", REST_CALC, "idea_get_check_results")


class _CycleInput(BaseModel):
    loads: dict[str, JsonValue] = {}


class _Approve(FakeApprovalPort):
    async def present(self, request: ApprovalRequest) -> None:
        await super().present(request)
        self.script(
            request.request_id,
            ApprovalAnswer(
                request_id=request.request_id, shown_sha256=request.shown_sha256, decision="approve", by="test"
            ),
        )


class IdeaCycle:
    def __init__(self, root: Path, route: str, run_id: str | None = None) -> None:
        self.route = route
        self.control = root / "control.json"
        self.original = root / "joint.ideaCon"
        if not self.original.exists():
            make_ideacon(self.original)
        self.clock = SystemClock()
        self.ids = SystemIdSource(self.clock)
        self.workspace = Workspace(root=root / "workspace", classification=LocationClass.LOCAL)
        self.store = ResultStore(self.workspace, HARNESS_KINDS.extend(IDEA_KINDS), self.ids, self.clock)
        self.run_id = run_id or f"run_{self.ids.new_ulid()}"
        self.run = self.workspace.root / "runs" / self.run_id
        self.copy = self.run / "copies" / self.original.name
        self.config = _idea_config(root, self.control, route=route)
        self.locks = root / "locks"
        self.steps = NATIVE if route == "native" else REST

    def ports(self) -> AdapterPorts:
        return build_ports(
            self.config,
            self.workspace,
            self.store,
            self.run,
            self.clock,
            self.ids,
            files={"joint": self.original},
            lock_dir=self.locks,
        )

    def request(self) -> RunRequest:
        producer = Provenance(
            tool="test/idea-cycle", tool_version="1", inputs={}, started_at=self.clock.now(), duration_ms=0
        )
        fields = {
            name: {"value": value, "unit": unit, "source": f"engineer:test@{self.clock.now()}", "confirmed": True}
            for name, value, unit in (
                ("connection.design_code", _DESIGN_CODE, None),
                ("checks.readback_relative_tolerance_ratio", _TOLERANCE, "1"),
            )
        }
        basis = self.store.put("basis.design_basis/1", {"template": None, "fields": cast(JsonValue, fields)}, producer)
        loads = _plan(self.store, self.copy).model_dump(mode="json", by_alias=True) if self.route == "native" else {}
        return RunRequest(
            workflow="idea_cycle",
            input={"loads": loads},
            basis_ref=basis.result_id,
            run_id=self.run_id,
            run_class=RunClass.TRIAL,
            mode=PermissionMode.AUTONOMOUS_LOGGED,
        )

    async def start(self, ports: AdapterPorts) -> RunOutcome:
        preflight = ports.host_port.preflight

        async def prepare_copy(min_builds: Mapping[str, str]) -> list[ServerCheck]:
            checks = await preflight(min_builds)
            # Engine.start checks for a new run directory before preflight. Seed the copy after that check.
            assert await ports.host_port.working_copy("joint", self.copy.parent) == MODEL
            return checks

        with patch.object(ports.host_port, "preflight", prepare_copy):
            return await self.engine(ports).start(self.request())

    def engine(self, ports: AdapterPorts, inputs: FakeInputPort | None = None) -> Engine:
        @workflow(
            name="idea_cycle",
            version=1,
            description="Read and check an IDEA connection on its working copy.",
            min_server_builds={"idea": idea_allowlist().sasaah_commit},
            always_ask=(SET_LOADS,) if self.route == "native" else (REST_CALC,),
        )
        async def cycle(ctx: Any, inp: _CycleInput) -> ChainOutput:
            target: dict[str, JsonValue] = {"model": MODEL}
            native = {**target, "path": str(self.copy), "connection_id": "CON1"}
            args: dict[str, dict[str, JsonValue]] = {
                GET_LOADS: native,
                SET_LOADS: {**inp.loads, **target},
                "idea_native_calculate": native,
                "idea_open_project": {**target, "path": str(self.copy)},
                "idea_list_connections": target,
                # REST calculates the currently open project. Its identity was journaled by the open step.
                REST_CALC: {"connection_ids": [1]},
                "idea_get_check_results": {**target, "connection_id": 1},
            }
            return ChainOutput(refs=[(await ctx.tool(tool, args[tool])).ref.ref for tool in self.steps])

        return Engine(
            self.workspace,
            Registry([cycle]),
            EnginePorts(
                tool=ports.tool_port,
                host=ports.host_port,
                calc=FakeCalcPort(RunClass.TRIAL, []),
                basis=StoreBasisPort(self.store),
                approvals=_Approve(),
                inputs=inputs or FakeInputPort(),
            ),
            self.store,
            EngineSettings(),
            self.clock,
            self.ids,
        )

    def events(self) -> list[Event]:
        with closing(JournalReader(self.run)) as reader:
            return reader.events()

    def calls(self) -> list[str]:
        return [entry["tool"] for entry in json.loads(self.control.read_text(encoding="utf-8"))["calls"]]


def _assert_cycle(rig: IdeaCycle) -> None:
    original = rig.original.read_bytes()

    async def run() -> None:
        async with rig.ports() as ports:
            outcome = await rig.start(ports)
            assert outcome.status is RunStatus.COMPLETED, outcome
            assert isinstance(outcome.output, ChainOutput)
            result_ids = outcome.output.refs
            verdict_refs = result_ids[-1:] if rig.route == "native" else result_ids[-2:]
            for ref in verdict_refs:
                assert rig.store.get(ref).kind == "verdicts.set/1"
                verdicts = VerdictSet.model_validate(rig.store.payload(ref))
                assert verdicts.verdicts
                assert {v.source.value for v in verdicts.verdicts} == {"host"}
                if rig.route == "rest":
                    assert verdicts.draft
            (bound,) = ports.host_port.model_files(MODEL)
            if rig.route == "native":
                assert rig.store.payload(result_ids[0])["file_sha256"] == hashlib.sha256(original).hexdigest()
                loads = IdeaLoads.model_validate(rig.store.payload(result_ids[1]))
                assert loads.effects[0].segments[0].N_kN == 25.0  # synthetic fixture
                assert bound != rig.copy
                assert rig.calls().count(SET_LOADS) == 1
            else:
                assert rig.store.payload(result_ids[0])["live_project"] is True
                assert rig.store.payload(result_ids[1])["connections"]
                assert rig.calls().count(REST_CALC) == 1
        assert rig.original.read_bytes() == rig.copy.read_bytes() == original
        assert set(rig.run.rglob("*.ideaCon")) == {rig.copy, bound}
        events = rig.events()
        assert any(isinstance(e.payload, ev.ModelBound) and e.payload.model_key == MODEL for e in events)
        started = [e for e in events if isinstance(e.payload, ev.StepStarted) and e.payload.kind == "tool"]
        assert [e.payload.name for e in started if isinstance(e.payload, ev.StepStarted)] == list(rig.steps)
        assert {e.path for e in started} <= {e.path for e in events if isinstance(e.payload, ev.StepCompleted)}
        async with rig.ports() as fresh:
            assert fresh.host_port.model_files(MODEL) == (bound,)  # Q14: last binding survives assembly.

    anyio.run(run)


def test_native_cycle_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_loads, "load_shipped_map", lambda: _loads.load_map_file(_SYNTHETIC_MAP))
    _assert_cycle(IdeaCycle(tmp_path, "native"))


def test_rest_cycle_steps(tmp_path: Path) -> None:
    _assert_cycle(IdeaCycle(tmp_path, "rest"))
