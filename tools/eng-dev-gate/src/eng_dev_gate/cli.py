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
from eng_dev_gate.checks.gate_check import handle_gate_check
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
        if name == "gate-check":
            command.add_argument("--event", default=None, help="GitHub event file (default: GITHUB_EVENT_PATH)")
            command.add_argument("--gate-ref", default=None, help="ref of the plans and specs (default: origin/<gate>)")
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
    handler = {"gate-check": handle_gate_check, **(handlers or {})}.get(args.command)
    try:
        if handler is None:
            raise UsageError(f"command {args.command!r} is not implemented yet")
        return int(exit_code_for(handler(args)))
    except GateError as error:
        _report_error(str(error), output_format)
        return int(error.exit_code)


def run() -> None:
    """Console-script entry point: exit the process with the code of :func:`main`."""
    raise SystemExit(main(sys.argv[1:]))
