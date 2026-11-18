"""Commands `run` and `resume` (spec 0006 sections 4.2.1, 4.2.2, 4.2.3, 4.4.8; plan 0006 T14 and T14c).

Purpose: validate the request, the answers file and the model files without creating anything, build the ports, check
the calcs of a production run, enter the ports around `Engine.start` or `Engine.resume`, remove the stop file the run
process owns, write the report and map the outcome to the exit code. Units: none. Errors: every failure is printed on
standard error and becomes an exit code; the engine's exceptions map as spec 4.2.3 says and an unexpected one is
`INTERNAL` with an error id (the journal is intact).
"""

import asyncio
import json
import logging
import re
from argparse import Namespace
from collections.abc import Awaitable, Callable, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, get_args

from eng_contract.canonical import canonical_json
from eng_contract.errors import ContractError
from eng_contract.store import ResultStore, Workspace
from pydantic import BaseModel, JsonValue, ValidationError

from eng_harness import __version__, errors
from eng_harness._kinds import HARNESS_KINDS
from eng_harness._text import sanitize_terminal
from eng_harness.basis import StoreBasisPort
from eng_harness.block import Registry, WorkflowDef
from eng_harness.cli._config import HarnessConfig
from eng_harness.cli._control import FileRunControl, remove_stop
from eng_harness.cli._exit import ExitCode, Outcome, exit_code_for, exit_code_for_error
from eng_harness.cli._options import parse_options
from eng_harness.cli._parser import UsageError
from eng_harness.cli._wiring import (
    EngineLike,
    FileAnswers,
    PageSession,
    RunIdCell,
    RunPortSet,
    engine_settings,
    open_workspace,
    release_marks,
)
from eng_harness.engine import PermissionMode, RunOutcome, RunRequest, RunStatus
from eng_harness.journal import Event, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.ports import RunClass
from eng_harness.progress import ExpectedTimes, Mode, ProgressRenderer, TerminalProgress
from eng_harness.report import ReportError, build_report, write_report
from eng_harness.servers import ConfigError

if TYPE_CHECKING:
    from eng_harness.cli import CliDeps, RunCalcPort, RunPorts

_LOG = logging.getLogger("eng_harness.cli")
_RUN_ID = re.compile(r"^run_[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_NO_BASIS = "res_" + "0" * 26  # the basis_ref of a workflow that declares no required basis field (spec Q23, interim)
_MODES: dict[str, Mode] = {"tty": "terminal", "plain": "plain", "json": "json"}


class _RefusedError(Exception):
    """The command ends before any run exists: `code` is its exit code."""

    def __init__(self, code: ExitCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _Plan:
    """What the command asks of the engine: `call` starts or resumes; `run_id` is known only for `resume`.

    `files` and `visible` are what the port builder gets from the input (spec 4.2.2 step 2); `asked` holds, at `resume`
    and only with `--answers`, each request the journal opened: its kind and whether it is answered.
    """

    workflow: str
    run_class: RunClass
    call: Callable[[EngineLike], Awaitable[RunOutcome]]
    run_id: str | None = None
    files: Mapping[str, Path] = field(default_factory=dict)
    visible: bool = False
    asked: Mapping[str, tuple[str, bool]] = field(default_factory=dict)


def run_command(args: Namespace, deps: CliDeps) -> int:
    """`run WORKFLOW`: spec 4.2.2 steps 1, 2, 4, 5 and 6."""
    return _command(args, deps, resume=False)


def resume_command(args: Namespace, deps: CliDeps) -> int:
    """`resume RUN_ID`: spec 4.2.2 steps 1, 5 and 6 with `Engine.resume`."""
    return _command(args, deps, resume=True)


def _say(deps: CliDeps, text: str) -> None:
    deps.stderr.write(f"eng-harness: {sanitize_terminal(text)}\n")


def _command(args: Namespace, deps: CliDeps, *, resume: bool) -> int:
    registry, port_builder, calc_factory = deps.workflow_registry, deps.port_builder, deps.calc_port_factory
    if registry is None or port_builder is None or calc_factory is None:
        _say(deps, f"command {args.command} is not available in this build")
        return ExitCode.USAGE
    try:
        workspace = open_workspace(deps.environ)
    except ContractError as error:  # a LocalWorkspaceError: nothing is created
        _say(deps, f"{error.detail.message} ({error.detail.hint})")
        return ExitCode.USAGE
    if resume and _RUN_ID.fullmatch(args.run_id):  # before step 1: a file written later is kept (spec 4.4.8)
        remove_stop(workspace.root / "runs" / args.run_id)
    config: HarnessConfig = args.config_data
    store = ResultStore(workspace, HARNESS_KINDS, deps.ids, deps.clock)
    try:
        plan = _resume_plan(args, workspace, registry, store) if resume else _run_plan(args, registry, config)
        answers = _answers(args, config, plan, resume=resume)
        cell = RunIdCell(workspace.root / "runs", plan.run_id)
        try:
            built = port_builder(
                config, workspace, store, cell.folder, deps.clock, deps.ids, files=plan.files, visible=plan.visible
            )
        except errors.NotImplementedGap as gap:  # gap H-G8: the usage exit is returned here (spec 4.2.2 step 2)
            raise _RefusedError(ExitCode.USAGE, gap.message) from gap
        calc = calc_factory(config, workspace, store, plan.run_class, deps.clock, deps.ids)
        # The workflow declares no calcs, so nothing is listed until it does; `run` refuses an unapproved calc at its
        # step all the same (spec 0003 AC11).
        refusals = calc.preflight(()) if not resume and plan.run_class is RunClass.PRODUCTION else []
        if refusals:
            lines = [f"{item.calc_id} is {item.status.value} ({item.code.value})" for item in refusals]
            raise _RefusedError(ExitCode.REFUSED, "calcs refused for a production run: " + "; ".join(lines))
        page = PageSession(
            config=config, store=store, runs_dir=workspace.root / "runs", cell=cell, clock=deps.clock,
            wait_timeout_s=args.wait_timeout, no_wait=args.no_wait, no_browser=args.no_browser,
            opener=deps.opener, stderr=deps.stderr, answers=answers, answers_once=not resume,
        )  # fmt: skip
        progress = _progress(args, deps, config, workspace, plan.workflow)
        try:
            parts = _PortParts(calc, page, progress)
            outcome = asyncio.run(_drive(deps, built, registry, config, workspace, store, parts, plan))
        finally:
            page.close()
            if progress is not None:
                progress.close()
        if args.answers is not None and not page.answers_used:
            _say(deps, "the --answers file was not used: no data request took it")
        return _finish(args, deps, config, workspace, store, plan.workflow, outcome)
    except _RefusedError as refused:
        _say(deps, str(refused))
        return refused.code
    except Exception as error:
        return _failed(deps, error)


@dataclass(frozen=True)
class _PortParts:
    """The ports the command builds itself (the host ports come from the port builder)."""

    calc: RunCalcPort
    page: PageSession
    progress: TerminalProgress | None


def _run_plan(args: Namespace, registry: Registry, config: HarnessConfig) -> _Plan:
    """Steps 1 and 2 of `run`: the workflow, the input and the options; nothing is created."""
    workflow = next((b for b in registry.blocks if isinstance(b, WorkflowDef) and b.name == args.workflow), None)
    if workflow is None:
        raise _RefusedError(ExitCode.REFUSED, f"workflow {args.workflow!r} is not registered")
    if workflow.required_basis:  # step 3 arrives with plan 0006 T15
        raise _RefusedError(ExitCode.USAGE, "a workflow with required basis fields is not available in this build")
    data, model = _load_input(args, workflow)
    files, visible = _model_files(model, check=True)
    request = RunRequest(
        workflow=workflow.name, input=data, basis_ref=_NO_BASIS,
        mode=PermissionMode(args.mode or config.engine.default_mode), run_class=RunClass(args.run_class),
    )  # fmt: skip
    return _Plan(workflow.name, request.run_class, lambda engine: engine.start(request), None, files, visible)


def _load_input(args: Namespace, workflow: WorkflowDef[Any, Any]) -> tuple[dict[str, JsonValue], BaseModel]:
    try:
        data = json.loads(args.input.read_text(encoding="utf-8-sig")) if args.input is not None else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _RefusedError(ExitCode.USAGE, f"cannot read the input file {args.input.name}: {error}") from error
    if not isinstance(data, dict):
        raise _RefusedError(ExitCode.USAGE, "the input file must hold one JSON object")
    data |= parse_options(workflow.options_model, args.extra)
    try:
        model = workflow.input_model.model_validate_json(canonical_json(data), strict=True)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise _RefusedError(
            ExitCode.USAGE, f"the input does not fit {workflow.name}: {where}: {first['msg']}"
        ) from error
    return data, model


def _model_files(model: BaseModel, *, check: bool) -> tuple[dict[str, Path], bool]:
    """The model files of the input (base name to path) and its `visible_host` (spec 4.2.2 step 2).

    A model file is the value of a top-level `Path` (or `Path | None`) field. `check` is true at `run`: the path must be
    absolute, name an existing file and not share its base name with another field's.
    """
    files: dict[str, Path] = {}
    owner: dict[str, str] = {}
    for name, info in type(model).model_fields.items():
        value = getattr(model, name)
        if value is None or not (info.annotation is Path or Path in get_args(info.annotation)):
            continue
        if check and not value.is_absolute():
            raise _RefusedError(ExitCode.USAGE, f"{value} is not an absolute path (input field {name})")
        if check and not value.is_file():
            raise _RefusedError(ExitCode.USAGE, f"{value} is not an existing file (input field {name})")
        if check and value.name in files:
            raise _RefusedError(ExitCode.USAGE, f"input fields {owner[value.name]} and {name} have the same base name")
        files[value.name], owner[value.name] = value, name
    return files, getattr(model, "visible_host", False) is True


def _resume_plan(args: Namespace, workspace: Workspace, registry: Registry, store: ResultStore) -> _Plan:
    """Step 1 of `resume`: the run's header and input, read before `Engine.resume` (run class, model files)."""
    run_dir = workspace.root / "runs" / args.run_id
    if not _RUN_ID.fullmatch(args.run_id) or not (run_dir / "journal.sqlite").is_file():
        raise _RefusedError(ExitCode.NOT_FOUND, f"no run {args.run_id}")
    with closing(JournalReader(run_dir)) as reader:
        header = reader.header()
        events = reader.events() if args.answers is not None else []
    asked: dict[str, tuple[str, bool]] = {}
    for event in events:
        if isinstance(event.payload, ev.InputRequested):
            asked[event.payload.request_id] = (event.payload.kind, False)
        elif isinstance(event.payload, ev.InputProvided) and event.payload.request_id in asked:
            asked[event.payload.request_id] = (asked[event.payload.request_id][0], True)
    workflow = next((b for b in registry.blocks if isinstance(b, WorkflowDef) and b.name == header.workflow), None)
    if workflow is None:
        raise _RefusedError(ExitCode.REFUSED, f"workflow {header.workflow!r} is not registered")
    try:  # the input the run was started with (engine `input_ref`); a moved original is not checked
        stored = canonical_json(store.payload(header.input_ref)["value"])
        files, visible = _model_files(workflow.input_model.model_validate_json(stored, strict=True), check=False)
    except ValidationError as error:
        raise _RefusedError(
            ExitCode.REFUSED, f"the stored input of run {args.run_id} no longer fits the workflow"
        ) from error
    run_class, call = RunClass(header.run_class), lambda engine: engine.resume(args.run_id)
    return _Plan(header.workflow, run_class, call, args.run_id, files, visible, asked)


def _answers(args: Namespace, config: HarnessConfig, plan: _Plan, *, resume: bool) -> FileAnswers | None:
    """Step 2: the `--answers` file as the function that names the object for a request (spec 4.2.1, AC46, AC64).

    `run` hands the whole object to the first data request; `resume` takes the object keyed by request id, or as it
    stands when exactly one data request is pending. Anything the journal shows is not a pending data request is
    refused here, before the engine is called.
    """
    if args.answers is None:
        return None
    try:
        given = json.loads(args.answers.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _RefusedError(ExitCode.USAGE, f"cannot read the answers file {args.answers.name}: {error}") from error
    if not isinstance(given, dict):
        raise _RefusedError(ExitCode.USAGE, "the answers file must hold one JSON object")
    payload = cast("dict[str, JsonValue]", given)
    if config.engine.engineer is None:
        raise _RefusedError(
            ExitCode.USAGE, "--answers needs the engineer's name: set [engine] engineer in harness.toml"
        )
    if not resume:
        return lambda _: payload
    pending = [rid for rid, (kind, answered) in plan.asked.items() if kind == "block" and not answered]
    if len(pending) == 1 and not payload.keys() & plan.asked.keys():
        return lambda rid: payload if rid == pending[0] else None
    for key, value in payload.items():
        if key not in plan.asked:
            raise _RefusedError(ExitCode.USAGE, f"no pending data request {key} in the run")
        kind, answered = plan.asked[key]
        if kind != "block":
            raise _RefusedError(ExitCode.USAGE, f"request {key} is not a data request: it is answered on the page")
        if answered:
            raise _RefusedError(ExitCode.USAGE, f"no pending data request {key} in the run")
        if not isinstance(value, dict):
            raise _RefusedError(ExitCode.USAGE, f"the answer for {key} must be a JSON object")
    return lambda rid: cast("Mapping[str, JsonValue] | None", payload.get(rid))


def _progress(
    args: Namespace, deps: CliDeps, config: HarnessConfig, workspace: Workspace, workflow: str
) -> TerminalProgress | None:
    if args.progress == "off":
        return None
    mode = _MODES.get(args.progress) or ("terminal" if deps.stderr.isatty() else "plain")
    renderer = ProgressRenderer(mode, ExpectedTimes.build(workspace.root, workflow, config.progress))
    return TerminalProgress(renderer, deps.stderr, mode=mode, queue_lines=config.progress.queue_lines)


async def _drive(
    deps: CliDeps, built: RunPorts, registry: Registry, config: HarnessConfig, workspace: Workspace,
    store: ResultStore, parts: _PortParts, plan: _Plan,
) -> RunOutcome:  # fmt: skip
    """Enter the ports, run the engine and leave the ports when it returns or raises (spec 4.2.2 step 5, AC71)."""
    async with built as hosted:
        ports = RunPortSet(
            tool=hosted.tool_port, host=hosted.host_port, calc=parts.calc, basis=StoreBasisPort(store),
            approvals=parts.page.approvals, inputs=parts.page.inputs, progress=parts.progress,
            run_control=FileRunControl(workspace.root / "runs"),
        )  # fmt: skip
        engine = deps.engine_factory(workspace, registry, ports, store, engine_settings(config), deps.clock, deps.ids)
        return await plan.call(engine)


def _finish(
    args: Namespace, deps: CliDeps, config: HarnessConfig, workspace: Workspace, store: ResultStore, workflow: str,
    outcome: RunOutcome,
) -> int:  # fmt: skip
    """Step 6: remove the stop file, write the report, print the summary and map the outcome to the exit code."""
    run_dir = workspace.root / "runs" / outcome.run_id
    remove_stop(run_dir)
    with closing(JournalReader(run_dir)) as reader:
        events = reader.events()
        report = None if args.no_report else _write_report(deps, reader, store, config, run_dir)
    code = exit_code_for(_outcome(outcome, events))
    titles = {
        e.payload.request_id: e.payload.title
        for e in events
        if isinstance(e.payload, ev.ApprovalRequested | ev.InputRequested)
    }
    pending = [{"request_id": rid, "title": sanitize_terminal(titles.get(rid, rid))} for rid in outcome.pending]
    escalation = None
    if outcome.escalation is not None:
        escalation = {"reason": outcome.escalation.reason, "detail": sanitize_terminal(outcome.escalation.detail)}
    if args.json:
        result = {
            "run_id": outcome.run_id, "workflow": workflow, "status": outcome.status.value, "exit_code": int(code),
            "pending": pending, "escalation": escalation, "report": None if report is None else str(report),
        }  # fmt: skip
        deps.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return code
    lines = [f"run {outcome.run_id} ({sanitize_terminal(workflow)}): {outcome.status.value}"]
    lines += [f"waiting for you: {item['title']} [{item['request_id']}]" for item in pending]
    if escalation is not None:
        lines.append(f"needs the engineer: {escalation['reason']}: {escalation['detail']}")
    if outcome.status is not RunStatus.COMPLETED and outcome.status is not RunStatus.FAILED:
        lines.append(f"resume with: eng-harness resume {outcome.run_id}")
    if report is not None:
        lines.append(f"report: {report}")
    deps.stdout.write("\n".join(lines) + "\n")
    return code


def _write_report(
    deps: CliDeps, reader: JournalReader, store: ResultStore, config: HarnessConfig, run_dir: Path
) -> Path | None:
    """`<run>/report/report.html`; a report that cannot be built is a warning, never a change of the exit code."""
    path = run_dir / "report" / "report.html"
    try:
        write_report(build_report(reader, store, release_marks(config), deps.clock, __version__), path)
    except (ReportError, ContractError) as error:
        _say(deps, f"the report was not written: {error}")
        return None
    return path


def _outcome(outcome: RunOutcome, events: list[Event]) -> Outcome:
    """The command's outcome: a pause is told apart by the reason of the journal's `run_paused`."""
    match outcome.status:
        case RunStatus.COMPLETED:
            return Outcome.COMPLETED
        case RunStatus.FAILED:
            return Outcome.FAILED
        case RunStatus.NEEDS_ENGINEER:
            return Outcome.NEEDS_ENGINEER
    last = events[-1].payload if events else None
    reason = last.reason if isinstance(last, ev.RunPaused) else "awaiting_approval"
    return {
        "stop_requested": Outcome.PAUSED_STOP_REQUESTED, "awaiting_input": Outcome.PAUSED_AWAITING_INPUT,
    }.get(reason, Outcome.PAUSED_AWAITING_APPROVAL)  # fmt: skip


def _failed(deps: CliDeps, error: Exception) -> int:
    """Print the error and return its exit code (spec 4.2.3); an unexpected one names an error id."""
    if isinstance(error, UsageError):
        deps.stderr.write(f"{sanitize_terminal(str(error))}\n")
        return ExitCode.USAGE
    if isinstance(error, ConfigError):
        _say(deps, f"configuration error: {error}")
        return ExitCode.USAGE
    if isinstance(error, errors.RunRefused | errors.RunLocked | errors.JournalIntegrityError):
        _say(deps, f"{error.code}: {error.message}")
        return exit_code_for_error(str(error.code))
    if isinstance(error, ContractError):
        _say(deps, f"{error.detail.code}: {error.detail.message}")
        return exit_code_for_error(str(error.detail.code))
    error_id = f"err_{deps.ids.new_ulid()}"
    _LOG.error("error id %s", error_id, exc_info=error)
    _say(deps, f"internal error {error_id} ({type(error).__name__}); the journal is intact and can be resumed")
    return exit_code_for(Outcome.UNEXPECTED)
