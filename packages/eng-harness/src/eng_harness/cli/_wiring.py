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
from typing import Protocol, TextIO

from eng_contract.ids import Clock, IdSource
from eng_contract.store import ResultStore, Workspace, default_location_probe, resolve_workspace

from eng_harness import __version__
from eng_harness.block import Registry
from eng_harness.cli._config import HarnessConfig
from eng_harness.cli._control import FileRunControl
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunOutcome, RunRequest
from eng_harness.journal import JournalReader
from eng_harness.pages import PageApprovalPort, PageInputPort, PageServer
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
    """The merged `Engine`, given the ports its `EnginePorts` holds (the decision, progress and run-control fields
    reach it with plan 0006 T14b and T16b)."""
    held = EnginePorts(
        tool=ports.tool, host=ports.host, calc=ports.calc, basis=ports.basis, approvals=ports.approvals,
        inputs=ports.inputs,
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
    (spec 4.4.4), and a failed or declined opening says that the address cannot be shown here.
    """

    def __init__(
        self, *, config: HarnessConfig, store: ResultStore, runs_dir: Path, cell: RunIdCell, clock: Clock,
        wait_timeout_s: int | None, no_wait: bool, no_browser: bool, opener: Callable[[str], bool], stderr: TextIO,
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
        self._opener, self._stderr = opener, stderr
        self._server: PageServer | None = None
        self.approvals: ApprovalPort = _Shown(self._page, self._shown, lambda request: cell.fill(request.run_id))
        self.inputs: InputPort = _Shown(PageInputPort(self._page), self._shown)

    def _shown(self) -> None:
        if self._server is not None or not self._serve:
            return
        self._server = PageServer(self._page.hub, self._settings)
        self._server.start()
        if self._browser and self._opener(self._server.launch_address):
            self._stderr.write("approval page opened in your browser\n")
        else:
            self._stderr.write(
                "the launch address cannot be shown here; run from a terminal, or use --no-wait and resume later\n"
            )

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
    """A page port that runs `before` on each request, shows it, then starts the page server."""

    def __init__(
        self, inner: _Port[Req, Ans], shown: Callable[[], None], before: Callable[[Req], None] = lambda _: None
    ) -> None:
        self._inner, self._shown, self._before = inner, shown, before

    async def present(self, request: Req) -> None:
        """Show the request on the page."""
        self._before(request)
        await self._inner.present(request)
        self._shown()

    async def answer(self, request_id: str, *, wait: bool) -> Ans | None:
        """The page's answer, as the page port gives it."""
        return await self._inner.answer(request_id, wait=wait)
