"""Command line of the harness (spec 0006 section 4.1): `main`, exit codes, configuration and dependencies."""

import contextlib
import os
import sys
from argparse import Namespace
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from eng_harness.cli._config import HarnessConfig, load_config, resolve_config_path
from eng_harness.cli._encoding import configure_streams
from eng_harness.cli._exit import ExitCode
from eng_harness.cli._parser import UsageError, build_parser
from eng_harness.servers import ConfigError

Handler = Callable[[Namespace, "CliDeps"], int]


@dataclass(frozen=True)
class CliDeps:
    """Collaborators of `main`; later tasks add the registry, port factories, clock and decision assembler.

    Attributes:
        stdout: Standard output.
        stderr: Standard error.
        environ: The environment.
        opener: Opens a launch address; returns False on failure (never `webbrowser`, spec 4.4.4). None until the
            launch-address opener arrives (plan 0006 T3b).
        handlers: Command name to handler; a command without one is reported as not available.
    """

    stdout: TextIO = field(default_factory=lambda: sys.stdout)
    stderr: TextIO = field(default_factory=lambda: sys.stderr)
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    opener: Callable[[str], bool] | None = None
    handlers: Mapping[str, Handler] = field(default_factory=dict)


def main(argv: Sequence[str] | None = None, *, deps: CliDeps | None = None) -> int:
    """Run the command line and return the process exit code (spec 4.2.3).

    Usage and configuration errors print one line on standard error and return 2.
    """
    deps = deps or CliDeps()
    configure_streams(deps.stdout, deps.stderr)
    parser = build_parser()
    try:
        with contextlib.redirect_stdout(deps.stdout), contextlib.redirect_stderr(deps.stderr):
            args = parser.parse_args(sys.argv[1:] if argv is None else list(argv))
    except SystemExit as stop:  # argparse ends --help with exit 0
        return int(stop.code or 0)
    except UsageError as error:
        deps.stderr.write(f"{error}\n")
        return ExitCode.USAGE
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


__all__ = ["CliDeps", "ConfigError", "ExitCode", "HarnessConfig", "main"]
