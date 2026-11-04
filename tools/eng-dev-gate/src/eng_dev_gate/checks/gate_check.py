"""``gate-check`` part 1 (spec 4.5): body parsing, plan and task, file scope and diff budget.

The spec and plan pull-request rule, the lane, the ``none`` reasons, protected paths, the base branch and the
``awaiting owner`` reports are plan task T14. A ``Plan-Task: none (...)`` line is therefore a usage error here, never
a pass. The pull-request title and body are data: they are parsed, never executed or interpolated.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict

from eng_dev_gate.config import GateConfig, Mode, load_gate_config
from eng_dev_gate.event import PullRequest, event_path, read_event
from eng_dev_gate.frontmatter import FrontMatterError, Spec, Task, parse_plan, parse_spec, safe_relative_path
from eng_dev_gate.gitio import Change, Git, NumstatEntry, PathNotFoundError, SubprocessGit
from eng_dev_gate.globs import matches_any
from eng_dev_gate.report import CommandResult, Finding, Severity, StepResult, render
from eng_dev_gate.results import Status, UsageError
from eng_dev_gate.workspace import discover_members

LARGEST_FILES_SHOWN = 3  # files named in a GC009 message (presentation only)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*")
_PLAN_TASK = re.compile(r"(\S+)#(T\d+[a-z]*)")
_NONE = re.compile(r"none \(.+\)")
_BOOTSTRAP_ITEM = re.compile(r"B-\d+")
_CLOSES = re.compile(r"Closes #(\d+)")
_NOTES_FILES = ("CHANGELOG.md", "docs/local-testing.md")  # in scope beside a task file (AC10a, amendment B-096)


class BodyFields(BaseModel):
    """Lines of the pull-request body as ``(line number, value)``; fenced code and HTML comments are left out."""

    model_config = ConfigDict(frozen=True)

    plan_task: list[tuple[int, str]]
    work_item: list[tuple[int, str]]
    closes: list[tuple[int, str]]


def _strip_comments(line: str, in_comment: bool) -> tuple[str, bool]:
    """Remove HTML comment spans from ``line``; return the rest and whether a comment is still open."""
    kept, pos = "", 0
    while True:
        marker = "-->" if in_comment else "<!--"
        found = line.find(marker, pos)
        if found < 0:
            return (kept if in_comment else kept + line[pos:]), in_comment
        if not in_comment:
            kept += line[pos:found]
        pos, in_comment = found + len(marker), not in_comment


def parse_body(body: str) -> BodyFields:
    """Collect the ``Plan-Task:``, ``Work-Item:`` and ``Closes #<n>`` lines; keys are case-sensitive, at line start."""
    fields: dict[str, list[tuple[int, str]]] = {"plan_task": [], "work_item": [], "closes": []}
    fence, in_comment = "", False
    for number, raw in enumerate(body.splitlines(), 1):
        if fence:
            closer = _FENCE_CLOSE.fullmatch(raw)
            if closer and closer[1][0] == fence[0] and len(closer[1]) >= len(fence):
                fence = ""
            continue
        if not in_comment and (opener := _FENCE.match(raw)):
            fence = opener.group(1)
            continue
        line, in_comment = _strip_comments(raw, in_comment)
        if line.startswith("Plan-Task:"):
            fields["plan_task"].append((number, line.removeprefix("Plan-Task:").strip()))
        elif line.startswith("Work-Item:"):
            fields["work_item"].append((number, line.removeprefix("Work-Item:").strip()))
        elif closes := _CLOSES.fullmatch(line.strip()):
            fields["closes"].append((number, closes.group(1)))
    return BodyFields(**fields)


def _error(code: str, message: str, path: str | None = None) -> Finding:
    return Finding(code=code, severity=Severity.ERROR, path=path, message=message)


def _work_item(fields: BodyFields, config: GateConfig) -> list[Finding]:
    bootstrap = config.mode is Mode.BOOTSTRAP
    if fields.closes or (bootstrap and any(_BOOTSTRAP_ITEM.fullmatch(v) for _, v in fields.work_item)):
        return []
    form = "`Work-Item: B-<digits>` or `Closes #<digits>`" if bootstrap else "`Closes #<digits>`"
    return [_error("GC003", f"no valid work item line; use {form}")]


def _plan_task(fields: BodyFields, config: GateConfig) -> tuple[str, str] | Finding:
    """Return ``(plan path, task id)`` from the single ``Plan-Task:`` line, else GC001 or GC002."""
    if not fields.plan_task:
        return _error("GC001", "no `Plan-Task: <plan path>#T<n>` line in the pull request body")
    if len(fields.plan_task) > 1:
        return _error("GC002", f"{len(fields.plan_task)} Plan-Task lines; exactly one is allowed")
    value = fields.plan_task[0][1]
    if _NONE.fullmatch(value):
        raise UsageError("Plan-Task `none (<reason>)` is not implemented yet (plan task T14)")
    found = _PLAN_TASK.fullmatch(value)
    if not found or not safe_relative_path(found[1]) or not matches_any(found[1], config.plan_globs):
        return _error("GC002", f"malformed Plan-Task {value!r}; expected `<package>/docs/plans/<file>.md#T<n>`")
    return found[1], found[2]


def _read[D: Spec](git: Git, gate_ref: str, path: str, parse: Callable[[str], D]) -> D | Finding:
    """Read ``path`` at the gate ref and parse its front matter: GC004 when absent, GC005 when invalid."""
    try:
        text = git.show(gate_ref, path)
    except PathNotFoundError:
        return _error("GC004", f"{path} is not on the gate branch ({gate_ref})", path)
    try:
        return parse(text)
    except FrontMatterError as error:
        return _error("GC005", str(error), path)


def _status(doc: Spec, path: str, config: GateConfig) -> list[Finding]:
    """GC006 unless ``approved``; ``draft`` is acceptable in bootstrap mode only (AC8)."""
    if doc.status == "approved" or config.mode is Mode.BOOTSTRAP:
        return []
    return [_error("GC006", f"status {doc.status!r} is not acceptable; it must be approved", path)]


def _scope(changes: list[Change], task: Task, plan_path: str, member_dirs: Sequence[str]) -> list[Finding]:
    """GC008 for each changed path (a rename counts both) outside the task's globs.

    The ``CHANGELOG.md`` and ``docs/local-testing.md`` of a workspace member or of the plan's package folder are in
    scope when another changed file under that directory matches a glob of the task (AC10a).
    """
    paths = dict.fromkeys(p for change in changes for p in change.paths)
    inside = {p for p in paths if matches_any(p, task.files)}
    plan = PurePosixPath(plan_path)
    holders = [*member_dirs, *([plan.parents[2].as_posix()] if plan.parent.parts[-2:] == ("docs", "plans") else [])]
    for directory in holders:
        prefix = "" if directory == "." else f"{directory}/"
        inside |= {
            f
            for f in (prefix + n for n in _NOTES_FILES)
            if f in paths and any(q != f and q.startswith(prefix) and q in inside for q in paths)
        }
    return [_error("GC008", f"{p} matches no file glob of task {task.id}", p) for p in paths if p not in inside]


def _budget(entries: list[NumstatEntry], task: Task, config: GateConfig) -> list[Finding]:
    """GC009 when added plus deleted lines exceed the task limit; tests, generated and spike files are not counted."""
    exempt = [*config.test_globs, *config.generated_globs, *config.spike_globs]
    counted = [e for e in entries if not matches_any(e.path, exempt)]
    findings = [
        Finding(
            code="GC009",
            severity=Severity.NOTICE,
            path=e.path,
            message="notice, not a budget failure: binary file counts zero",
        )
        for e in counted
        if e.binary
    ]
    total = sum(e.added + e.deleted for e in counted)
    if total > task.max_changed_lines:
        largest = sorted(counted, key=lambda e: e.added + e.deleted, reverse=True)[:LARGEST_FILES_SHOWN]
        names = ", ".join(f"{e.path} ({e.added + e.deleted})" for e in largest)
        findings.append(
            _error(
                "GC009",
                f"{total} changed lines exceed max_changed_lines {task.max_changed_lines} of task {task.id} "
                f"(BLOCKED: propose a plan change); largest: {names}",
            )
        )
    return findings


def check_pull_request(
    pr: PullRequest, config: GateConfig, git: Git, gate_ref: str, member_dirs: Sequence[str] = ()
) -> list[Finding]:
    """Run steps 4 to 7 of spec 4.5 and the body rules; findings accumulate.

    Args:
        pr: the pull request from the event file.
        config: the gate configuration (read from the gate root).
        git: the git port; ``gate_ref`` is the ref the plan and spec are read from.
        member_dirs: POSIX paths of the workspace members (for the changelog exception of the scope check).

    Returns:
        The findings (GC001 to GC009).

    Raises:
        UsageError: the pull request is from another repository, or its Plan-Task is `none (...)` (plan task T14).
        GitError: git failed (exit 3).
    """
    if pr.from_fork:
        raise UsageError("pull requests from another repository are not supported")
    fields = parse_body(pr.body)
    findings = _work_item(fields, config)
    target = _plan_task(fields, config)
    if isinstance(target, Finding):
        return [*findings, target]
    plan_path, task_id = target
    plan = _read(git, gate_ref, plan_path, lambda text: parse_plan(text, config.limits.max_task_lines))
    if isinstance(plan, Finding):
        return [*findings, plan]
    findings += _status(plan, plan_path, config)
    spec = _read(git, gate_ref, plan.spec, parse_spec)
    findings += [spec] if isinstance(spec, Finding) else _status(spec, plan.spec, config)
    task = next((t for t in plan.tasks if t.id == task_id), None)
    if task is None:
        return [*findings, _error("GC007", f"plan {plan_path} defines no task {task_id}", plan_path)]
    base = git.merge_base(pr.base_sha, pr.head_sha)
    return [
        *findings,
        *_scope(git.name_status(base, pr.head_sha), task, plan_path, member_dirs),
        *_budget(git.numstat(base, pr.head_sha), task, config),
    ]


def handle_gate_check(args: argparse.Namespace) -> Status:
    """The ``gate-check`` command: read the event, check the pull request, print the result.

    Raises:
        UsageError: no event file, an unreadable event, bad configuration, a fork, or an unsupported Plan-Task.
        GitError: git failed.
    """
    root = Path(args.root)
    config = load_gate_config(Path(args.gate_root) if args.gate_root else root)
    path = event_path(args.event, os.environ)
    if path is None:
        raise UsageError("no event file: pass --event or set GITHUB_EVENT_PATH")
    pr = read_event(path).pull_request
    if pr is None:
        step = StepResult(name="gate-check", skipped_reason="push event")
    else:
        gate_ref = args.gate_ref or f"origin/{config.gate_branch}"
        members = [m.path for m in discover_members(root)] if (root / "pyproject.toml").is_file() else []
        findings = check_pull_request(pr, config, SubprocessGit(root), gate_ref, members)
        step = StepResult(name="gate-check", findings=findings)
    result = CommandResult(command="gate-check", mode=config.mode.value, steps=[step])
    render(result, args.format, sys.stdout, os.environ)
    return result.status
