"""``test-first`` part 1 (spec 4.7 up to step 4.2): title, exemptions, commit selection, new or changed tests.

The temporary base worktree, the pytest runs, the classification (TF004, TF005, TF009, TF011) and the CI job are plan
task T17. A pull request that passes the selection is therefore a usage error here, never a pass. The title and the
body are data: they are parsed, never executed or interpolated.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from eng_dev_gate.checks.gate_check import parse_body
from eng_dev_gate.config import GateConfig
from eng_dev_gate.event import event_path, read_event
from eng_dev_gate.frontmatter import FrontMatterError, Task, parse_plan, safe_relative_path
from eng_dev_gate.gate_root import GateContext
from eng_dev_gate.gitio import Change, Git, PathNotFoundError, SubprocessGit
from eng_dev_gate.globs import matches_any
from eng_dev_gate.report import CommandResult, Finding, Severity, StepResult, render
from eng_dev_gate.results import Status, UsageError

_TITLE = re.compile(r"(feat|fix|refactor|test|docs|build|ci|chore|perf|release)(?:\([^()\s]+\))?!?: (\S.*)")
_PLAN_TASK = re.compile(r"(\S+)#(T\d+[a-z]*)")
_NONE = re.compile(r"none \(.+\)")
EXEMPT_TYPES = frozenset({"docs", "chore", "ci", "release"})
_FIELD_SEPARATOR = "\x1f"  # between the commit id and the subject in the git log format


class Commit(BaseModel):
    """A commit of the pull request: its id and its subject line."""

    model_config = ConfigDict(frozen=True)

    sha: str
    subject: str


class CommitLog(Git, Protocol):
    """The git port plus the commit list of a pull request."""

    def commits(self, base: str, head: str) -> list[Commit]:
        """Commits of ``base..head`` on the first-parent line, oldest first, without merge commits."""
        ...


class SubprocessCommitLog(SubprocessGit):
    """:class:`CommitLog` over the ``git`` executable."""

    def commits(self, base: str, head: str) -> list[Commit]:
        """Return ``git log --reverse --first-parent --no-merges base..head``.

        Raises:
            GitError: git failed.
        """
        out = self._run(
            "log",
            "-z",
            "--reverse",
            "--first-parent",
            "--no-merges",
            f"--format=%H{_FIELD_SEPARATOR}%s",
            f"{base}..{head}",
        )
        return [
            Commit(sha=sha, subject=subject)
            for sha, _, subject in (record.partition(_FIELD_SEPARATOR) for record in out.split("\0") if record)
        ]


class Selection(BaseModel):
    """The first test commit: ``paths`` are its test files still present, ``tests`` the new or changed test ids."""

    model_config = ConfigDict(frozen=True)

    commit: str
    paths: tuple[str, ...]
    tests: tuple[str, ...]  # pytest node ids ``<path>::[<Class>::]<function>``, sorted


class Outcome(BaseModel):
    """Result of :func:`evaluate`; ``selection`` is set only when there is no error and tests must run (T17)."""

    model_config = ConfigDict(frozen=True)

    findings: list[Finding] = Field(default_factory=list)
    skipped_reason: str | None = None
    selection: Selection | None = None


def _finding(code: str, message: str, severity: Severity = Severity.ERROR, path: str | None = None) -> Finding:
    return Finding(code=code, severity=severity, path=path, message=message)


def list_test_functions(source: str) -> dict[str, str]:
    """Map the qualified name of every ``test*`` function to the dump of its syntax tree.

    The functions are those at the top level or directly in a top-level ``Test*`` class. The dump leaves out
    positions, so moving a test or editing comments does not change it.

    Raises:
        SyntaxError: ``source`` does not parse.
        ValueError: ``source`` contains a null byte.
    """
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    found: dict[str, str] = {}
    for node in ast.parse(source).body:
        if isinstance(node, functions) and node.name.startswith("test"):
            found[node.name] = ast.dump(node)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for member in node.body:
                if isinstance(member, functions) and member.name.startswith("test"):
                    found[f"{node.name}::{member.name}"] = ast.dump(member)
    return found


def _changed_tests(git: Git, merge_base: str, commit: str, change: Change) -> tuple[list[str], list[Finding]]:
    """Return the ids of the tests of ``change`` that are new or differ from the merge base, and notices."""
    try:
        now = list_test_functions(git.show(commit, change.path))
    except (SyntaxError, ValueError) as error:
        message = f"{change.path} does not parse ({error}); its tests are not counted"
        return [], [_finding("TF010", message, Severity.NOTICE, change.path)]
    try:
        before = list_test_functions(git.show(merge_base, change.old_path or change.path))
    except PathNotFoundError, SyntaxError, ValueError:  # absent or unreadable at the merge base: all tests are new
        before = {}
    return [f"{change.path}::{name}" for name, dump in now.items() if before.get(name) != dump], []


def _select(merge_base: str, head: str, config: GateConfig, git: CommitLog, task: Task | None) -> Outcome:
    """Spec 4.7 step 4.1 and 4.2: the first `test:` commit, TF002, TF003, TF010 and TF008."""
    commit = next((c for c in git.commits(merge_base, head) if c.subject.startswith(("test:", "test("))), None)
    if commit is None:
        return Outcome(findings=[_finding("TF002", "no commit of the pull request has a subject starting `test:`")])
    changes = git.name_status(f"{commit.sha}^", commit.sha)
    findings = [
        _finding("TF003", f"the first test commit {commit.sha[:12]} changes a non-test file", path=p)
        for p in dict.fromkeys(p for c in changes for p in c.paths)
        if not matches_any(p, config.test_globs)
    ]
    test_files = sorted(
        (c for c in changes if c.status != "D" and matches_any(c.path, config.test_globs)), key=lambda c: c.path
    )
    tests: list[str] = []
    for change in (c for c in test_files if c.path.endswith(".py")):
        ids, notices = _changed_tests(git, merge_base, commit.sha, change)
        tests += ids
        findings += notices
    if not tests:
        findings.append(_finding("TF010", f"the first test commit {commit.sha[:12]} adds or changes no test"))
    touched = {c.path for c in test_files}
    for entry in dict.fromkeys(task.tests_first if task else []):
        if (path := entry.partition("::")[0]) not in touched:
            findings.append(_finding("TF008", f"tests_first file {path} is not in the first test commit", path=path))
    if any(f.severity is Severity.ERROR for f in findings):
        return Outcome(findings=findings)
    return Outcome(
        findings=findings,
        selection=Selection(commit=commit.sha, paths=tuple(c.path for c in test_files), tests=tuple(sorted(tests))),
    )


def evaluate(title: str, base: str, head: str, config: GateConfig, git: CommitLog, task: Task | None) -> Outcome:
    """Run steps 1 to 4.2 of spec 4.7 for a pull request.

    Args:
        title: the pull-request title (the squash-merge subject).
        base: the base commit; the merge base with ``head`` is the comparison point.
        head: the head commit.
        config: the gate configuration (``test_globs``, ``spike_globs``).
        git: the git port with the commit list.
        task: the plan task named by the pull request, if any (for TF008).

    Returns:
        The findings (TF001 to TF003, TF006 to TF008, TF010), the reason when the check is exempt, and the selection
        when tests must be run.

    Raises:
        GitError: git failed (exit 3).
    """
    parsed = _TITLE.fullmatch(title)
    if parsed is None:
        return Outcome(
            findings=[_finding("TF001", f"title {title!r} is not `<type>(<scope>)!: <text>` of Conventional Commits")]
        )
    kind = parsed[1]
    if kind in EXEMPT_TYPES:
        return Outcome(skipped_reason=f"exempt: type {kind}")
    merge_base = git.merge_base(base, head)
    paths = list(dict.fromkeys(p for c in git.name_status(merge_base, head) for p in c.paths))
    if paths and all(matches_any(p, config.spike_globs) for p in paths):
        return Outcome(skipped_reason="exempt: only spike files changed")
    if kind in ("refactor", "test"):
        wrong = [p for p in paths if matches_any(p, config.test_globs) == (kind == "refactor")]
        code, what = ("TF006", "a test file") if kind == "refactor" else ("TF007", "a non-test file")
        return Outcome(findings=[_finding(code, f"a {kind} pull request changes {what}", path=p) for p in wrong])
    return _select(merge_base, head, config, git, task)


def resolve_task(body: str, config: GateConfig, git: Git, gate_ref: str) -> Task | Finding | None:
    """Return the plan task named by the body's single ``Plan-Task:`` line, read at ``gate_ref``.

    Returns None when no task is named (no line, or ``none (<reason>)``). A task that is named but cannot be used
    (several lines, malformed, plan missing or invalid, unknown task) gives a TF008 notice: ``tests_first`` is not
    judged then, and ``gate-check`` reports the cause as GC001 to GC007.
    """
    lines = parse_body(body).plan_task
    if not lines or (len(lines) == 1 and _NONE.fullmatch(lines[0][1])):
        return None
    reason = "several Plan-Task lines" if len(lines) > 1 else "malformed Plan-Task line"
    found = _PLAN_TASK.fullmatch(lines[0][1]) if len(lines) == 1 else None
    if found and safe_relative_path(found[1]) and matches_any(found[1], config.plan_globs):
        try:
            plan = parse_plan(git.show(gate_ref, found[1]), config.limits.max_task_lines)
        except (PathNotFoundError, FrontMatterError) as error:
            reason = f"plan {found[1]} cannot be used: {error}"
        else:
            task = next((t for t in plan.tasks if t.id == found[2]), None)
            if task is not None:
                return task
            reason = f"plan {found[1]} has no task {found[2]}"
    return _finding("TF008", f"tests_first is not checked: {reason}", Severity.NOTICE)


def handle(args: argparse.Namespace) -> Status:
    """The ``test-first`` command: ``--base --head --title`` or an event file; print the result.

    Raises:
        UsageError: bad options, no event, a fork, or a pull request that passes the selection (runs: plan task T17).
        GitError: git failed.
    """
    context: GateContext = args.gate_context
    config, git = context.config, SubprocessCommitLog(context.root)
    given = (args.base, args.head, args.title)
    findings: list[Finding] = []
    if any(v is not None for v in given):
        if None in given:
            raise UsageError("--base, --head and --title go together")
        outcome = evaluate(args.title, args.base, args.head, config, git, None)
    else:
        path = event_path(args.event, os.environ)
        if path is None:
            raise UsageError("no event file: pass --event or set GITHUB_EVENT_PATH, or give --base --head --title")
        pr = read_event(path).pull_request
        if pr is None:
            outcome = Outcome(skipped_reason="push event")
        elif pr.from_fork:
            raise UsageError("pull requests from another repository are not supported")
        else:
            task = resolve_task(pr.body, config, git, args.gate_ref or f"origin/{config.gate_branch}")
            findings = [task] if isinstance(task, Finding) else []
            outcome = evaluate(
                pr.title, pr.base_sha, pr.head_sha, config, git, task if isinstance(task, Task) else None
            )
    if outcome.selection is not None:
        raise UsageError("the test runs (TF004, TF005) are not implemented yet (plan task T17)")
    step = StepResult(name="test-first", findings=[*findings, *outcome.findings], skipped_reason=outcome.skipped_reason)
    result = context.with_findings(CommandResult(command="test-first", mode=config.mode.value, steps=[step]))
    render(result, args.format, sys.stdout, os.environ)
    return result.status
