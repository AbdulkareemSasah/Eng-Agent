"""Argument parser of the command line (spec 0006 section 4.2.1, AC1).

There is no approve command and no option that answers a request: approval exists only on the page.
"""

import argparse
from pathlib import Path
from typing import NoReturn


class UsageError(Exception):
    """The command line is not valid; maps to exit code 2."""


def _absolute_dir(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(f"{self.format_usage()}{self.prog}: error: {message}")


def _shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-wait", action="store_true", help="never wait for an answer; exit 10 at the first request")
    parser.add_argument("--wait-timeout", type=int, metavar="SECONDS", help="stop waiting for an answer after this")
    parser.add_argument("--no-browser", action="store_true", help="do not open the page")
    parser.add_argument("--progress", choices=("auto", "tty", "plain", "json", "off"), default="auto")
    parser.add_argument("--json", action="store_true", help="the final result as one JSON object")
    parser.add_argument("--no-report", action="store_true", help="do not write the report")


def build_parser() -> argparse.ArgumentParser:
    """Build the parser: six commands, no abbreviations."""
    parser = _Parser(
        prog="eng-harness", description="Run engineering workflows; approval happens on the page.", allow_abbrev=False
    )
    parser.add_argument("--workspace", type=_absolute_dir, metavar="DIR", help="workspace (overrides ENG_WORKSPACE)")
    parser.add_argument("--config", type=Path, metavar="FILE", help="harness.toml")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        return commands.add_parser(name, help=help_text, allow_abbrev=False)

    run = command("run", "start a run")
    run.add_argument("workflow")
    run.add_argument("--input", type=Path, metavar="FILE")
    run.add_argument("--basis", type=Path, metavar="FILE")
    run.add_argument("--template", metavar="NAME[@VERSION]")
    run.add_argument("--mode", choices=("work_on_copy", "approve_each_write", "autonomous_logged"))
    run.add_argument("--run-class", choices=("trial", "production"), default="production")
    run.add_argument("--answers", type=Path, metavar="FILE", help="answer the first data request from a JSON object")
    _shared(run)
    resume = command("resume", "replay and continue a run")
    resume.add_argument("run_id")
    resume.add_argument("--answers", type=Path, metavar="FILE", help="answer pending data requests from JSON")
    _shared(resume)
    status = command("status", "show runs; read-only")
    status.add_argument("run_id", nargs="?")
    status.add_argument("--json", action="store_true")
    stop = command("stop", "ask a live run to pause at the next safe point")
    stop.add_argument("run_id")
    stop.add_argument("--wait", type=int, metavar="SECONDS")
    report = command("report", "build the run report")
    report.add_argument("run_id")
    report.add_argument("--out", type=Path, metavar="FILE")
    report.add_argument("--force", action="store_true")
    doctor = command("doctor", "check the installation")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--show-paths", action="store_true")
    return parser
