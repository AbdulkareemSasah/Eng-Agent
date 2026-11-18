"""Command line of the harness (spec 0006 section 4.1): `main`, exit codes, configuration and dependencies."""

import contextlib
import os
import sys
from argparse import Namespace
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Protocol, TextIO

from eng_contract.ids import Clock, IdSource, SystemClock, SystemIdSource
from eng_contract.store import ResultStore, Workspace

from eng_harness._calc._port import CalcRefusal
from eng_harness.block import Registry
from eng_harness.cli._config import HarnessConfig, load_config, resolve_config_path
from eng_harness.cli._encoding import configure_streams
from eng_harness.cli._exit import ExitCode
from eng_harness.cli._opener import open_address
from eng_harness.cli._parser import UsageError, build_parser
from eng_harness.cli._run import resume_command, run_command
from eng_harness.cli._wiring import EngineFactory, default_engine_factory
from eng_harness.ports import CalcPort, HostPort, RunClass, ToolPort
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


type PortBuilder = Callable[[HarnessConfig, Workspace, ResultStore, Callable[[], Path], Clock, IdSource], RunPorts]
type CalcPortFactory = Callable[[HarnessConfig, Workspace, ResultStore, RunClass, Clock, IdSource], RunCalcPort]


@dataclass(frozen=True)
class CliDeps:
    """Collaborators of `main`; later tasks add the decision assembler and the other port factories.

    Attributes:
        stdout: Standard output.
        stderr: Standard error.
        environ: The environment.
        opener: Opens a launch address with `BROWSER` removed; returns False on failure (never `webbrowser`,
            spec 4.4.4). Defaults to the platform opener.
        handlers: Command name to handler (`run` and `resume` by default); a command without one is reported as not
            available.
        clock: The time source of runs and results.
        ids: The id source of runs and results.
        engine_factory: Builds the engine from the full port set; defaults to the merged `Engine`.
        workflow_registry: The registered workflows; `None` until plan 0006 T18a binds it, and `run` and `resume`
            are then not available in this build.
        port_builder: Builds the tool and host ports (spec 0002 `build_ports`, plan 0006 T18b); `None` likewise.
        calc_port_factory: Builds the calc port of a run (plan 0006 T18a); `None` likewise.
    """

    stdout: TextIO = field(default_factory=lambda: sys.stdout)
    stderr: TextIO = field(default_factory=lambda: sys.stderr)
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    opener: Callable[[str], bool] = open_address
    handlers: Mapping[str, Handler] = field(default_factory=lambda: {"run": run_command, "resume": resume_command})
    clock: Clock = field(default_factory=SystemClock)
    ids: IdSource = field(default_factory=lambda: SystemIdSource(SystemClock()))
    engine_factory: EngineFactory = default_engine_factory
    workflow_registry: Registry | None = None
    port_builder: PortBuilder | None = None
    calc_port_factory: CalcPortFactory | None = None


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
    try:
        workspace = args.workspace or (Path(deps.environ["ENG_WORKSPACE"]) if "ENG_WORKSPACE" in deps.environ else None)
        args.config_data = load_config(resolve_config_path(args.config, deps.environ, workspace))
    except ConfigError as error:
        deps.stderr.write(f"eng-harness: configuration error: {error}\n")
        return ExitCode.USAGE
    handler = deps.handlers.get(args.command)
    if handler is None:
        deps.stderr.write(f"eng-harness: command {args.command} is not available in this build\n")
        return ExitCode.USAGE
    return handler(args, deps)


__all__ = [
    "CalcPortFactory", "CliDeps", "ConfigError", "ExitCode", "HarnessConfig", "HostedPorts", "PortBuilder",
    "RunCalcPort", "RunPorts", "main",
]  # fmt: skip
