"""Command line shell of ``eng-gate`` (spec section 5).

The commands are registered here; their handlers arrive in later plan tasks. A registered command
without a handler exits 2 with "not implemented", never 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from eng_dev_gate import __version__, agents, gate_root
from eng_dev_gate.checks import licenses
from eng_dev_gate.checks.check import _select_members, _workspace_root, make_handler, run_check
from eng_dev_gate.checks.gate_check import handle_gate_check
from eng_dev_gate.checks.registry import STEPS
from eng_dev_gate.checks.risk_floor import handle_risk_floor
from eng_dev_gate.report import AWAITING_TITLE, CommandResult, escape_data, render
from eng_dev_gate.results import ExitCode, GateError, Status, UsageError, exit_code_for
from eng_dev_gate.toolrun import SubprocessToolRunner
from eng_dev_gate.workspace import discover_members

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
        child = sub.add_parser(name, help=f"{name} command")
        if name == "agents":
            agents.add_arguments(child)
        if name == "gate-check":
            child.add_argument("--event", default=None, help="GitHub event file (default: GITHUB_EVENT_PATH)")
            child.add_argument("--gate-ref", default=None, help="ref of the plans and specs (default: origin/<gate>)")
        if name == "risk-floor":
            child.add_argument("--event", default=None, help="GitHub event file (default: GITHUB_EVENT_PATH)")
            child.add_argument("--gate-ref", default=None, help="ref of the plans and specs (default: origin/<gate>)")
            child.add_argument("--base", default=None, help="base commit (with --head and --body-file)")
            child.add_argument("--head", default=None, help="head commit (with --base and --body-file)")
            child.add_argument("--body-file", default=None, help="file with the pull-request body")
        if name == "packages":
            shape = child.add_mutually_exclusive_group()
            shape.add_argument("--names", action="store_true", help="print the project names, one per line")
            shape.add_argument("--json", action="store_true", help="print a JSON list of name and path")
        if name == "licenses":
            child.add_argument("--package", default=None, help="check this workspace member")
            child.add_argument("--all", action="store_true", help="check every member")
        if name in ("check", "forbidden"):
            child.add_argument("--package", default=None, help="check this workspace member")
            child.add_argument("--all", action="store_true", help="check every member")
        if name == "check":
            child.add_argument("--only", action="append", default=[], help="run only these steps (comma list)")
            child.add_argument("--skip", action="append", default=[], help="skip these steps (comma list)")
            child.add_argument("--fail-fast", action="store_true", help="stop after the first failing step")
    return parser


def _report_error(message: str, output_format: str) -> None:
    if output_format == "json":
        sys.stderr.write(json.dumps({"status": "error", "message": message}) + "\n")
    else:
        sys.stderr.write(f"eng-gate: {message}\n")


def _forbidden(args: argparse.Namespace) -> Status:
    """``forbidden``: the step of that name on the selected members, with the policy of the gate context."""
    context: gate_root.GateContext = args.gate_context
    start = Path(args.root).resolve()
    root = _workspace_root(start)
    members = _select_members(discover_members(root), start, root, args)
    steps = run_check(
        [step for step in STEPS if step.name == "forbidden"],
        root, context.policy_root, members, SubprocessToolRunner(), fail_fast=False,
    )  # fmt: skip
    result = context.with_findings(CommandResult(command="forbidden", mode=context.config.mode.value, steps=steps))
    render(result, args.format, sys.stdout, os.environ)
    return result.status


def _workflows(args: argparse.Namespace) -> Status:
    """``workflows``: the step of that name on the tree under check (no member is involved)."""
    context: gate_root.GateContext = args.gate_context
    root = _workspace_root(Path(args.root).resolve())
    steps = run_check(
        [step for step in STEPS if step.name == "workflows"],
        root,
        context.policy_root,
        [],
        SubprocessToolRunner(),
        False,
    )
    result = context.with_findings(CommandResult(command="workflows", mode=context.config.mode.value, steps=steps))
    render(result, args.format, sys.stdout, os.environ)
    return result.status


def _packages(args: argparse.Namespace) -> Status:
    """List the workspace members ordered by path: names (``--names``), JSON (``--json``) or ``name<TAB>path``.

    Standard output holds only the list, because the ``build`` job reads it; an AW09 notice goes to standard error.

    Raises:
        UsageError: the workspace root has no ``[tool.uv.workspace]`` table or a member is invalid (exit 2).
    """
    context = args.gate_context
    members = discover_members(context.root)
    for finding in context.findings:
        sys.stderr.write(f"::notice title={AWAITING_TITLE}::{escape_data(finding.text())}\n")
    if args.json:
        sys.stdout.write(json.dumps([{"name": m.name, "path": m.path} for m in members]) + "\n")
    else:
        sys.stdout.writelines(f"{m.name}\n" if args.names else f"{m.name}\t{m.path}\n" for m in members)
    return Status.PASS


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
    handler = {
        "agents": agents.handle,
        "forbidden": _forbidden,
        "gate-check": handle_gate_check,
        "packages": _packages,
        "risk-floor": handle_risk_floor,
        "workflows": _workflows,
        **(handlers or {}),
    }.get(args.command)
    try:
        if handler is None:
            raise UsageError(f"command {args.command!r} is not implemented yet")
        args.gate_context = gate_root.resolve_for(args)  # None for a command that does not judge (spec 4.16)
        return int(exit_code_for(handler(args)))
    except GateError as error:
        _report_error(str(error), output_format)
        return int(error.exit_code)


def run() -> None:
    """Console-script entry point: exit the process with the code of :func:`main`."""
    raise SystemExit(main(sys.argv[1:], {"check": make_handler(), "licenses": licenses.make_handler()}))
