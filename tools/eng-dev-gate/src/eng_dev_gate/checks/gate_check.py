"""``gate-check`` (spec 4.5): body parsing, plan and task, file scope and diff budget.

Part 2 is in ``gate_check_docs`` and ``codeowners``. The pull-request title and body are data, never executed.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict

from eng_dev_gate.approvals import Approvals, source_from_env
from eng_dev_gate.checks.codeowners import load_patterns
from eng_dev_gate.checks.gate_check_docs import (
    NONE_LINE,
    counted_lines,
    entry_findings,
    identity_findings,
    is_document,
    load_specs,
    none_findings,
    owner_decides,
    protected_findings,
    spec_plan_findings,
)
from eng_dev_gate.checks.ratchet import RATCHET_FILE, RatchetFile
from eng_dev_gate.config import GateConfig, Mode, awaiting_finding
from eng_dev_gate.event import PullRequest, event_path, read_event
from eng_dev_gate.frontmatter import FrontMatterError, Spec, Task, parse_plan, safe_relative_path
from eng_dev_gate.gitio import Change, Git, NumstatEntry, PathNotFoundError, SubprocessGit
from eng_dev_gate.globs import matches_any
from eng_dev_gate.report import CommandResult, Finding, Severity, StepResult, render
from eng_dev_gate.results import Status, UsageError
from eng_dev_gate.workspace import discover_members

LARGEST_FILES_SHOWN = 3  # files named in a GC009 message (presentation only)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*")
_PLAN_TASK = re.compile(r"(\S+)#(T\d+[a-z]*)")
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


def _plan_task(fields: BodyFields, config: GateConfig) -> tuple[str, str] | str | Finding:
    """Return ``(plan path, task id)`` or the ``none (<reason>)`` reason from the single line, else GC001, GC002."""
    if not fields.plan_task:
        return _error("GC001", "no `Plan-Task: <plan path>#T<n>` line in the pull request body")
    if len(fields.plan_task) > 1:
        return _error("GC002", f"{len(fields.plan_task)} Plan-Task lines; exactly one is allowed")
    value = fields.plan_task[0][1]
    if none := NONE_LINE.fullmatch(value):
        return none[1]
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
    """GC006 unless ``approved``; ``draft`` is acceptable in bootstrap mode only (AC8); AW01 if the owner decides."""
    if doc.status == "approved":
        return []
    if config.mode is Mode.BOOTSTRAP:
        needed = awaiting_finding(config, "AW01", f"{path} is a draft that needs the owner", path)
        return [needed] if owner_decides(doc) else []
    return [_error("GC006", f"status {doc.status!r} is not acceptable; it must be approved", path)]


def _ratchet_counts(text: str) -> dict[str, dict[str, int]]:
    """Counts per package directory of a baseline file; ValueError when it does not validate."""
    return {p: {str(b): n for b, n in c.items()} for p, c in RatchetFile.model_validate_json(text).counts.items()}


def _ratchet_in_scope(git: Git, base: str, head: str, anchors: set[str]) -> bool:
    """True when the baseline changes only counts of packages that have a changed file in ``anchors`` (AC10b).

    A package key added or removed without a count change, a reformat, another file version, a baseline that does
    not parse, or a count of another package (a lowering included) is not in scope. The workspace root (``.``) has no
    path ``./...`` among the anchors, so it never anchors a change.
    """
    try:
        old = _ratchet_counts(git.show(base, RATCHET_FILE))
    except PathNotFoundError:
        old = {}  # a missing baseline records nothing
    try:
        new = _ratchet_counts(git.show(head, RATCHET_FILE))
    except PathNotFoundError, ValueError:  # pydantic's ValidationError is a ValueError
        return False
    changed = [p for p in old.keys() | new.keys() if old.get(p) != new.get(p)]

    def nonzero(counts: dict[str, dict[str, int]], package: str) -> dict[str, int]:
        return {b: n for b, n in counts.get(package, {}).items() if n}  # a zero is the same as absent

    return bool(changed) and all(
        nonzero(old, p) != nonzero(new, p) and any(a.startswith(f"{p}/") for a in anchors) for p in changed
    )


def _test_markers(changes: list[Change], member_dirs: Sequence[str], git: Git, head: str, inside: set[str]) -> set[str]:
    """Empty ``__init__.py`` files added or modified under a member's ``tests/`` beside an in-scope file (AC10c)."""
    markers: set[str] = set()
    for change in changes:
        path = PurePosixPath(change.path)
        if change.status not in ("A", "M") or path.name != "__init__.py":
            continue
        if not any(change.path.startswith("tests/" if d == "." else f"{d}/tests/") for d in member_dirs):
            continue
        beside = any(q != change.path and PurePosixPath(q).parent == path.parent for q in inside)
        if beside and git.show(head, change.path) == "":
            markers.add(change.path)
    return markers


def accepted_paths(
    changes: list[Change], task: Task, plan_path: str, member_dirs: Sequence[str], git: Git, base: str, head: str
) -> tuple[list[str], set[str]]:
    """Return the changed paths (a rename counts both) and the subset inside the task's scope (also used by risk-floor).

    The ``CHANGELOG.md`` and ``docs/local-testing.md`` of a workspace member or of the plan's package folder are in
    scope when another changed file under that directory matches a glob of the task (AC10a); so is the ratchet
    baseline when it changes only counts of packages with such a file (AC10b).
    """
    paths = dict.fromkeys(p for change in changes for p in change.paths)
    inside = {p for p in paths if matches_any(p, task.files)}
    anchors = set(inside)
    plan = PurePosixPath(plan_path)
    holders = [*member_dirs, *([plan.parents[2].as_posix()] if plan.parent.parts[-2:] == ("docs", "plans") else [])]
    for directory in holders:
        prefix = "" if directory == "." else f"{directory}/"
        inside |= {
            f
            for f in (prefix + n for n in _NOTES_FILES)
            if f in paths and any(q != f and q.startswith(prefix) and q in inside for q in paths)
        }
    if RATCHET_FILE in paths and _ratchet_in_scope(git, base, head, anchors):
        inside.add(RATCHET_FILE)
    inside |= _test_markers(changes, member_dirs, git, head, anchors)
    return list(paths), inside


def _scope(
    changes: list[Change], task: Task, plan_path: str, member_dirs: Sequence[str], git: Git, base: str, head: str
) -> list[Finding]:
    """GC008 for each changed path outside the task's globs."""
    paths, inside = accepted_paths(changes, task, plan_path, member_dirs, git, base, head)
    return [_error("GC008", f"{p} matches no file glob of task {task.id}", p) for p in paths if p not in inside]


def _budget(entries: list[NumstatEntry], task: Task, config: GateConfig) -> list[Finding]:
    """GC009 when added plus deleted lines exceed the task limit; tests, generated and spike files are not counted."""
    counted = counted_lines(entries, config)
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


def _judge(
    pr: PullRequest, config: GateConfig, git: Git, gate_ref: str, member_dirs: Sequence[str], base: str,
    changes: list[Change], approvals: Approvals | None, risks: set[str],
) -> list[Finding]:  # fmt: skip
    """Body, ``none`` reasons, spec and plan pull requests, plan, task, scope and budget (steps 3 to 8)."""
    fields = parse_body(pr.body)
    findings = _work_item(fields, config)
    target = _plan_task(fields, config)
    entries = git.numstat(base, pr.head_sha)
    if any(is_document(p, config) for c in changes for p in c.paths):
        if target != "spec and plan":
            needed = "a spec and plan pull request needs `Plan-Task: none (spec and plan)`"
            findings.append(target if isinstance(target, Finding) else _error("GC011", needed))
        return [*findings, *spec_plan_findings(git, config, changes, pr.head_sha, base, approvals, risks)]
    if isinstance(target, Finding):
        return [*findings, target]
    if isinstance(target, str):
        paths = [p for c in changes for p in c.paths]
        return [*findings, *none_findings(target, paths, entries, config)]
    plan_path, task_id = target
    plan = _read(git, gate_ref, plan_path, lambda text: parse_plan(text, config.limits.max_task_lines))
    if isinstance(plan, Finding):
        return [*findings, plan]
    risks.update(plan.risk)
    findings += _status(plan, plan_path, config)
    try:
        _, specs, bad = load_specs(git, gate_ref, plan.spec)
    except PathNotFoundError:
        findings.append(
            _error("GC004", f"{plan.spec} is not on the gate branch ({gate_ref}) or holds no spec", plan.spec)
        )
    else:
        findings += [*bad, *(f for path, spec in specs.items() for f in _status(spec, path, config))]
    task = next((t for t in plan.tasks if t.id == task_id), None)
    if task is None:
        return [*findings, _error("GC007", f"plan {plan_path} defines no task {task_id}", plan_path)]
    return [
        *findings,
        *_scope(changes, task, plan_path, member_dirs, git, base, pr.head_sha),
        *_budget(entries, task, config),
    ]


def check_pull_request(
    pr: PullRequest,
    config: GateConfig,
    git: Git,
    gate_ref: str,
    member_dirs: Sequence[str] = (),
    approvals: Approvals | None = None,
) -> list[Finding]:
    """Run the checks of spec 4.5 and the body rules; findings accumulate.

    Args:
        pr: the pull request from the event file.
        config: the gate configuration (read from the gate root).
        git: the git port; ``gate_ref`` is the ref the plan and spec are read from.
        member_dirs: POSIX paths of the workspace members (for the changelog exception of the scope check).
        approvals: the approvals of the pull request, set with bootstrap off; None means bootstrap mode (AW codes).

    Returns:
        The findings (GC001 to GC016, AW02, AW03, AW06, AW08).

    Raises:
        UsageError: the pull request is from another repository, or CODEOWNERS uses syntax outside the subset.
        GitError: git failed (exit 3).
    """
    if pr.from_fork:
        raise UsageError("pull requests from another repository are not supported")
    findings, skip = entry_findings(pr, config)
    if skip:
        return findings
    base = git.merge_base(pr.base_sha, pr.head_sha)
    changes = git.name_status(base, pr.head_sha)
    paths = [p for c in changes for p in c.paths]
    patterns = load_patterns(git, (pr.base_sha, pr.head_sha))
    risks: set[str] = set()  # risk classes of the plan or documents; they set the G3 approvals
    return [
        *findings,
        *_judge(pr, config, git, gate_ref, member_dirs, base, changes, approvals, risks),
        *protected_findings(paths, patterns, config, approvals),
        *identity_findings(config, approvals, risks),
    ]


def handle_gate_check(args: argparse.Namespace) -> Status:
    """The ``gate-check`` command: read the event, check the pull request, print the result.

    Raises:
        UsageError: no event file, an unreadable event, bad configuration, a fork, or an unsupported Plan-Task.
        GitError: git failed.
    """
    root = Path(args.root)
    config: GateConfig = args.gate_context.config
    path = event_path(args.event, os.environ)
    if path is None:
        raise UsageError("no event file: pass --event or set GITHUB_EVENT_PATH")
    pr = read_event(path).pull_request
    if pr is None:
        step = StepResult(name="gate-check", skipped_reason="push event")
    else:
        gate_ref = args.gate_ref or f"origin/{config.gate_branch}"
        members = [m.path for m in discover_members(root)] if (root / "pyproject.toml").is_file() else []
        approvals = None
        if config.mode is Mode.NORMAL:
            approvals = Approvals(
                source_from_env(os.environ), config, number=pr.number, author=pr.user_login, head_sha=pr.head_sha
            )
        findings = check_pull_request(pr, config, SubprocessGit(root), gate_ref, members, approvals)
        step = StepResult(name="gate-check", findings=findings)
    judged = CommandResult(command="gate-check", mode=config.mode.value, steps=[step])
    result: CommandResult = args.gate_context.with_findings(judged)
    render(result, args.format, sys.stdout, os.environ)
    return result.status
