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
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Provenance
from eng_contract.ids import FixedClock, IdSource, SeededIdSource
from eng_contract.store import ResultStore, Workspace
from pydantic import BaseModel, ConfigDict, JsonValue

from eng_harness import __version__
from eng_harness.block import Registry, workflow
from eng_harness.calc import CalcStatus
from eng_harness.cli import CliDeps, main
from eng_harness.cli._config import HarnessConfig
from eng_harness.cli._wiring import RunPortSet
from eng_harness.engine import EngineSettings, RunOutcome, RunRequest, RunStatus
from eng_harness.errors import HarnessCode
from eng_harness.journal import EventType, JournalWriter
from eng_harness.pages import PageServer
from eng_harness.pages._answers import bound_sha256
from eng_harness.pages._security import CSRF_FIELD
from eng_harness.ports import ApprovalRequest, HostPort, RunClass, ToolPort
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


REGISTRY = Registry([fake_flow, needs_basis])


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
        script: Script, log: list[str],
    ) -> None:  # fmt: skip
        self.workspace, self.ports, self.store, self.clock, self.ids = workspace, ports, store, clock, ids
        self._script, self._log = script, log
        self.request: ApprovalRequest | None = None  # the approval the script showed
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
        header = {
            "run_id": run_id, "workflow": request.workflow,
            "block": {"name": request.workflow, "version": "1", "code_sha256": SHA},
            "input_ref": stored.result_id, "input_sha256": payload_sha256(request.input), "basis_ref": base,
            "mode": request.mode.value, "run_class": request.run_class.value, "engine_version": __version__,
            "contract_version": "eng-contract/1", "settings_sha256": SHA, "servers": [], "always_ask": [],
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
        writer = self._writer(self.workspace.root / "runs" / run_id)
        try:
            writer.append(EventType.RUN_RESUMED, {"resume_no": 1, "code_hash_changed": False, "servers": []})
            return await self._script(Session(self, run_id, True, writer, self.ports))
        finally:
            writer.close()


class FakePorts:
    """The ports a port builder returns: entering and leaving are logged."""

    def __init__(self, log: list[str]) -> None:
        self._log = log
        self.tool_port = cast(ToolPort, Placeholder())
        self.host_port = cast(HostPort, Placeholder())

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
    out: io.StringIO = field(default_factory=io.StringIO)
    err: io.StringIO = field(default_factory=io.StringIO)
    engines: list[FakeEngine] = field(default_factory=list)
    calcs: list[FakeCalc] = field(default_factory=list)

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

    def _engine(
        self, workspace: Workspace, registry: Registry, ports: RunPortSet, store: ResultStore, settings: EngineSettings,
        clock: Any, ids: IdSource,
    ) -> FakeEngine:  # fmt: skip
        engine = FakeEngine(workspace, ports, store, clock, ids, self.script, self.log)
        self.engines.append(engine)
        return engine

    def _port_builder(
        self, config: HarnessConfig, workspace: Workspace, store: ResultStore, run_folder: Callable[[], Path],
        clock: Any, ids: IdSource,
    ) -> FakePorts:  # fmt: skip
        self.built.append((config, workspace, store, run_folder))
        if self.on_build is not None:
            self.on_build(workspace.root / "runs")
        return FakePorts(self.log)

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
            "opener": self._opener, "clock": clock, "ids": SeededIdSource(b"cli", clock),
            "engine_factory": self._engine, "workflow_registry": REGISTRY, "port_builder": self._port_builder,
            "calc_port_factory": self._calc,
        }  # fmt: skip
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


def approving_opener(rig: Rig, *, by: str = "ada") -> Callable[[str], bool]:
    """An opener that hands the launch address to a thread, which answers the open approval with Approve."""

    def answer(address: str) -> None:
        with contextlib.suppress(Exception):  # the command may end before the page has answered the browser
            client = client_for(address)
            client.open()
            end = time.monotonic() + 10
            while rig.engines[-1].request is None or client.get("/request/apr_one").status != 200:
                assert time.monotonic() < end
                time.sleep(0.01)
            request = rig.engines[-1].request
            assert request is not None
            form = {CSRF_FIELD: client.token("/request/apr_one"), "shown_sha256": bound_sha256(request)}
            client.post("/answer/apr_one", form | {"by": by, "decision": "approve"})

    def opener(address: str) -> bool:
        threading.Thread(target=answer, args=(address,), daemon=True).start()
        return True

    return opener
