"""Test rig for the engine: an `Engine` over the in-memory fakes with a real SQLite journal in a temporary workspace.

Test doubles for plan 0001 T9 and T9b; never shipped. Every port is wrapped in a `Spy` that logs `<port>.<method>`, so a
test can state which port calls a step of the engine made (spec 0001 AC28, AC35, AC65). Several engines over the same
workspace, store and fake host stand for several processes that open the same run.
"""

import inspect
import multiprocessing
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any

import pytest
from eng_contract import CONTRACT_VERSION
from eng_contract.canonical import payload_sha256
from eng_contract.envelope import FailureEnvelope, Provenance
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.basis import DesignBasis
from eng_contract.store import LocationClass, ResultStore, Workspace
from fakes.ports import ENVELOPE, FakeApprovalPort, FakeBasisPort, FakeCalcPort, FakeHost, FakeInputPort, Raise
from pydantic import JsonValue

from eng_harness import __version__
from eng_harness._kinds import HARNESS_KINDS
from eng_harness._runlock import RunLock
from eng_harness.block import BlockDef, Registry
from eng_harness.engine import Engine, EnginePorts, EngineSettings, PermissionMode, RunRequest
from eng_harness.journal import Event, EventType, JournalReader, JournalWriter, is_locked
from eng_harness.journal import _events as ev
from eng_harness.ports import CalcInfo, HostInstance, LoadedBasis, RunClass, ServerCheck, ToolInfo

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
BASIS_REF = "res_" + "0" * 26
OPEN_MODELS = ("m1", "m2")
TOOLS = (
    ToolInfo(name="read_a", effect="read", action="plain", host_key="csi"),
    ToolInfo(name="read_c", effect="read", action="plain", host_key="csi"),
    ToolInfo(name="write_b", effect="write", action="plain", host_key="csi", model_param="model"),
)


class Spy:
    """Forwards every call to `target` and logs `<port>.<method>`; attributes that are not callable pass through."""

    def __init__(self, port: str, target: object, log: list[str]) -> None:
        """Wrap `target` as the port named `port`."""
        self._port, self._target, self._log = port, target, log

    def __getattr__(self, name: str) -> Any:
        member = getattr(self._target, name)
        if not callable(member):
            return member
        label = f"{self._port}.{name}"
        if inspect.iscoroutinefunction(member):

            async def call_async(*args: Any, **kwargs: Any) -> Any:
                self._log.append(label)
                return await member(*args, **kwargs)

            return call_async

        def call(*args: Any, **kwargs: Any) -> Any:
            self._log.append(label)
            return member(*args, **kwargs)

        return call


class Host(FakeHost):
    """The fake host with a record of unreleased tools that a test can change between two resumes.

    `locked` holds, for each call that reached the host, whether any run folder under `runs_dir` was locked.
    `started` holds the instances its servers started for the engine (none by default: the models of the rig are open in
    an instance that was running already), which `started_instances` lists and `close_started` removes (4.6 #10).
    """

    def __init__(
        self, ids: SeededIdSource, clock: FixedClock, runs_dir: Path, unreleased: Mapping[str, str] | None = None
    ) -> None:
        """Serve `TOOLS`; `unreleased` names the tools that are not released yet (none by default)."""
        super().__init__(TOOLS, ids, clock)
        rig_instance = HostInstance(instance_id="rig-1", pid=1, process_started_at=clock.now(), program="csi")
        for key in OPEN_MODELS:  # the models the tests address are open (spec 4.8: a step on a closed model is refused)
            self.add_model(key, rig_instance)
        self.unreleased: dict[str, str] = dict(unreleased or {})
        self.locked: list[bool] = []
        self._runs_dir = runs_dir
        self._checks: dict[str, deque[ENVELOPE | Raise]] = {}
        self.preflight_checks: list[ServerCheck] | None = None
        self.started: list[HostInstance] = []

    async def started_instances(self, host_key: str) -> list[HostInstance]:
        """The instances of `host_key` in `started`."""
        return [i for i in self.started if i.program == host_key]

    async def close_started(self, host_key: str, instances: Sequence[HostInstance]) -> None:
        """Close the instances (the fake host's record) and forget them in `started`."""
        await super().close_started(host_key, instances)
        gone = {i.instance_id for i in instances}
        self.started = [i for i in self.started if i.instance_id not in gone]

    def script_check(self, model_key: str, outcome: ENVELOPE | Raise) -> None:
        """Queue `outcome` for the next `check_model` of `model_key`; with none queued the check succeeds."""
        self._checks.setdefault(model_key, deque()).append(outcome)

    async def check_model(self, model_key: str) -> ENVELOPE:
        """The next scripted check, or the fake host's passing check."""
        queue = self._checks.get(model_key)
        if queue:
            outcome = queue.popleft()
            if isinstance(outcome, Raise):
                raise outcome.error
            return outcome
        return await super().check_model(model_key)

    async def preflight(self, min_builds: Mapping[str, str]) -> list[ServerCheck]:
        """`preflight_checks` when set, otherwise one passing check per minimum build."""
        if self.preflight_checks is not None:
            return self.preflight_checks
        return await super().preflight(min_builds)

    def script(self, tool: str, *outcomes: ENVELOPE | Raise) -> None:
        """Queue outcomes; a retryable failure of a read fails every attempt of one run (the engine retries reads).

        A test that scripted a failure to stop a run at a read keeps that meaning: the failure is queued once for each
        attempt the default settings allow. `outcomes[tool]` takes exact outcomes.
        """
        attempts = 1 + EngineSettings().step_retry_limit
        for outcome in outcomes:
            retryable = isinstance(outcome, FailureEnvelope) and outcome.error.retryable
            self.outcomes[tool].extend(
                [outcome] * (attempts if retryable and self._tools[tool].effect == "read" else 1)
            )

    def unreleased_tools(self) -> Mapping[str, str]:
        """A copy of `unreleased`."""
        return dict(self.unreleased)

    async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> ENVELOPE:
        """Note whether a run is locked, then behave as the fake host."""
        self.locked.append(any(is_locked(p) for p in self._runs_dir.iterdir()))
        return await super().call(tool, args, op_id=op_id, model=model)


@dataclass
class Rig:
    """The shared parts of the engines of one test: workspace, store, fake host and the port-call log."""

    workspace: Workspace
    store: ResultStore
    clock: FixedClock
    ids: SeededIdSource
    host: Host
    approvals: FakeApprovalPort
    inputs: FakeInputPort
    run_class: RunClass = RunClass.PRODUCTION
    log: list[str] = field(default_factory=list)
    calc_infos: list[CalcInfo] = field(default_factory=list)
    calc_results: dict[str, ENVELOPE | Raise] = field(default_factory=dict)
    calc_runs: list[tuple[str, Mapping[str, JsonValue]]] = field(default_factory=list)
    bases: Mapping[str, LoadedBasis] = field(default_factory=dict)

    def engine(
        self,
        *workflows: BlockDef[Any, Any],
        calc_class: RunClass | None = None,
        settings: EngineSettings | None = None,
    ) -> Engine:
        """A new engine over the shared parts that registers `workflows`; its calc port has class `calc_class`."""
        calc = FakeCalcPort(calc_class or self.run_class, self.calc_infos)
        calc.results, calc.runs = self.calc_results, self.calc_runs  # shared by every engine of the rig
        ports = EnginePorts(
            tool=Spy("tool", self.host, self.log),
            host=Spy("host", self.host, self.log),
            calc=Spy("calc", calc, self.log),
            basis=Spy("basis", FakeBasisPort(self.bases), self.log),
            approvals=Spy("approvals", self.approvals, self.log),
            inputs=Spy("inputs", self.inputs, self.log),
        )
        return Engine(
            self.workspace, Registry(workflows), ports, self.store, settings or EngineSettings(), self.clock, self.ids
        )

    def run_dir(self, run_id: str) -> Path:
        """The folder of the run."""
        return self.workspace.root / "runs" / run_id

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

    def run_ids(self) -> list[str]:
        """The ids of the run folders, sorted."""
        return sorted(p.name for p in (self.workspace.root / "runs").glob("run_*"))

    def types(self, run_id: str) -> list[EventType]:
        """The event types of the run's journal, in order."""
        return [e.type for e in self.events(run_id)]

    def forge(
        self,
        workflow: BlockDef[Any, Any] | None,
        *events: tuple[EventType, str | None, dict[str, Any]],
        input_sha256: str | None = None,
    ) -> str:
        """A run folder whose journal holds the header of a run of `workflow` (input `{"count": 3}`), then `events`.

        Each event is (type, path or None, payload), at attempt 1 when it has a path. With no `workflow` the journal
        has no header, as after a crash between its creation and `run_started`. `input_sha256` replaces the header's.
        """
        run_id = f"run_{self.ids.new_ulid()}"
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True)
        writer = JournalWriter(run_dir, self.store, self.clock, self.ids)
        if workflow is not None:
            given: dict[str, JsonValue] = {"count": 3}
            producer = Provenance(
                tool="harness", tool_version=__version__, inputs={}, started_at=self.clock.now(), duration_ms=0
            )
            stored = self.store.put("harness.run_input/1", {"value": given}, producer)
            block = {"name": workflow.name, "version": str(workflow.version), "code_sha256": workflow.code_sha256}
            header = {
                "run_id": run_id, "workflow": workflow.name, "block": block, "input_ref": stored.result_id,
                "input_sha256": input_sha256 or payload_sha256(given), "basis_ref": BASIS_REF,
                "mode": "work_on_copy", "run_class": self.run_class.value, "engine_version": __version__,
                "contract_version": CONTRACT_VERSION, "settings_sha256": "e" * 64, "servers": [], "always_ask": [],
            }  # fmt: skip
            writer.append(EventType.RUN_STARTED, header)
        for kind, path, payload in events:
            writer.append(kind, payload, path=path, attempt=None if path is None else 1)
        writer.close()
        return run_id


def make_rig(
    root: Path,
    unreleased: Mapping[str, str] | None = None,
    *,
    run_class: RunClass = RunClass.PRODUCTION,
    bases: Mapping[str, LoadedBasis] | None = None,
) -> Rig:
    """A rig whose workspace and result store are under `root`; `unreleased` names the host's unreleased tools."""
    clock = FixedClock(START_MS, 1)
    ids = SeededIdSource(b"harness", clock)
    workspace = Workspace(root=root / "ws", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    host = Host(ids, clock, workspace.root / "runs", unreleased)
    loaded = {BASIS_REF: LoadedBasis(result_id=BASIS_REF, basis=DesignBasis(template=None, fields={}))}
    loaded.update(bases or {})
    return Rig(workspace, store, clock, ids, host, FakeApprovalPort(), FakeInputPort(), run_class, bases=loaded)


def watch_closing(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> list[list[EventType]]:
    """Record the journal's event types at each `close_started` of the rig's host (the rig has one run)."""
    seen: list[list[EventType]] = []
    close = rig.host.close_started

    async def closing(host_key: str, instances: Sequence[HostInstance]) -> None:
        seen.append(rig.types(rig.run_ids()[0]))
        await close(host_key, instances)

    monkeypatch.setattr(rig.host, "close_started", closing)
    return seen


def request(
    workflow: str = "chain",
    values: Mapping[str, JsonValue] | None = None,
    *,
    basis_ref: str = BASIS_REF,
    run_class: RunClass = RunClass.PRODUCTION,
    mode: PermissionMode = PermissionMode.WORK_ON_COPY,
) -> RunRequest:
    """A request to run `workflow` with the input `values`."""
    return RunRequest(workflow=workflow, input=dict(values or {}), basis_ref=basis_ref, mode=mode, run_class=run_class)


def _hold(run_dir: str, conn: Connection) -> None:
    """The holder process: take the run lock of `run_dir`, say so, and wait until it is killed."""
    RunLock(Path(run_dir)).acquire()
    conn.send("held")
    conn.recv()


@contextmanager
def hold_lock(run_dir: Path) -> Iterator[BaseProcess]:
    """Run a process that holds the run lock of `run_dir`, once it says it does; kill and reap it on exit.

    The process is started by `spawn`, so it shares nothing with this one; the test may kill it earlier.
    """
    context = multiprocessing.get_context("spawn")
    here, there = context.Pipe()
    holder = context.Process(target=_hold, args=(str(run_dir), there))
    holder.start()
    there.close()  # so that `here.recv()` fails, instead of waiting for ever, when the holder dies before it holds
    try:
        assert here.recv() == "held"
        yield holder
    finally:
        holder.kill()
        holder.join()
        here.close()


def steps(*names: str) -> Sequence[tuple[str, dict[str, JsonValue]]]:
    """Steps that call the tools `names` in order, each with its position as the argument `n`."""
    return [(name, {"n": index}) for index, name in enumerate(names)]
