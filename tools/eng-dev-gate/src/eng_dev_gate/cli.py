"""Command line shell of ``eng-gate`` (spec section 5).

The commands are registered here; their handlers arrive in later plan tasks. A registered command
without a handler exits 2 with "not implemented", never 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence

from eng_dev_gate import __version__
from eng_dev_gate.checks.check import make_handler
from eng_dev_gate.results import ExitCode, GateError, Status, UsageError, exit_code_for

Handler = Callable[[argparse.Namespace], Status]

COMMANDS: tuple[str, ...] = (
    "check", "gate-check", "risk-floor", "test-first", "forbidden", "imports", "licenses", "ratchet",
    "secrets", "agents", "workflows", "mutation", "review", "windows-tests", "packages",
)  # fmt: skip


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eng-gate", exit_on_error=False)
    parser.add_argument("--version", action="version", version=f"eng-gate {__version__}")
    parser.add_argument("--root", default=".", help="workspace root")
    parser.add_argument("--gate-root", default=None, help="root of the policy files (base checkout)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        command = sub.add_parser(name, help=f"{name} command")
        if name == "check":
            command.add_argument("--package", default=None, help="check this workspace member")
            command.add_argument("--all", action="store_true", help="check every member")
            command.add_argument("--only", action="append", default=[], help="run only these steps (comma list)")
            command.add_argument("--skip", action="append", default=[], help="skip these steps (comma list)")
            command.add_argument("--fail-fast", action="store_true", help="stop after the first failing step")
    return parser


def _report_error(message: str, output_format: str) -> None:
    if output_format == "json":
        sys.stderr.write(json.dumps({"status": "error", "message": message}) + "\n")
    else:
        sys.stderr.write(f"eng-gate: {message}\n")


def main(argv: Sequence[str], handlers: Mapping[str, Handler] | None = None) -> int:
    """Run the gate.

    Args:
        argv: arguments after the program name.
        handlers: command name to handler; commands without one are "not implemented".

    Returns:
        The process exit code (spec AC1): 0, 1, 2 or 3. Errors go to stderr.
    """
    output_format = "text"
    try:
        args = _parser().parse_args(list(argv))
    except SystemExit as stop:  # argparse exits for --help and --version
        return int(stop.code) if isinstance(stop.code, int) else int(ExitCode.USAGE)
    except argparse.ArgumentError as error:
        _report_error(str(error), output_format)
        return int(ExitCode.USAGE)
    output_format = args.format
    handler = (handlers or {}).get(args.command)
    try:
        if handler is None:
            raise UsageError(f"command {args.command!r} is not implemented yet")
        return int(exit_code_for(handler(args)))
    except GateError as error:
        _report_error(str(error), output_format)
        return int(error.exit_code)


def run() -> None:
    """Console-script entry point: exit the process with the code of :func:`main`."""
    raise SystemExit(main(sys.argv[1:], {"check": make_handler()}))
