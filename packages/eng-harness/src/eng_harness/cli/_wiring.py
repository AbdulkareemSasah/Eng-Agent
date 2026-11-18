"""What `run` and `resume` build for the engine (spec 0006 section 4.2.2, 4.4.8; plan 0006 T14).

Purpose: the full port set of the engine factory, the default factory over the merged `Engine`, the run-id cell behind
the page's stop check and report, and the page ports of one command, whose server starts at the first request shown.
Nothing here builds an answer: the page ports belong to `eng_harness.pages`. Units: none. Errors: `ContractError` for
a workspace that cannot be used (`resolve_workspace`); the cell raises `RuntimeError` for a run id that changes.
"""

from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TextIO

from eng_contract.errors import ContractError
from eng_contract.ids import Clock, IdSource
from eng_contract.store import ResultStore, Workspace, default_location_probe, resolve_workspace
from pydantic import JsonValue

from eng_harness import __version__
from eng_harness.block import Registry
from eng_harness.cli._config import HarnessConfig
from eng_harness.cli._control import FileRunControl
from eng_harness.cli._opener import write_to_terminal
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunOutcome, RunRequest
from eng_harness.journal import JournalReader
from eng_harness.pages import PageApprovalPort, PageInputPort, PageServer, accept_answers_file
from eng_harness.pages._ports import _NO_REPORT
from eng_harness.pages._screens_approval import approval_screens, sign_off_screens
from eng_harness.pages._screens_choice import choice_screens
from eng_harness.pages._server import PageSettings
from eng_harness.ports import (
    ApprovalPort,
    BasisPort,
    CalcPort,
    DecisionPort,
    HostPort,
    InputPort,
    InputRequest,
    ProgressSink,
    RunControlPort,
    ToolPort,
)
from eng_harness.report import ReleaseMarks, build_report


@dataclass(frozen=True)
class RunPortSet:
    """Every port a run works through (spec 4.2.2 steps 2 to 5): the six of engine plan T9, then the other three."""

    tool: ToolPort
    host: HostPort
    calc: CalcPort
    basis: BasisPort
    approvals: ApprovalPort
    inputs: InputPort
    decision: DecisionPort | None = None
    progress: ProgressSink | None = None
    run_control: RunControlPort | None = None


class EngineLike(Protocol):
    """The part of `Engine` the commands call."""

    async def start(self, request: RunRequest) -> RunOutcome:
        """Start a run."""
        ...

    async def resume(self, run_id: str) -> RunOutcome:
        """Resume a run."""
        ...


type EngineFactory = Callable[
    [Workspace, Registry, RunPortSet, ResultStore, EngineSettings, Clock, IdSource], EngineLike
]


def default_engine_factory(
    workspace: Workspace, registry: Registry, ports: RunPortSet, store: ResultStore, settings: EngineSettings,
    clock: Clock, ids: IdSource,
) -> Engine:  # fmt: skip
    """The merged `Engine`, given the ports its `EnginePorts` holds (progress and run-control reach it with T16b)."""
    held = EnginePorts(
        tool=ports.tool, host=ports.host, calc=ports.calc, basis=ports.basis, approvals=ports.approvals,
        inputs=ports.inputs, decision=ports.decision,
    )  # fmt: skip
    return Engine(workspace, registry, held, store, settings, clock, ids)


def open_workspace(environ: Mapping[str, str]) -> Workspace:
    """The workspace of the environment `main` hands on (spec 4.2.1).

    Raises:
        ContractError: `PRECONDITION_FAILED` (`LocalWorkspaceError`) when none is configured or it is not local.
    """
    return resolve_workspace(environ, default_location_probe())


def engine_settings(config: HarnessConfig) -> EngineSettings:
    """The `[engine]` limits of the configuration; the engine's defaults where it sets none."""
    return EngineSettings.model_validate(config.engine.model_dump(exclude={"default_mode", "engineer"}))


def release_marks(config: HarnessConfig) -> ReleaseMarks:
    """The `[project_lane.<tool>]` records, for the report and the page (ADR-0026 section 3)."""
    return ReleaseMarks(records={tool: lane.record for tool, lane in config.project_lane.items()})


class RunIdCell:
    """The run id behind the run-folder bindings (spec 4.4.8): empty until the run id is known, then fixed."""

    def __init__(self, runs_dir: Path, known: str | None = None) -> None:
        self._runs_dir, self._run_id = runs_dir, known

    @property
    def run_id(self) -> str | None:
        """The run id, or `None` while it is not known."""
        return self._run_id

    def fill(self, run_id: str) -> None:
        """Set the run id; the same id again is a confirmation, another one a defect (`RuntimeError`)."""
        if self._run_id not in (None, run_id):
            raise RuntimeError(f"the run id changed from {self._run_id} to {run_id}")
        self._run_id = run_id

    def folder(self) -> Path:
        """The run folder; `RuntimeError` while the run id is not known."""
        if self._run_id is None:
            raise RuntimeError("the run id is not known yet")
        return self._runs_dir / self._run_id


class PageSession:
    """The page ports of one command and the page server behind them.

    The server starts when the first request is shown, never with `no_wait`; the launch address goes to `opener` only
    (spec 4.4.4), and a failed or declined opening says that the address cannot be shown here. The ports wait for the
    page unless `no_wait` (spec 4.4.5 step 2): the engine's own `wait` is ignored. `answers` (from the `--answers`
    file) names the object that answers a data request; such a request is not shown on the page.
    """

    def __init__(
        self, *, config: HarnessConfig, store: ResultStore, runs_dir: Path, cell: RunIdCell, clock: Clock,
        wait_timeout_s: int | None, no_wait: bool, no_browser: bool, opener: Callable[[str], bool], stderr: TextIO,
        answers: FileAnswers | None = None, answers_once: bool = False,
        terminal_writer: Callable[[str], bool] = write_to_terminal,
    ) -> None:  # fmt: skip
        marks, control = release_marks(config), FileRunControl(runs_dir)

        def journal() -> JournalReader:
            return JournalReader(cell.folder())

        def report() -> str:
            if cell.run_id is None or not (cell.folder() / "journal.sqlite").exists():
                return _NO_REPORT
            with closing(journal()) as reader:
                return build_report(reader, store, marks, clock, __version__)

        sign_builders, sign_checks = sign_off_screens(store, journal)
        choice_builders, choice_checks = choice_screens()

        def stop_requested() -> bool:
            return cell.run_id is not None and control.stop_requested(cell.run_id)

        self._page = self.page = PageApprovalPort(
            engineer=config.engine.engineer, stop_requested=stop_requested, report=report,
            wait_timeout_s=wait_timeout_s, ack_timeout_s=config.page.ack_timeout_s,
            builders={**approval_screens(store, journal), **sign_builders, **choice_builders}, marks=marks,
            checks={**sign_checks, **choice_checks},
        )  # fmt: skip
        self._settings = PageSettings(
            max_body_bytes=config.page.max_body_bytes, max_failed_requests=config.page.max_failed_requests
        )
        self._serve = not no_wait
        self._browser = config.page.open_browser and not no_browser
        self._opener, self._stderr, self._terminal = opener, stderr, terminal_writer
        self._server: PageServer | None = None
        wait = not no_wait
        self.approvals: ApprovalPort = _Shown(self._page, self._shown, lambda request: cell.fill(request.run_id), wait)
        self._file: _FromFile[Any] | None = None
        self.inputs: InputPort = _Shown(PageInputPort(self._page), self._shown, wait=wait)
        if answers is not None:
            self._file = _FromFile(
                self.inputs, accept_answers_file, config.engine.engineer or "", answers, once=answers_once
            )
            self.inputs = self._file

    def _shown(self) -> None:
        if self._server is not None or not self._serve:
            return
        self._server = PageServer(self._page.hub, self._settings)
        self._server.start()
        address = self._server.launch_address
        if self._browser and self._opener(address):
            self._stderr.write("approval page opened in your browser\n")
        elif not self._terminal(f"approval page: {address}"):
            self._stderr.write(
                "the launch address cannot be shown here; run from a terminal, or use --no-wait and resume later\n"
            )

    @property
    def answers_used(self) -> bool:
        """True when the `--answers` file answered a request."""
        return self._file is not None and self._file.used

    def close(self) -> None:
        """Stop the page server, if one started."""
        if self._server is not None:
            self._server.close()


class _Port[Req, Ans](Protocol):
    """A page port, whatever it answers with (this module names no answer type: spec 0006 AC2)."""

    async def present(self, request: Req, /) -> None:
        """Show the request."""
        ...

    async def answer(self, request_id: str, *, wait: bool) -> Ans | None:
        """The answer, or `None`."""
        ...


class _Shown[Req, Ans]:
    """A page port that runs `before` on each request, shows it, starts the page server and waits as `wait` says."""

    def __init__(
        self,
        inner: _Port[Req, Ans],
        shown: Callable[[], None],
        before: Callable[[Req], None] = lambda _: None,
        wait: bool = True,
    ) -> None:
        self._inner, self._shown, self._before, self._wait = inner, shown, before, wait

    async def present(self, request: Req) -> None:
        """Show the request on the page."""
        self._before(request)
        await self._inner.present(request)
        self._shown()

    async def answer(self, request_id: str, *, wait: bool) -> Ans | None:
        """The page's answer, asked with the process wait mode (the engine's `wait` is always false, spec 4.4.5)."""
        return await self._inner.answer(request_id, wait=self._wait)


type FileAnswers = Callable[[str], Mapping[str, JsonValue] | None]
"""The object of the `--answers` file that answers the request with this id, or `None`."""


class _FromFile[Ans]:
    """A page `InputPort` that answers a data request from the answers file instead of the page, once (spec 4.2.1).

    What the file may answer is decided by `accept` (`pages.accept_answers_file`); a request it refuses, and every
    request `pick` has no object for, goes to the page port unchanged. With `once` only the first request is answered.
    """

    def __init__(
        self,
        inner: _Port[InputRequest, Ans],
        accept: Callable[[InputRequest, Mapping[str, JsonValue], str], Ans],
        by: str,
        pick: FileAnswers,
        *,
        once: bool,
    ) -> None:
        self._inner, self._accept, self._by, self._pick, self._once = inner, accept, by, pick, once
        self._given: dict[str, Ans] = {}
        self._done: set[str] = set()

    @property
    def used(self) -> bool:
        """True when the file answered a request."""
        return bool(self._done)

    async def present(self, request: InputRequest) -> None:
        """Take the answer from the file, or show the request on the page."""
        rid = request.request_id
        payload = None if rid in self._done or (self._once and self._done) else self._pick(rid)
        if payload is not None:
            try:
                self._given[rid] = self._accept(request, payload, self._by)
            except ContractError:  # not a data request: it is answered on the page
                payload = None
        if payload is None:
            await self._inner.present(request)
        else:
            self._done.add(rid)

    async def answer(self, request_id: str, *, wait: bool) -> Ans | None:
        """The file's answer, once; else the page's."""
        if request_id in self._given:
            return self._given.pop(request_id)
        return await self._inner.answer(request_id, wait=wait)
