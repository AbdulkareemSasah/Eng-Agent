"""Commands `status`, `report` and `doctor` (spec 0006 sections 4.2.1, 4.2.3, 4.3, 4.6; plan 0006 T16).

Purpose: read-only run inspection (`status`), atomic HTML report and cycle-timings export (`report`), and
pass-through diagnostics (`doctor`). Units: durations and ages in milliseconds. Errors: unknown run is `NOT_FOUND`
(6), tampered journal is `JOURNAL_INTEGRITY` (5), workspace or configuration refusal is `USAGE` (2).
"""

import json
import re
from argparse import Namespace
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eng_contract.errors import ContractError
from eng_contract.store import ResultStore, Workspace

from eng_harness import __version__
from eng_harness._kinds import HARNESS_KINDS
from eng_harness._text import format_duration_ms, format_timestamp, sanitize_terminal
from eng_harness.cli._config import HarnessConfig
from eng_harness.cli._exit import ExitCode, exit_code_for_error
from eng_harness.cli._wiring import open_workspace, release_marks
from eng_harness.errors import JournalIntegrityError
from eng_harness.journal import JournalReader
from eng_harness.progress import Liveness, read_liveness
from eng_harness.report import ReportError, build_report, edit_cycle_timings, write_cycle_timings, write_report
from eng_harness.servers import ConfigError

if TYPE_CHECKING:
    from eng_harness.cli import CliDeps

RUN_ID_PATTERN = re.compile(r"^run_[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_LIST_LIMIT = 20


def say_error(deps: CliDeps, text: str) -> None:
    """Write a sanitized error line to standard error."""
    deps.stderr.write(f"eng-harness: {sanitize_terminal(text)}\n")


def require_workspace(deps: CliDeps) -> Workspace | None:
    """Resolve the workspace, printing the contract error and remedy on `LocalWorkspaceError` (AC71)."""
    try:
        return open_workspace(deps.environ)
    except ContractError as error:
        say_error(deps, f"{error.detail.message} ({error.detail.hint})")
        return None


def existing_run_dir(deps: CliDeps, workspace: Workspace, run_id: str) -> Path | None:
    """Return the run folder when `run_id` is valid and holds a journal; otherwise print and return `None`."""
    run_dir = workspace.root / "runs" / run_id
    if RUN_ID_PATTERN.fullmatch(run_id) is None or not (run_dir / "journal.sqlite").is_file():
        say_error(deps, f"no run {run_id}")
        return None
    return run_dir


def _next_command(status: str, run_id: str) -> str:
    if status in {"COMPLETED", "FAILED"}:
        return f"eng-harness report {run_id}"
    if status == "RUNNING":
        return f"eng-harness stop {run_id}"
    return f"eng-harness resume {run_id}"


def _heartbeat_summary(liveness: Liveness) -> tuple[str | None, str]:
    if liveness.state == "not_running" or liveness.age_ms is None:
        return None, "not running"
    age = format_duration_ms(liveness.age_ms)
    message = "no heartbeat, possibly stuck" if liveness.state == "no_heartbeat" else "running"
    return message, f"{message} (age {age})"


def _status_list(deps: CliDeps, workspace: Workspace, *, as_json: bool) -> int:
    runs_dir = workspace.root / "runs"
    rows: list[tuple[str, str, dict[str, Any]]] = []
    if runs_dir.is_dir():
        candidates = [
            p
            for p in runs_dir.iterdir()
            if p.is_dir() and RUN_ID_PATTERN.fullmatch(p.name) is not None and (p / "journal.sqlite").is_file()
        ]
        for run_dir in sorted(candidates, key=lambda p: p.name, reverse=True):
            try:
                with closing(JournalReader(run_dir)) as reader:
                    view = reader.run()
                    row: dict[str, Any] = {
                        "run_id": view.run_id,
                        "workflow": sanitize_terminal(view.workflow),
                        "status": view.status,
                        "started_at": format_timestamp(view.started_at),
                        "ended_at": format_timestamp(view.ended_at) if view.ended_at is not None else None,
                    }
                    rows.append((view.started_at, view.run_id, row))
            except JournalIntegrityError as error:
                rows.append(
                    (
                        "",
                        run_dir.name,
                        {
                            "run_id": run_dir.name,
                            "workflow": "",
                            "status": "JOURNAL_INTEGRITY",
                            "started_at": None,
                            "ended_at": None,
                            "error": sanitize_terminal(error.message),
                        },
                    )
                )
    rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
    recent = [item[2] for item in rows[:_LIST_LIMIT]]
    if as_json:
        deps.stdout.write(json.dumps(recent, ensure_ascii=False) + "\n")
        return ExitCode.OK
    if not recent:
        deps.stdout.write("no runs\n")
        return ExitCode.OK
    lines = [
        f"{item['run_id']} | {item['workflow'] or '-'} | {item['status']} | {item['started_at'] or '-'}"
        for item in recent
    ]
    deps.stdout.write("\n".join(lines) + "\n")
    return ExitCode.OK


def status_command(args: Namespace, deps: CliDeps) -> int:
    """`status [RUN_ID]`: read-only status of the 20 most recent runs or one run (spec 0006 AC11, AC18)."""
    workspace = require_workspace(deps)
    if workspace is None:
        return ExitCode.USAGE
    if args.run_id is None:
        return _status_list(deps, workspace, as_json=bool(args.json))
    run_dir = existing_run_dir(deps, workspace, args.run_id)
    if run_dir is None:
        return ExitCode.NOT_FOUND
    config: HarnessConfig = args.config_data
    try:
        with closing(JournalReader(run_dir)) as reader:
            view = reader.run()
            steps = reader.steps()
            requests = reader.requests()
    except JournalIntegrityError as error:
        say_error(deps, f"{error.code}: {error.message}")
        return ExitCode.JOURNAL_INTEGRITY
    liveness = read_liveness(
        run_dir,
        now_ms=deps.clock.now_ms(),
        heartbeat_s=config.progress.heartbeat_s,
        stale_after_heartbeats=config.progress.stale_after_heartbeats,
    )
    hb_message, hb_text = _heartbeat_summary(liveness)
    running_steps = [
        {
            "path": sanitize_terminal(s.path),
            "kind": s.kind,
            "name": sanitize_terminal(s.name),
            "started_at": format_timestamp(s.started_at),
        }
        for s in steps
        if s.status == "running"
    ]
    pending = [
        {"request_id": r.request_id, "kind": r.kind, "title": sanitize_terminal(r.title)}
        for r in requests
        if r.resolution is None
    ]
    escalation = (
        {"reason": view.escalation.reason, "detail": sanitize_terminal(view.escalation.detail)}
        if view.escalation is not None
        else None
    )
    next_cmd = _next_command(view.status, view.run_id)
    payload: dict[str, Any] = {
        "run_id": view.run_id,
        "workflow": sanitize_terminal(view.workflow),
        "mode": view.mode,
        "run_class": view.run_class,
        "status": view.status,
        "started_at": format_timestamp(view.started_at),
        "ended_at": format_timestamp(view.ended_at) if view.ended_at is not None else None,
        "steps_in_progress": running_steps,
        "pending": pending,
        "escalation": escalation,
        "heartbeat": {
            "state": liveness.state,
            "age_ms": liveness.age_ms,
            "message": hb_message,
            "step": sanitize_terminal(liveness.step) if liveness.step is not None else None,
            "seq": liveness.seq,
        },
        "next_command": next_cmd,
    }
    if args.json:
        deps.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return ExitCode.OK
    lines = [
        f"run_id: {payload['run_id']}",
        f"workflow: {payload['workflow']} ({payload['mode']}, {payload['run_class']})",
        f"status: {payload['status']}",
        f"started: {payload['started_at']}",
    ]
    if payload["ended_at"] is not None:
        lines.append(f"ended: {payload['ended_at']}")
    lines.append(f"heartbeat: {hb_text}")
    if running_steps:
        for step in running_steps:
            lines.append(f"step in progress: {step['kind']} {step['name']} [{step['path']}]")
    else:
        lines.append("step in progress: none")
    if pending:
        for req in pending:
            lines.append(f"pending: {req['kind']} {req['title']} [{req['request_id']}]")
    else:
        lines.append("pending: none")
    if escalation is not None:
        lines.append(f"escalation: {escalation['reason']}: {escalation['detail']}")
    else:
        lines.append("escalation: none")
    lines.append(f"next: {next_cmd}")
    deps.stdout.write("\n".join(lines) + "\n")
    return ExitCode.OK


def report_command(args: Namespace, deps: CliDeps) -> int:
    """`report RUN_ID`: write HTML report atomically and cycle timings when present (spec 0006 AC12, AC69)."""
    workspace = require_workspace(deps)
    if workspace is None:
        return ExitCode.USAGE
    run_dir = existing_run_dir(deps, workspace, args.run_id)
    if run_dir is None:
        return ExitCode.NOT_FOUND
    target: Path = args.out if args.out is not None else run_dir / "report" / "report.html"
    config: HarnessConfig = args.config_data
    store = ResultStore(workspace, HARNESS_KINDS, deps.ids, deps.clock)
    try:
        with closing(JournalReader(run_dir)) as reader:
            if args.out is not None and target.exists() and not args.force:
                say_error(deps, f"output file already exists: {target.name} (use --force to overwrite)")
                return ExitCode.USAGE
            if target.is_dir():
                say_error(deps, f"output path is a directory: {target.name}")
                return ExitCode.USAGE
            html = build_report(reader, store, release_marks(config), deps.clock, __version__)
            write_report(html, target)
            timings = edit_cycle_timings(reader, store)
            if timings.cycles:
                write_cycle_timings(timings, run_dir / "report" / "cycle-timings.json")
    except JournalIntegrityError as error:
        say_error(deps, f"{error.code}: {error.message}")
        return ExitCode.JOURNAL_INTEGRITY
    except ContractError as error:
        say_error(deps, f"{error.detail.code}: {error.detail.message}")
        return exit_code_for_error(str(error.detail.code))
    except ReportError as error:
        say_error(deps, f"cannot build the report: {error}")
        return ExitCode.INTERNAL
    deps.stdout.write(f"report: {target}\n")
    return ExitCode.OK


def doctor_command(args: Namespace, deps: CliDeps) -> int:
    """`doctor`: call `deps.doctor` with options, config path and environment (spec 0006 AC13)."""
    try:
        return deps.doctor(
            args.config_path,
            json_output=bool(args.json),
            show_paths=bool(args.show_paths),
            out=deps.stdout,
            env=deps.environ,
        )
    except ConfigError as error:
        say_error(deps, f"configuration error: {error}")
        return ExitCode.USAGE
