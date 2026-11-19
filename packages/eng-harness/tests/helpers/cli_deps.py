"""A fully set `CliDeps` over a fake engine, a fake port builder and a fake calc port (plan 0006 T14).

Staged engine (spec 0006 section 9): the run and resume tests drive the command line with a fake engine that journals
through the merged `JournalWriter`, feeds the progress sink it was given and presents its approval to the page ports
it was given, so the commands, the page and the report meet real journals while the engine itself is not under test.
`Rig.run` and `Rig.resume` call `main`; `Rig.log` lists what the fakes saw (`enter`, `start`, `exit`, ...).
"""

import contextlib
import io
import threading
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Provenance
from eng_contract.errors import ContractError
from eng_contract.ids import Clock, FixedClock, IdSource, SeededIdSource
from eng_contract.store import ResultStore, Workspace
from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError
from workflows.rig import Host

from eng_harness import __version__
from eng_harness.block import ModelFile, Registry, workflow
from eng_harness.calc import CalcStatus
from eng_harness.cli import CliDeps, DoctorRunner, main
from eng_harness.cli._config import HarnessConfig
from eng_harness.cli._wiring import RunPortSet, default_engine_factory
from eng_harness.decisions.interfaces import DecisionAnswer, DecisionCall, PendingAnswer
from eng_harness.engine import EngineSettings, RunOutcome, RunRequest, RunStatus
from eng_harness.engine._inputs import build_request, check_answer, data_schema
from eng_harness.errors import HarnessCode
from eng_harness.journal import EventType, JournalReader, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.pages import PageServer
from eng_harness.pages._answers import bound_sha256
from eng_harness.pages._security import CSRF_FIELD
from eng_harness.ports import ApprovalRequest, DecisionPort, HostPort, InputAnswer, InputRequest, RunClass, ToolPort
from eng_harness.providers import DecisionRuntime, assemble_decision_runtime
from helpers.page_client import PageClient

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
SHA = "a" * 64
PRODUCER = Provenance(tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0)
WORKFLOW = "fake_flow"


class FakeInput(BaseModel):
    """The input of the test workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    note: str = "n"
    title: str = ""
    count: int = 1


class FakeOutput(BaseModel):
    """The output of the test workflow."""

    done: bool = True


class FakeOptions(BaseModel):
    """The options model of the test workflow: `title` and `count` are options, `load` is a quantity."""

    title: str = ""
    count: int = 1
    load: float = 0.0


@workflow(name=WORKFLOW, version=1, description="A workflow for the command-line tests.", options_model=FakeOptions)
async def fake_flow(ctx: Any, inp: FakeInput) -> FakeOutput:
    """The body is never run: the fake engine stands in for the engine."""
    return FakeOutput()


NEEDS_BASIS = "needs_basis"


@workflow(
    name=NEEDS_BASIS, version=1, description="A workflow that needs a basis.", required_basis=("materials.fc_MPa",)
)
async def needs_basis(ctx: Any, inp: FakeInput) -> FakeOutput:
    """The body is never run."""
    return FakeOutput()


FILE_FLOW = "file_flow"


class FileInput(BaseModel):
    """Model files, an ordinary path and the visibility flag (spec 0006 AC67)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_file: ModelFile
    other_file: ModelFile | None = None
    ordinary_path: Path = Path("notes.txt")
    visible_host: bool = False


@workflow(name=FILE_FLOW, version=1, description="A workflow that works on model files.")
async def file_flow(ctx: Any, inp: FileInput) -> FakeOutput:
    """The body is never run."""
    return FakeOutput()


REGISTRY = Registry([fake_flow, needs_basis, file_flow])


class Asked(BaseModel):
    """The values of the data request the fake engine opens (`ctx.ask`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    count: int = 1


class Placeholder:
    """A port the fake engine never calls."""


@dataclass
class Session:
    """What a script sees: the run, its journal writer and the ports the command gave the engine."""

    engine: FakeEngine
    run_id: str
    resumed: bool
    writer: JournalWriter
    ports: RunPortSet

    def blob(self, value: int) -> str:
        """Store a value result and return its id."""
        return self.engine.store.put("harness.journal_blob/1", {"value": value}, PRODUCER).result_id

    async def approval(self, title: str, *, wait: bool) -> bool:
        """Journal an approval request (not again on a resume), show it and wait as `wait` says; True when answered."""
        preview: dict[str, JsonValue] = {
            "items": [{"id": "i1", "label": "One change", "refs": []}], "diff_ref": None, "models": [],
        }  # fmt: skip
        stored = self.engine.store.put("harness.approval_preview/1", preview, PRODUCER)
        request = ApprovalRequest(
            request_id="apr_one", run_id=self.run_id, kind="info", title=title, preview_ref=stored.result_id,
            shown_sha256=payload_sha256(preview), binding=(), items=("i1",),
        )  # fmt: skip
        self.engine.request = request
        if not self.resumed:
            self.writer.append(
                EventType.APPROVAL_REQUESTED,
                {
                    "request_id": request.request_id, "kind": request.kind, "title": title,
                    "preview_ref": request.preview_ref, "shown_sha256": request.shown_sha256, "binding": {},
                    "items": ["i1"],
                },
            )  # fmt: skip
        await self.ports.approvals.present(request)
        answer = await self.ports.approvals.answer(request.request_id, wait=wait)
        if answer is None:
            return False
        self.writer.append(
            EventType.APPROVAL_RESOLVED, answer.model_dump(mode="json") | {"by": "engineer:" + answer.by}
        )
        return True

    async def ask(self, request_id: str, *, wait: bool) -> bool:
        """Journal a data request (not again on a resume), present it and take the answer as the engine does.

        True when an answer fits the request and `Asked`; a refused or missing answer is False, the request stays open.
        """
        request = build_request(
            self.engine.ids, request_id, "block", "Give the values", data_schema(Asked.model_json_schema())
        )
        self.engine.asked.append(request)
        if not self.resumed:
            self.writer.append(
                EventType.INPUT_REQUESTED,
                {
                    "request_id": request_id, "kind": "block", "title": request.title,
                    "fields_schema_sha256": request.fields_schema_sha256,
                },
            )  # fmt: skip
        await self.ports.inputs.present(request)
        answer = await self.ports.inputs.answer(request_id, wait=wait)
        if answer is None:
            return False
        try:
            check_answer(request, answer)
            Asked.model_validate(dict(answer.values or {}))
        except ContractError, ValidationError:
            return False
        stored = self.engine.store.put("harness.journal_blob/1", {"value": 1}, PRODUCER)
        by = {"request_id": request_id, "answer_ref": stored.result_id, "by": "engineer:" + answer.by}
        self.writer.append(EventType.INPUT_PROVIDED, by)
        self.engine.answers.append(answer)
        return True

    def paused(self, reason: str, pending: tuple[str, ...] = ()) -> RunOutcome:
        """Journal `run_paused` and return the paused outcome."""
        self.writer.append(EventType.RUN_PAUSED, {"reason": reason, "request_ids": list(pending)})
        return RunOutcome(self.run_id, RunStatus.PAUSED, pending=pending)

    def completed(self) -> RunOutcome:
        """Journal `run_completed` with a stored output and return the completed outcome."""
        stored = self.engine.store.put("harness.run_output/1", {"value": {"done": True}}, PRODUCER)
        done = {"output_ref": stored.result_id, "output_sha256": payload_sha256({"done": True}), "draft": False}
        self.writer.append(EventType.RUN_COMPLETED, done)
        return RunOutcome(self.run_id, RunStatus.COMPLETED, FakeOutput())


type Script = Callable[[Session], Awaitable[RunOutcome]]


async def completes(session: Session) -> RunOutcome:
    """The run ends at once."""
    return session.completed()


def approves(*, wait: bool) -> Script:
    """The run asks for one approval, waiting for the page as `wait` says; unanswered, it pauses."""

    async def script(session: Session) -> RunOutcome:
        if await session.approval("Apply the change", wait=wait):
            return session.completed()
        return session.paused("awaiting_approval", ("apr_one",))

    return script


def asks(*request_ids: str, wait: bool = False) -> Script:
    """The run opens the data requests `request_ids` in order; at the first one without a fitting answer it pauses."""

    async def script(session: Session) -> RunOutcome:
        for request_id in request_ids:
            if not await session.ask(request_id, wait=wait):
                return session.paused("awaiting_input", (request_id,))
        return session.completed()

    return script


def opens_choice(kind: str, request_id: str) -> Script:
    """The run journals an engine request of `kind` (a choice) and pauses on it."""

    async def script(session: Session) -> RunOutcome:
        sha = "b" * 64
        body = {"request_id": request_id, "kind": kind, "title": "A choice", "fields_schema_sha256": sha}
        session.writer.append(EventType.INPUT_REQUESTED, body)
        return session.paused("awaiting_input", (request_id,))

    return script


async def pauses_on_stop(session: Session) -> RunOutcome:
    """The run pauses when the run-control port says stop (the first check between steps), else it ends."""
    control = session.ports.run_control
    if control is not None and control.stop_requested(session.run_id):
        return session.paused("stop_requested")
    return session.completed()


class FakeEngine:
    """Starts and resumes runs by script, journaling as the engine does (header, events, end)."""

    def __init__(
        self, workspace: Workspace, ports: RunPortSet, store: ResultStore, clock: FixedClock, ids: IdSource,
        script: Script, log: list[str], keep_basis_ref: bool = False,
    ) -> None:  # fmt: skip
        self.workspace, self.ports, self.store, self.clock, self.ids = workspace, ports, store, clock, ids
        self._script, self._log, self._keep_basis_ref = script, log, keep_basis_ref
        self.request: ApprovalRequest | None = None  # the approval the script showed
        self.asked: list[InputRequest] = []  # the data requests the script opened
        self.answers: list[InputAnswer] = []  # the answers the script accepted
        self.run_request: RunRequest | None = None  # what `start` was asked

    def _writer(self, run_dir: Path) -> JournalWriter:
        progress = self.ports.progress
        return JournalWriter(
            run_dir, self.store, self.clock, self.ids, on_commit=None if progress is None else progress.emit
        )

    async def start(self, request: RunRequest) -> RunOutcome:
        """Create the run folder, journal the header and run the script."""
        self._log.append("start")
        self.run_request = request
        run_id = request.run_id or f"run_{self.ids.new_ulid()}"
        run_dir = self.workspace.root / "runs" / run_id
        run_dir.mkdir(parents=True)
        base = self.store.put("harness.journal_blob/1", {"value": 0}, PRODUCER).result_id
        stored = self.store.put("harness.run_input/1", {"value": request.input}, PRODUCER)
        decision_runtime = dict(self.ports.decision.runtime_summary()) if self.ports.decision is not None else {}
        header = {
            "run_id": run_id, "workflow": request.workflow,
            "block": {"name": request.workflow, "version": "1", "code_sha256": SHA},
            "input_ref": stored.result_id, "input_sha256": payload_sha256(request.input),
            "basis_ref": request.basis_ref if self._keep_basis_ref else base,
            "mode": request.mode.value, "run_class": request.run_class.value, "engine_version": __version__,
            "contract_version": "eng-contract/1", "settings_sha256": SHA, "servers": [], "always_ask": [],
            "decision_runtime": decision_runtime,
        }  # fmt: skip
        writer = self._writer(run_dir)
        try:
            writer.append(EventType.RUN_STARTED, header)
            return await self._script(Session(self, run_id, False, writer, self.ports))
        finally:
            writer.close()

    async def resume(self, run_id: str) -> RunOutcome:
        """Journal `run_resumed` and run the script again."""
        self._log.append("resume")
        run_dir = self.workspace.root / "runs" / run_id
        with contextlib.closing(JournalReader(run_dir)) as reader:
            events = reader.events()
        head = next(e.payload for e in events if isinstance(e.payload, ev.RunHeader))
        seen = [e.payload for e in events if isinstance(e.payload, ev.RunResumed)]
        last_runtime = [head.decision_runtime, *(p.decision_runtime for p in seen if p.decision_runtime is not None)][
            -1
        ]
        runtime = dict(self.ports.decision.runtime_summary()) if self.ports.decision is not None else {}
        resumed: dict[str, JsonValue] = {
            "resume_no": max((p.resume_no for p in seen), default=0) + 1,
            "code_hash_changed": False,
            "servers": [],
            "decision_runtime": runtime if runtime != last_runtime else None,
        }
        writer = self._writer(run_dir)
        try:
            writer.append(EventType.RUN_RESUMED, resumed)
            return await self._script(Session(self, run_id, True, writer, self.ports))
        finally:
            writer.close()


class FakePorts:
    """The ports a port builder returns: entering and leaving are logged."""

    def __init__(self, log: list[str], host: Host | None = None) -> None:
        self._log = log
        self.tool_port = cast(ToolPort, host or Placeholder())
        self.host_port = cast(HostPort, host or Placeholder())

    async def __aenter__(self) -> FakePorts:
        self._log.append("enter")
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._log.append("exit")


class FakeCalc:
    """A calc port that refuses `refusals` at its preflight; the fake engine never runs a calc."""

    def __init__(self, refusals: Sequence[tuple[str, CalcStatus, HarnessCode]], run_class: RunClass) -> None:
        self.refusals, self.run_class, self.preflighted = refusals, run_class, False

    def preflight(self, calc_ids: Sequence[str]) -> list[Any]:
        """The scripted refusals."""
        from eng_harness._calc._port import CalcRefusal

        self.preflighted = True
        return [CalcRefusal(*refusal) for refusal in self.refusals]


def client_for(address: str) -> PageClient:
    """A page client for the launch address a fake opener received (it needs the port and the address only)."""
    port = int(address.split(":")[2].split("/")[0])
    return PageClient(cast(PageServer, SimpleNamespace(port=port, launch_address=address)))


class _FakeDecisionPort:
    """A `DecisionPort` over the assembled runtime summary for command-line tests."""

    def __init__(self, summary: Mapping[str, JsonValue]) -> None:
        self._summary = dict(summary)

    async def decide(self, call: DecisionCall) -> DecisionAnswer | PendingAnswer:
        raise AssertionError("the fake decision port is not called in CLI wiring tests")

    async def decide_many(self, calls: Sequence[DecisionCall]) -> list[DecisionAnswer | PendingAnswer]:
        raise AssertionError("the fake decision port is not called in CLI wiring tests")

    def runtime_summary(self) -> Mapping[str, JsonValue]:
        return self._summary


@dataclass
class Rig:
    """One command-line environment in `root`: the deps, the fakes' log and the captured streams."""

    root: Path
    script: Script = completes
    refusals: Sequence[tuple[str, CalcStatus, HarnessCode]] = ()
    opened: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    built: list[tuple[Any, ...]] = field(default_factory=list)
    on_build: Callable[[Path], None] | None = None
    open_with: Callable[[str], bool] | None = None
    terminal_writer: Callable[[str], bool] | None = None
    out: io.StringIO = field(default_factory=io.StringIO)
    err: io.StringIO = field(default_factory=io.StringIO)
    engines: list[FakeEngine] = field(default_factory=list)
    calcs: list[FakeCalc] = field(default_factory=list)
    keep_basis_ref: bool = False  # journal the request's own basis reference, which the report cannot read (Q23)
    real_engine: bool = False  # the merged `Engine` over a fake host, the page ports seen through `shown`
    shown: list[ApprovalRequest] = field(default_factory=list)  # the approvals the real engine presented
    models: list[tuple[Mapping[str, Path], bool]] = field(default_factory=list)  # `files`, `visible` of each build
    doctor: DoctorRunner | None = None

    @property
    def workspace(self) -> Path:
        """The workspace folder."""
        return self.root / "ws"

    @property
    def runs(self) -> Path:
        """The runs folder."""
        return self.workspace / "runs"

    def run_ids(self) -> list[str]:
        """The run folders that exist."""
        return sorted(p.name for p in self.runs.iterdir()) if self.runs.exists() else []

    def _opener(self, address: str) -> bool:
        self.opened.append(address)
        return True if self.open_with is None else self.open_with(address)

    def _terminal(self, text: str) -> bool:
        return False if self.terminal_writer is None else self.terminal_writer(text)

    def _decision_port(
        self, runtime: DecisionRuntime, config: HarnessConfig, workspace: Workspace, clock: Clock, ids: IdSource
    ) -> DecisionPort:
        return _FakeDecisionPort(runtime.summary)

    def _engine(
        self, workspace: Workspace, registry: Registry, ports: RunPortSet, store: ResultStore, settings: EngineSettings,
        clock: Any, ids: IdSource,
    ) -> Any:  # fmt: skip
        if self.real_engine:
            held = replace(ports, approvals=_Recording(ports.approvals, self.shown))
            return default_engine_factory(workspace, registry, held, store, settings, clock, ids)
        engine = FakeEngine(workspace, ports, store, clock, ids, self.script, self.log, self.keep_basis_ref)
        self.engines.append(engine)
        return engine

    def _port_builder(
        self, config: HarnessConfig, workspace: Workspace, store: ResultStore, run_folder: Callable[[], Path],
        clock: Any, ids: IdSource, *, files: Mapping[str, Path] | None = None, visible: bool = False,
    ) -> FakePorts:  # fmt: skip
        self.built.append((config, workspace, store, run_folder))
        self.models.append((dict(files or {}), visible))
        if self.on_build is not None:
            self.on_build(workspace.root / "runs")
        return FakePorts(
            self.log, Host(cast(SeededIdSource, ids), clock, workspace.root / "runs") if self.real_engine else None
        )

    def _calc(
        self, config: HarnessConfig, workspace: Workspace, store: ResultStore, run_class: RunClass, clock: Any,
        ids: IdSource,
    ) -> FakeCalc:  # fmt: skip
        calc = FakeCalc(self.refusals, run_class)
        self.calcs.append(calc)
        return calc

    def deps(self, **replace: Any) -> CliDeps:
        """The fully set deps; `replace` overrides a field."""
        clock = FixedClock(START_MS, 1)
        fields: dict[str, Any] = {
            "stdout": self.out, "stderr": self.err, "environ": {"ENG_WORKSPACE": str(self.workspace)},
            "opener": self._opener, "terminal_writer": self._terminal, "clock": clock,
            "ids": SeededIdSource(b"cli", clock), "engine_factory": self._engine, "workflow_registry": REGISTRY,
            "port_builder": self._port_builder, "calc_port_factory": self._calc,
            "decision_assembler": assemble_decision_runtime, "point_policies": {},
            "decision_port_factory": self._decision_port, "basis_fields_of": lambda w: w.basis_fields,
        }  # fmt: skip
        if self.doctor is not None:
            fields["doctor"] = self.doctor
        return CliDeps(**(fields | replace))

    def main(self, *argv: str, **replace: Any) -> int:
        """Call `main` with the deps; the streams hold what it wrote."""
        return main(list(argv), deps=self.deps(**replace))

    def input_file(self, text: str, encoding: str = "utf-8") -> str:
        """Write `text` as the input file and return its path."""
        path = self.root / "input.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
        return str(path)


class _Recording:
    """The page `ApprovalPort` of a real engine that keeps each request it is shown."""

    def __init__(self, inner: Any, shown: list[ApprovalRequest]) -> None:
        self._inner, self._shown = inner, shown

    async def present(self, request: ApprovalRequest) -> None:
        self._shown.append(request)
        await self._inner.present(request)

    async def answer(self, request_id: str, *, wait: bool) -> Any:
        return await self._inner.answer(request_id, wait=wait)


def approving_opener(
    rig: Rig, *, by: str = "ada", current: Callable[[], ApprovalRequest | None] | None = None
) -> Callable[[str], bool]:
    """An opener that hands the launch address to a thread, which answers the open approval with Approve.

    `current` names the approval to answer; by default it is the one the fake engine showed last.
    """
    shown = current or (lambda: rig.engines[-1].request)

    def answer(address: str) -> None:
        with contextlib.suppress(Exception):  # the command may end before the page has answered the browser
            client = client_for(address)
            client.open()
            end = time.monotonic() + 10
            while (request := shown()) is None or client.get(f"/request/{request.request_id}").status != 200:
                assert time.monotonic() < end
                time.sleep(0.01)
            form = {CSRF_FIELD: client.token(f"/request/{request.request_id}"), "shown_sha256": bound_sha256(request)}
            client.post(f"/answer/{request.request_id}", form | {"by": by, "decision": "approve"})

    def opener(address: str) -> bool:
        threading.Thread(target=answer, args=(address,), daemon=True).start()
        return True

    return opener
