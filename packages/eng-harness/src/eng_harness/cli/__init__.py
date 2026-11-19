"""Command line of the harness (spec 0006 section 4.1): `main`, exit codes, configuration and dependencies."""

import contextlib
import os
import sys
from argparse import Namespace
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, TextIO

from eng_contract.errors import ContractError
from eng_contract.ids import Clock, IdSource, SystemClock, SystemIdSource
from eng_contract.store import ResultStore, Workspace, default_location_probe, resolve_workspace

from eng_harness._calc._port import CalcRefusal
from eng_harness.basis import FieldSpec
from eng_harness.block import Registry, WorkflowDef
from eng_harness.cli._config import HarnessConfig, load_config, resolve_config_path
from eng_harness.cli._encoding import configure_streams
from eng_harness.cli._exit import ExitCode
from eng_harness.cli._opener import open_address, write_to_terminal
from eng_harness.cli._parser import UsageError, build_parser
from eng_harness.cli._run import resume_command, run_command
from eng_harness.cli._status import doctor_command, report_command, status_command
from eng_harness.cli._stop import stop_command
from eng_harness.cli._wiring import EngineFactory, default_engine_factory
from eng_harness.decisions._policy import DecisionSettings
from eng_harness.decisions.types import DecisionPolicy
from eng_harness.doctor import run as doctor_run
from eng_harness.ports import CalcPort, DecisionPort, HostPort, RunClass, ToolPort
from eng_harness.providers import DecisionRuntime, ProvidersConfig, load_providers_config
from eng_harness.servers import ConfigError

Handler = Callable[[Namespace, "CliDeps"], int]


class HostedPorts(Protocol):
    """What entering the ports of a run gives: the tool and host ports (spec 0002 `AdapterPorts` fits)."""

    @property
    def tool_port(self) -> ToolPort:
        """The tool port."""
        ...

    @property
    def host_port(self) -> HostPort:
        """The host port."""
        ...


class RunPorts(Protocol):
    """The tool and host ports of a run as an async context manager: servers start on entry and stop on exit."""

    async def __aenter__(self) -> HostedPorts:
        """Start the servers and hand out the ports."""
        ...

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None, /
    ) -> bool | None:
        """Shut the servers down."""
        ...


class RunCalcPort(CalcPort, Protocol):
    """The engine's `CalcPort` with the preflight of spec 0003 AC11 (`HarnessCalcPort` fits)."""

    def preflight(self, calc_ids: Sequence[str]) -> Sequence[CalcRefusal]:
        """The calcs a production run may not use."""
        ...


class PortBuilder(Protocol):
    """Builds the tool and host ports of a run, given the input's model files and `visible_host` (spec 4.2.2 step 2)."""

    def __call__(
        self, config: HarnessConfig, workspace: Workspace, store: ResultStore, run_folder: Callable[[], Path],
        clock: Clock, ids: IdSource, *, files: Mapping[str, Path], visible: bool,
    ) -> RunPorts:  # fmt: skip
        """The ports, not yet entered."""
        ...


type CalcPortFactory = Callable[[HarnessConfig, Workspace, ResultStore, RunClass, Clock, IdSource], RunCalcPort]
type ProvidersLoader = Callable[[Mapping[str, Any] | None], ProvidersConfig]
type DecisionAssembler = Callable[
    [ProvidersConfig, DecisionSettings, Workspace, Mapping[str, DecisionPolicy]], DecisionRuntime
]
type DecisionPortFactory = Callable[[DecisionRuntime, HarnessConfig, Workspace, Clock, IdSource], DecisionPort]
type BasisFieldsOf = Callable[[WorkflowDef[Any, Any]], Sequence[FieldSpec]]


class DoctorRunner(Protocol):
    """Runs `eng-harness doctor` diagnostics (spec 0002 section 4.9, spec 0006 AC13)."""

    def __call__(
        self,
        config_path: Path | None,
        *,
        json_output: bool,
        show_paths: bool,
        out: TextIO | None = None,
        env: Mapping[str, str] | None = None,
    ) -> int:
        """Run the checks and return the exit code."""
        ...


@dataclass(frozen=True)
class CliDeps:
    """Collaborators of `main`; later tasks bind the remaining defaults.

    Attributes:
        stdout: Standard output.
        stderr: Standard error.
        environ: The environment.
        opener: Opens a launch address with `BROWSER` removed; returns False on failure (never `webbrowser`,
            spec 4.4.4). Defaults to the platform opener.
        handlers: Command name to handler (`run`, `resume`, `status`, `stop`, `report`, `doctor`); a command without
            one is reported as not available.
        clock: The time source of runs and results.
        ids: The id source of runs and results.
        engine_factory: Builds the engine from the full port set; defaults to the merged `Engine`.
        workflow_registry: The registered workflows; `None` until plan 0006 T18a binds it, and `run` and `resume`
            are then not available in this build.
        port_builder: Builds the tool and host ports (spec 0002 `build_ports`, plan 0006 T18b); `None` likewise.
        calc_port_factory: Builds the calc port of a run (plan 0006 T18a); `None` likewise.
        terminal_writer: Writes the launch address to the controlling terminal only; defaults to `write_to_terminal`.
        providers_loader: Validates `[providers.*]`; defaults to `load_providers_config`.
        decision_assembler: Assembles the decision runtime in step 5 (plan 0006 T18a); `None` likewise.
        point_policies: Maps each decision point name to its `DecisionPolicy` (plan 0006 T18a); `None` likewise.
        decision_port_factory: Builds the `DecisionPort` from the assembled runtime (plan 0006 T18a); `None` likewise.
        basis_fields_of: Returns the workflow's `FieldSpec` sequence for step 3 (plan 0006 T18a); `None` keeps a
            workflow with required basis fields unavailable in this build.
        doctor: Runs `eng-harness doctor`; defaults to `eng_harness.doctor.run`.
    """

    stdout: TextIO = field(default_factory=lambda: sys.stdout)
    stderr: TextIO = field(default_factory=lambda: sys.stderr)
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    opener: Callable[[str], bool] = open_address
    handlers: Mapping[str, Handler] = field(
        default_factory=lambda: {
            "run": run_command,
            "resume": resume_command,
            "status": status_command,
            "stop": stop_command,
            "report": report_command,
            "doctor": doctor_command,
        }
    )
    clock: Clock = field(default_factory=SystemClock)
    ids: IdSource = field(default_factory=lambda: SystemIdSource(SystemClock()))
    engine_factory: EngineFactory = default_engine_factory
    workflow_registry: Registry | None = None
    port_builder: PortBuilder | None = None
    calc_port_factory: CalcPortFactory | None = None
    terminal_writer: Callable[[str], bool] = write_to_terminal
    providers_loader: ProvidersLoader = load_providers_config
    decision_assembler: DecisionAssembler | None = None
    point_policies: Mapping[str, DecisionPolicy] | None = None
    decision_port_factory: DecisionPortFactory | None = None
    basis_fields_of: BasisFieldsOf | None = None
    doctor: DoctorRunner = doctor_run


def main(argv: Sequence[str] | None = None, *, deps: CliDeps | None = None) -> int:
    """Run the command line and return the process exit code (spec 4.2.3).

    Usage and configuration errors print one line on standard error and return 2.
    """
    deps = deps or CliDeps()
    configure_streams(deps.stdout, deps.stderr)
    parser = build_parser()
    try:
        with contextlib.redirect_stdout(deps.stdout), contextlib.redirect_stderr(deps.stderr):
            args, rest = parser.parse_known_args(sys.argv[1:] if argv is None else list(argv))
    except SystemExit as stop:  # argparse ends --help with exit 0
        return int(stop.code or 0)
    except UsageError as error:
        deps.stderr.write(f"{error}\n")
        return ExitCode.USAGE
    if rest and args.command != "run":  # `run` meets the generated options of its workflow (AC14)
        deps.stderr.write(f"eng-harness {args.command}: error: unrecognized arguments: {' '.join(rest)}\n")
        return ExitCode.USAGE
    args.extra = rest
    environ = dict(deps.environ)
    if args.workspace is not None:
        environ["ENG_WORKSPACE"] = str(args.workspace)
    try:
        workspace: Path | None = resolve_workspace(environ, default_location_probe()).root
    except ContractError:  # a LocalWorkspaceError leaves workspace lookup unset; handlers report or refuse it
        workspace = None
    try:
        config_path = resolve_config_path(args.config, environ, workspace)
        args.config_path = config_path
        args.config_data = load_config(config_path)
    except ConfigError as error:
        deps.stderr.write(f"eng-harness: configuration error: {error}\n")
        return ExitCode.USAGE
    handler = deps.handlers.get(args.command)
    if handler is None:
        deps.stderr.write(f"eng-harness: command {args.command} is not available in this build\n")
        return ExitCode.USAGE
    return handler(args, replace(deps, environ=environ))


__all__ = [
    "BasisFieldsOf", "CalcPortFactory", "CliDeps", "ConfigError", "DecisionAssembler", "DecisionPortFactory",
    "DoctorRunner", "ExitCode", "HarnessConfig", "HostedPorts", "PortBuilder", "ProvidersLoader", "RunCalcPort",
    "RunPorts", "main",
]  # fmt: skip
