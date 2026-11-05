"""Engine start: validation, the run header, the run class and the unreleased-tool record (plan 0001 T9).

Covers spec 0001 AC16 (input and output validation), the start halves of AC65 (run class) and AC68 (unreleased tools),
the run header of section 4.4.2, the minimal `ctx.tool` and the settings of section 4.10. Resume, the replay index and
the resume halves of AC65 and AC68 belong to task T9b. Fake ports and a real SQLite journal in a temporary workspace;
the fake host's ledger shows which calls reached it. The rig is local to this file: the task's file scope holds no
shared test helper.
"""

import asyncio
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract import CONTRACT_VERSION
from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode, ErrorDetail
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from fakes.ports import FakeApprovalPort, FakeBasisPort, FakeCalcPort, FakeHost, FakeInputPort, failure
from pydantic import BaseModel, JsonValue, ValidationError

from eng_harness import __version__
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.block import Registry, WorkflowDef, workflow
from eng_harness.engine import Engine, EnginePorts, EngineSettings, PermissionMode, RunRequest, RunStatus
from eng_harness.engine._steps import op_id
from eng_harness.errors import HarnessCode, RunRefused
from eng_harness.journal import Event, EventType, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.ports import RunClass, ToolInfo

T = EventType
START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
BASIS_REF = "res_" + "0" * 26
RUN_ID = re.compile(r"^run_[0-7][0-9A-HJKMNP-TV-Z]{25}$")
TOOLS = (
    ToolInfo(name="read_a", effect="read", action="plain", host_key="csi"),
    ToolInfo(name="read_c", effect="read", action="plain", host_key="csi"),
    ToolInfo(name="write_b", effect="write", action="plain", host_key="csi", model_param="model"),
)
Step = tuple[str, dict[str, JsonValue]]


class ChainInput(BaseModel):
    """Input of the test workflows: a label and an integer count (so a string for the count is an invalid input)."""

    label: str = "x"
    count: int = 0


class ChainOutput(BaseModel):
    """Output of the test workflows: the result reference of each step, in order."""

    refs: list[str]


class Impostor(BaseModel):
    """A model that is not `ChainOutput`."""

    refs: list[str] = []


def chain(steps: Sequence[Step], *, always_ask: tuple[str, ...] = ()) -> WorkflowDef[ChainInput, ChainOutput]:
    """A workflow that calls each of `steps` in order and returns their result references."""

    @workflow(name="chain", version=1, description="Calls its tools in order.", always_ask=always_ask)
    async def run(ctx: Any, inp: ChainInput) -> ChainOutput:
        refs = []
        for tool, args in steps:
            result = await ctx.tool(tool, args)
            refs.append(result.ref.ref)
        return ChainOutput(refs=refs)

    return run


@workflow(name="bad_output", version=1, description="Returns a value that is not its output model.")
async def bad_output(ctx: Any, inp: ChainInput) -> ChainOutput:
    """Returns an `Impostor`, which the engine must refuse."""
    return cast(ChainOutput, Impostor())


def steps(*names: str) -> Sequence[Step]:
    """Steps that call the tools `names` in order, each with its position as the argument `n`."""
    return [(name, {"n": index}) for index, name in enumerate(names)]


@dataclass
class Rig:
    """The parts of an engine's world: workspace, result store, deterministic sources and the fake host."""

    workspace: Workspace
    store: ResultStore
    clock: FixedClock
    ids: SeededIdSource
    host: FakeHost
    approvals: FakeApprovalPort
    inputs: FakeInputPort

    def engine(
        self,
        *workflows: WorkflowDef[Any, Any],
        calc_class: RunClass = RunClass.PRODUCTION,
        settings: EngineSettings | None = None,
    ) -> Engine:
        """An engine that registers `workflows`; its calc port has class `calc_class`."""
        ports = EnginePorts(
            tool=self.host,
            host=self.host,
            calc=FakeCalcPort(calc_class, []),
            basis=FakeBasisPort({}),
            approvals=self.approvals,
            inputs=self.inputs,
        )
        return Engine(
            self.workspace, Registry(workflows), ports, self.store, settings or EngineSettings(), self.clock, self.ids
        )

    def run_dir(self, run_id: str) -> Path:
        """The folder of the run."""
        return self.workspace.root / "runs" / run_id

    def run_ids(self) -> list[str]:
        """The ids of the run folders, sorted."""
        return sorted(p.name for p in (self.workspace.root / "runs").glob("run_*"))

    def events(self, run_id: str) -> list[Event]:
        """The journal of the run, read and verified."""
        reader = JournalReader(self.run_dir(run_id))
        try:
            return reader.events()
        finally:
            reader.close()

    def header(self, run_id: str) -> ev.RunHeader:
        """The run header, the payload of the first event."""
        head = self.events(run_id)[0].payload
        assert isinstance(head, ev.RunHeader)
        return head


def make_rig(root: Path, unreleased: Mapping[str, str] | None = None) -> Rig:
    """A rig whose workspace and result store are under `root`."""
    clock = FixedClock(START_MS, 1)
    ids = SeededIdSource(b"harness", clock)
    workspace = Workspace(root=root / "ws", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    host = FakeHost(TOOLS, ids, clock, unreleased)
    return Rig(workspace, store, clock, ids, host, FakeApprovalPort(), FakeInputPort())


def request(
    workflow_name: str = "chain",
    values: Mapping[str, JsonValue] | None = None,
    *,
    run_class: RunClass = RunClass.PRODUCTION,
    mode: PermissionMode = PermissionMode.WORK_ON_COPY,
) -> RunRequest:
    """A request to run `workflow_name` with the input `values`."""
    return RunRequest(
        workflow=workflow_name, input=dict(values or {}), basis_ref=BASIS_REF, mode=mode, run_class=run_class
    )


@pytest.mark.parametrize(
    "bad", [{"count": "3"}, {"count": 1.5}, {"count": None}, {"label": 5}, {"count": float("nan")}]
)
def test_input_and_output_validation(tmp_path: Path, bad: dict[str, JsonValue]) -> None:
    rig = make_rig(tmp_path)
    engine = rig.engine(chain(steps("read_a")), bad_output)
    with pytest.raises(ContractError) as refused:  # the input is checked strictly: no string for an integer, no float
        asyncio.run(engine.start(request(values=bad)))
    assert refused.value.detail.code is ErrorCode.INVALID_ARGUMENT
    with pytest.raises(ContractError) as unknown:
        asyncio.run(engine.start(request("no_such_workflow")))
    assert unknown.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert rig.run_ids() == []  # no run folder
    assert rig.host.ledger == []  # and no tool was called
    outcome = asyncio.run(engine.start(request("bad_output", {"count": 1})))  # a valid input, a wrong return value
    assert outcome.status is RunStatus.NEEDS_ENGINEER
    assert outcome.output is None
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "block_rule_violation"
    assert "ChainOutput" in outcome.escalation.detail
    assert "Impostor" in outcome.escalation.detail
    assert [e.type for e in rig.events(outcome.run_id)] == [T.RUN_STARTED, T.RUN_ESCALATED]  # and no output stored


def test_run_class_recorded_and_checked(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    workflow_def = chain(steps("read_a"))
    for asked, calc_class in ((RunClass.TRIAL, RunClass.PRODUCTION), (RunClass.PRODUCTION, RunClass.TRIAL)):
        with pytest.raises(RunRefused) as refused:
            asyncio.run(rig.engine(workflow_def, calc_class=calc_class).start(request(run_class=asked)))
        assert refused.value.code is HarnessCode.RUN_CLASS_MISMATCH
        assert asked.value in refused.value.message
        assert calc_class.value in refused.value.message
    assert rig.run_ids() == []  # no run folder
    assert rig.host.ledger == []
    for run_class in RunClass:
        outcome = asyncio.run(rig.engine(workflow_def, calc_class=run_class).start(request(run_class=run_class)))
        assert outcome.status is RunStatus.COMPLETED
        assert rig.header(outcome.run_id).run_class == run_class.value
        reader = JournalReader(rig.run_dir(outcome.run_id))
        assert reader.run().run_class == run_class.value  # the reader shows the recorded class
        reader.close()


def test_unreleased_tools_recorded(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, {"write_b": "B-1", "read_c": "B-2"})
    outcome = asyncio.run(rig.engine(chain(steps("read_a"))).start(request()))
    assert rig.header(outcome.run_id).unreleased_tools == {"write_b": "B-1", "read_c": "B-2"}
    reader = JournalReader(rig.run_dir(outcome.run_id))
    assert dict(reader.run().unreleased_tools) == {"write_b": "B-1", "read_c": "B-2"}
    reader.close()
    released = make_rig(tmp_path / "released")  # no tool is unreleased: the record is empty
    done = asyncio.run(released.engine(chain(steps("read_a"))).start(request()))
    assert released.header(done.run_id).unreleased_tools == {}


def test_start_journals_header_and_output(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    workflow_def = chain([("read_a", {"n": 0}), ("write_b", {"n": 1, "model": "m1"})], always_ask=("write_b",))
    settings = EngineSettings(step_retry_limit=3)
    given: dict[str, JsonValue] = {"label": "a", "count": 2}
    asked = request(values=given, mode=PermissionMode.AUTONOMOUS_LOGGED)
    outcome = asyncio.run(rig.engine(workflow_def, settings=settings).start(asked))
    run_id = outcome.run_id
    assert outcome.status is RunStatus.COMPLETED
    assert (outcome.pending, outcome.escalation) == ((), None)
    assert isinstance(outcome.output, ChainOutput)
    assert RUN_ID.fullmatch(run_id)
    assert rig.run_ids() == [run_id]
    assert {p.name for p in rig.run_dir(run_id).iterdir()} >= {"journal.sqlite", "run.lock"}
    events = rig.events(run_id)
    assert [e.type for e in events] == [
        T.RUN_STARTED, T.STEP_STARTED, T.STEP_COMPLETED, T.STEP_STARTED, T.STEP_COMPLETED, T.RUN_COMPLETED,
    ]  # fmt: skip
    head = rig.header(run_id)
    assert (head.run_id, head.workflow) == (run_id, "chain")
    assert head.block == ev.BlockRef(name="chain", version="1", code_sha256=workflow_def.code_sha256)
    assert (head.mode, head.run_class, head.basis_ref) == ("autonomous_logged", "production", BASIS_REF)
    assert (head.engine_version, head.contract_version) == (__version__, CONTRACT_VERSION)
    assert head.settings_sha256 == payload_sha256(settings.model_dump(mode="json"))
    assert head.settings_sha256 != payload_sha256(EngineSettings().model_dump(mode="json"))
    assert (head.servers, head.always_ask, head.unreleased_tools, head.decision_runtime) == ([], ["write_b"], {}, {})
    assert rig.store.payload(head.input_ref) == {"value": given}  # the input is stored, not copied into the journal
    assert head.input_sha256 == payload_sha256(given)
    read, read_done, write, write_done, done = events[1:]
    assert (read.path, read.attempt, write.path, write.attempt) == ("0", 1, "1", 1)
    started_read, started_write = read.payload, write.payload
    assert isinstance(started_read, ev.StepStarted)
    assert isinstance(started_write, ev.StepStarted)
    assert (started_read.kind, started_read.name, started_read.args, started_read.effect) == (
        "tool",
        "read_a",
        {"n": 0},
        "read",
    )
    assert started_read.args_sha256 == payload_sha256({"n": 0})
    assert (started_read.op_id, started_read.host_key, started_read.model_key) == (None, "csi", None)
    assert started_write.effect == "write"
    assert (started_write.op_id, started_write.model_key) == (op_id(run_id, "1", 1), "m1")
    assert [(c.tool, c.op_id, c.model) for c in rig.host.ledger] == [
        ("read_a", op_id(run_id, "0", 1), None), ("write_b", op_id(run_id, "1", 1), "m1"),
    ]  # fmt: skip
    for closing, ref in ((read_done, outcome.output.refs[0]), (write_done, outcome.output.refs[1])):
        assert isinstance(closing.payload, ev.StepCompleted)
        assert closing.payload.result is not None
        assert closing.payload.result.ref == ref
        assert (closing.payload.result.warnings, closing.payload.result.complete) == ([], True)
        assert closing.payload.duration_ms >= 0
    assert isinstance(done.payload, ev.RunCompleted)
    stored = {"refs": outcome.output.refs}
    assert rig.store.payload(done.payload.output_ref) == {"value": stored}
    assert done.payload.output_sha256 == payload_sha256(stored)
    assert done.payload.draft is False
    for port in (rig.approvals, rig.inputs):  # task T9 presents no approval and no input request
        assert (port.presented, port.waits) == ([], [])


def test_a_failed_step_stops_the_run_for_the_engineer(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.host.script("read_c", failure(ErrorCode.NOT_FOUND, "no such object"))
    outcome = asyncio.run(rig.engine(chain(steps("read_a", "read_c", "read_a"))).start(request()))
    assert outcome.status is RunStatus.NEEDS_ENGINEER  # the failure leaves the block, so the run waits for the engineer
    assert outcome.output is None
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "unhandled_error"
    assert outcome.escalation.detail == "no such object"
    assert [e.type for e in rig.events(outcome.run_id)] == [
        T.RUN_STARTED, T.STEP_STARTED, T.STEP_COMPLETED, T.STEP_STARTED, T.STEP_FAILED, T.RUN_ESCALATED,
    ]  # fmt: skip
    failed = rig.events(outcome.run_id)[4]
    assert (failed.path, failed.attempt) == ("1", 1)
    assert isinstance(failed.payload, ev.StepFailed)
    assert isinstance(failed.payload.error, ErrorDetail)
    assert failed.payload.error.code is ErrorCode.NOT_FOUND
    assert failed.payload.retryable is False
    assert [c.tool for c in rig.host.ledger] == ["read_a", "read_c"]  # the third step never ran


def test_request_defaults_and_validation() -> None:
    plain = RunRequest(workflow="chain", input={}, basis_ref=BASIS_REF)
    assert (plain.mode, plain.run_class) == (PermissionMode.WORK_ON_COPY, RunClass.PRODUCTION)
    with pytest.raises(ValidationError):
        RunRequest.model_validate({"workflow": "chain", "input": {}, "basis_ref": "not a ref"})
    with pytest.raises(ValidationError):
        RunRequest.model_validate({"workflow": "chain", "input": {}, "basis_ref": BASIS_REF, "extra": 1})
    with pytest.raises(ValidationError):
        plain.__setattr__("workflow", "other")  # the request is frozen


def test_settings_and_enums() -> None:
    settings = EngineSettings()
    assert (settings.max_parallel_children, settings.max_concurrent_hosts, settings.max_concurrent_decisions) == (
        8,
        1,
        4,
    )
    assert (settings.max_attempts_cap, settings.step_retry_limit) == (10, 2)
    for name in (
        "max_parallel_children",
        "max_concurrent_hosts",
        "max_concurrent_decisions",
        "max_attempts_cap",
        "step_retry_limit",
    ):
        with pytest.raises(ValidationError):
            EngineSettings.model_validate({name: 0})
    with pytest.raises(ValidationError):
        settings.__setattr__("max_attempts_cap", 3)  # the model is frozen
    assert {m.value for m in PermissionMode} == {"work_on_copy", "approve_each_write", "autonomous_logged"}
    assert {s.value for s in RunStatus} == {"COMPLETED", "PAUSED", "NEEDS_ENGINEER", "FAILED"}
