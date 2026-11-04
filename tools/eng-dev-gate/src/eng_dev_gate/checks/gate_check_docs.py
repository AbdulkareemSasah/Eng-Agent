"""``gate-check`` part 2 (spec 4.5 steps 1, 2, 3, 8 and 9): base branch, lane, ``none`` reasons, spec and plan pull
requests and protected paths. The approvals port is plan task T24, so verification with bootstrap off fails closed.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from pathlib import PurePosixPath

from eng_dev_gate.checks.codeowners import protected_paths
from eng_dev_gate.config import GateConfig, Mode, awaiting_finding
from eng_dev_gate.event import PullRequest
from eng_dev_gate.frontmatter import FrontMatterError, Plan, Spec, parse_plan, parse_spec, uncovered_criteria
from eng_dev_gate.gitio import Change, Git, NumstatEntry, PathNotFoundError
from eng_dev_gate.globs import matches_any
from eng_dev_gate.report import Finding, Severity

NONE_LINE = re.compile(r"none \((.+)\)")
TRIVIAL_MAX_LINES = 10  # changed counted lines of a `trivial` change: process/01 section 2
PATHS_SHOWN = 10  # paths named in one message (presentation only)
_LANE = re.compile(r"lane/[0-9]+-[a-z0-9-]+")
_TRIVIAL_EXCLUDED_DIRS = frozenset({"src", "tests", ".gate", ".github"})
_CONFIG_SUFFIXES = frozenset({".toml", ".yml", ".yaml", ".json", ".ini", ".cfg"})  # with names holding `schema`
_RELEASE_FILES = frozenset({"pyproject.toml", "CHANGELOG.md", "uv.lock"})
_NOT_VERIFIED = "verification through the approvals port is not implemented (plan task T24)"


def error(code: str, message: str, path: str | None = None) -> Finding:
    """Return an error finding."""
    return Finding(code=code, severity=Severity.ERROR, path=path, message=message)


def counted_lines(entries: Sequence[NumstatEntry], config: GateConfig) -> list[NumstatEntry]:
    """The entries that count against a budget: not tests, generated files or spike files (spec 4.5 step 7)."""
    exempt = [*config.test_globs, *config.generated_globs, *config.spike_globs]
    return [e for e in entries if not matches_any(e.path, exempt)]


def _shown(paths: Sequence[str]) -> str:
    more = f" and {len(paths) - PATHS_SHOWN} more" if len(paths) > PATHS_SHOWN else ""
    return ", ".join(paths[:PATHS_SHOWN]) + more


def entry_findings(pr: PullRequest, config: GateConfig) -> tuple[list[Finding], bool]:
    """Steps 1 and 2: the base branch (GC013, AW06) and the project lane (GC012).

    Returns:
        The findings and whether the remaining checks are skipped.
    """
    gate = config.gate_branch
    if config.mode is Mode.BOOTSTRAP and pr.head_ref == gate and pr.base_ref == config.main_branch:
        message = f"the merge of {gate} into {config.main_branch} is the owner's after local tests"
        return [awaiting_finding(config, "AW06", message)], True
    findings = (
        [error("GC013", f"base branch {pr.base_ref!r} is not the gate branch {gate!r}")] if pr.base_ref != gate else []
    )
    if not pr.head_ref.startswith("lane/"):
        return findings, False
    if not _LANE.fullmatch(pr.head_ref):
        findings.append(
            error("GC012", f"lane branch {pr.head_ref!r} is not `lane/<issue>-<slug>` (lowercase, digits, -)")
        )
    elif not pr.draft:
        findings.append(error("GC012", "a project lane pull request must be a draft; it never reaches the gate branch"))
    else:
        message = "project lane: draft pull request; the remaining checks run in the release lane"
        findings.append(Finding(code="GC012", severity=Severity.NOTICE, message=message))
    return findings, True


def _fits(reason: str, paths: Sequence[str], lines: int, config: GateConfig) -> bool:
    parts = [PurePosixPath(p) for p in paths]
    match reason:
        case "spec and plan":
            return all(matches_any(p, [*config.spec_globs, *config.plan_globs]) for p in paths)
        case "trivial":
            plain = not any(
                _TRIVIAL_EXCLUDED_DIRS.intersection(x.parts)
                or x.suffix in _CONFIG_SUFFIXES
                or "schema" in x.name.lower()
                for x in parts
            )
            return plain and lines <= TRIVIAL_MAX_LINES
        case "hub documents":
            return all(p.startswith("design/") for p in paths)
        case "spike":
            return all(matches_any(p, config.spike_globs) for p in paths)
        case "release":
            owners = {x.parent for x in parts if x.name != "uv.lock"}
            return all(x.name in _RELEASE_FILES for x in parts) and len(owners) <= 1
        case _:
            return False


def none_findings(
    reason: str, paths: Sequence[str], entries: Sequence[NumstatEntry], config: GateConfig
) -> list[Finding]:
    """Step 3: GC011 unless ``reason`` is in the table of spec 4.5 and the changed ``paths`` fit it."""
    lines = sum(e.added + e.deleted for e in counted_lines(entries, config))
    if _fits(reason.strip(), paths, lines, config):
        return []
    return [error("GC011", f"`Plan-Task: none ({reason})` is not an allowed reason or the diff does not fit it")]


def owner_decides(doc: Spec) -> bool:
    """Whether process/01 section 5 gives the approval to the owner: a spec of risk r1 or r2, a large plan."""
    return doc.size == "large" if isinstance(doc, Plan) else bool({"r1", "r2"}.intersection(doc.risk))


def is_document(path: str, config: GateConfig) -> bool:
    """Whether ``path`` is a spec or a plan."""
    return matches_any(path, [*config.spec_globs, *config.plan_globs])


def _check_document(git: Git, config: GateConfig, path: str, head: str, base: str) -> list[Finding]:
    """GC005, GC004, GC016 and GC014 or GC015 for one changed spec or plan, read at the head commit."""
    plan = matches_any(path, config.plan_globs)
    parse: Callable[[str], Spec] = (lambda t: parse_plan(t, config.limits.max_task_lines)) if plan else parse_spec
    try:
        doc = parse(git.show(head, path))
    except FrontMatterError as problem:
        return [error("GC005", str(problem), path)]
    try:
        was = parse(git.show(base, path)).status
    except PathNotFoundError, FrontMatterError:
        was = None
    findings: list[Finding] = []
    if doc.status == "approved" and was != "approved":
        if config.mode is Mode.BOOTSTRAP:
            findings.append(
                error("GC014", "`status: approved` is the owner's act and cannot be set by a pull request", path)
            )
        else:
            findings.append(error("GC015", f"approvals of process/01 section 5 are required; {_NOT_VERIFIED}", path))
    if isinstance(doc, Plan):
        try:
            missing = uncovered_criteria(doc, git.show(head, doc.spec))
        except PathNotFoundError:
            return [*findings, error("GC004", f"{doc.spec} named by the plan is not in the pull request head", path)]
        if missing:
            findings.append(error("GC016", f"no task covers {', '.join(missing)}", path))
    return findings


def spec_plan_findings(git: Git, config: GateConfig, changes: Sequence[Change], head: str, base: str) -> list[Finding]:
    """Step 8: GC010 for any other file, then the front matter, coverage and status of each changed document."""
    paths = list(dict.fromkeys(p for c in changes for p in c.paths))
    findings = [
        error("GC010", "a spec or plan pull request changes only specs and plans", p)
        for p in paths
        if not is_document(p, config)
    ]
    for change in changes:
        if change.status != "D" and is_document(change.path, config):
            findings += _check_document(git, config, change.path, head, base)
    return findings


def protected_findings(paths: Sequence[str], patterns: Sequence[str], config: GateConfig) -> list[Finding]:
    """Step 9: AW02 in bootstrap mode, else GC015, when a changed path is covered by CODEOWNERS."""
    covered = protected_paths(paths, patterns)
    if not covered:
        return []
    listed = f"{len(covered)} protected path(s): {_shown(covered)}"
    if config.mode is Mode.BOOTSTRAP:
        return [awaiting_finding(config, "AW02", f"CODEOWNERS review is required for {listed}")]
    return [error("GC015", f"the owner's approving review is required for {listed}; {_NOT_VERIFIED}")]
