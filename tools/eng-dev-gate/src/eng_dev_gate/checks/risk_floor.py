"""``risk-floor`` (spec 4.6): the risk floor of the changed paths against the recorded risk (RF001 to RF004).

The maps are read from git at the base and the head commit, so a pull request can add an entry but not drop one. The
pull-request title and body are data: the ``Risk:`` line is parsed, never executed.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from eng_dev_gate.checks.gate_check import parse_body
from eng_dev_gate.config import GateConfig
from eng_dev_gate.event import event_path, read_event
from eng_dev_gate.frontmatter import FrontMatterError, parse_plan, parse_spec, safe_relative_path
from eng_dev_gate.gate_root import GateContext
from eng_dev_gate.gitio import Git, PathNotFoundError, SubprocessGit
from eng_dev_gate.globs import matches_any
from eng_dev_gate.report import CommandResult, Finding, Severity, StepResult, render
from eng_dev_gate.results import Status, UsageError
from eng_dev_gate.workspace import discover_members

MAP_FILE = ".gate/risk-map.yml"
_LANE = re.compile(r"lane/\d+-[a-z0-9-]+")
_PLAN_TASK = re.compile(r"(\S+)#T\d+[a-z]*")
_RISK = re.compile(r"r[0-3]")


class RiskMapError(UsageError):
    """RF003: a risk map is missing, not YAML, or invalid (exit 2)."""

    def __init__(self, message: str) -> None:
        super().__init__(f"RF003 {message}")


class _Entry(BaseModel):
    """One map entry: the globs and the risk set they raise (a scalar risk is a set of one)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    paths: list[str] = Field(min_length=1)
    risk: list[Literal["r0", "r1", "r2", "r3"]] = Field(min_length=1)

    @field_validator("risk", mode="before")
    @classmethod
    def _scalar(cls, value: object) -> object:
        return [value] if isinstance(value, str) else value


def _read_map(git: Git, ref: str, path: str) -> list[_Entry] | None:
    """Return the entries of the map at ``ref``, or None when the file is absent there.

    Raises:
        RiskMapError: the file is not valid YAML or not a list of entries.
    """
    try:
        text = git.show(ref, path)
    except PathNotFoundError:
        return None
    try:
        return TypeAdapter(list[_Entry]).validate_python(yaml.safe_load(text))
    except (yaml.YAMLError, ValidationError) as error:
        raise RiskMapError(f"{path} at {ref} is invalid: {error}") from error


def risk_floor(git: Git, refs: tuple[str, str], changed: list[str], member_dirs: list[str]) -> dict[str, set[str]]:
    """Return ``{risk: changed paths that raised it}`` over both refs and both map levels.

    Args:
        git: the git port.
        refs: the base and the head commit whose maps are read.
        changed: changed paths, relative to the workspace root.
        member_dirs: POSIX paths of the workspace members whose own maps apply to the paths below them.

    Raises:
        RiskMapError: a map is invalid, or the root map is missing at both commits.
    """
    floor: dict[str, set[str]] = {}
    root_seen = False
    for ref in refs:
        for directory in ("", *member_dirs):
            prefix = f"{directory}/" if directory else ""
            entries = _read_map(git, ref, f"{prefix}{MAP_FILE}")
            root_seen = root_seen or (not directory and entries is not None)
            for entry in entries or []:
                for path in changed:
                    if path.startswith(prefix) and matches_any(path.removeprefix(prefix), entry.paths):
                        for risk in entry.risk:
                            floor.setdefault(risk, set()).add(path)
    if not root_seen:
        raise RiskMapError(f"{MAP_FILE} exists at neither the base nor the head commit")
    return floor


def parse_risk_line(value: str) -> set[str] | None:
    """Parse the value of a ``Risk:`` line (``r1, r2``; a trailing ``(...)`` note is ignored); None if malformed."""
    tokens = re.split(r"[,\s]+", re.sub(r"\(.*?\)", "", value).strip())
    return set(tokens) if all(_RISK.fullmatch(t) for t in tokens) else None


def _body_risk(body: str) -> list[set[str] | None]:
    return [parse_risk_line(line.removeprefix("Risk:")) for line in body.splitlines() if line.startswith("Risk:")]


def _rf004(message: str) -> Finding:
    return Finding(code="RF004", severity=Severity.ERROR, message=f"no recorded risk: {message}")


def _documents_risk(git: Git, head: str, changed: list[str], config: GateConfig) -> set[str] | Finding:
    """Union of the ``risk`` of the changed specs and plans at ``head``."""
    risks: set[str] = set()
    for path in changed:
        try:
            text = git.show(head, path)
            doc = (
                parse_plan(text, config.limits.max_task_lines)
                if matches_any(path, config.plan_globs)
                else parse_spec(text)
            )
        except (PathNotFoundError, FrontMatterError) as error:
            return _rf004(f"{path}: {error}")
        risks |= set(doc.risk)
    return risks


def _plan_risk(git: Git, gate_ref: str, body: str, config: GateConfig) -> set[str] | Finding:
    """The ``risk`` of the plan named by the single ``Plan-Task`` line, read on the gate branch."""
    lines = parse_body(body).plan_task
    found = _PLAN_TASK.fullmatch(lines[0][1]) if len(lines) == 1 else None
    if not found or not safe_relative_path(found[1]) or not matches_any(found[1], config.plan_globs):
        return _rf004("the body needs exactly one `Plan-Task: <plan path>#T<n>` line")
    try:
        return set(parse_plan(git.show(gate_ref, found[1]), config.limits.max_task_lines).risk)
    except (PathNotFoundError, FrontMatterError) as error:
        return _rf004(f"plan {found[1]} on {gate_ref}: {error}")


def check_risk_floor(
    git: Git,
    config: GateConfig,
    shas: tuple[str, str],
    head_ref: str | None,
    body: str,
    gate_ref: str,
    members: list[str],
) -> list[Finding]:
    """Compare the floor with the recorded risk (RF001, RF002, RF004).

    Args:
        git: the git port.
        config: the gate configuration (globs, line cap).
        shas: base and head commit.
        head_ref: the head branch name, None when unknown (then it is never a lane branch).
        body: the pull-request body.
        gate_ref: the ref plans are read from.
        members: POSIX paths of the workspace members.

    Raises:
        RiskMapError: RF003.
    """
    changed = list(dict.fromkeys(p for c in git.name_status(git.merge_base(*shas), shas[1]) for p in c.paths))
    floor = risk_floor(git, shas, changed, members)
    lane = head_ref is not None and _LANE.fullmatch(head_ref) is not None
    documents = bool(changed) and all(matches_any(p, [*config.spec_globs, *config.plan_globs]) for p in changed)
    declared = _body_risk(body)
    if lane:
        recorded = declared[0] if len(declared) == 1 else None
        recorded_or_finding = recorded if recorded is not None else _rf004("a lane branch needs one valid `Risk:` line")
    elif documents:
        recorded_or_finding = _documents_risk(git, shas[1], changed, config)
    else:
        recorded_or_finding = _plan_risk(git, gate_ref, body, config)
    if isinstance(recorded_or_finding, Finding):
        return [recorded_or_finding]
    findings = []
    if missing := sorted(set(floor) - recorded_or_finding):
        raised = "; ".join(f"{r}: {', '.join(sorted(floor[r]))}" for r in missing)
        message = (
            f"floor {sorted(floor)} is not within the recorded risk {sorted(recorded_or_finding)}; raised by {raised}"
        )
        findings.append(Finding(code="RF001", severity=Severity.ERROR, message=message))
    if not (lane or documents) and declared and declared != [recorded_or_finding]:
        message = f"the body `Risk:` line must name the plan's set {sorted(recorded_or_finding)}"
        findings.append(Finding(code="RF002", severity=Severity.ERROR, message=message))
    return findings


def handle_risk_floor(args: argparse.Namespace) -> Status:
    """The ``risk-floor`` command: from ``--base``, ``--head`` and ``--body-file`` or from the event.

    Raises:
        UsageError: no input, incomplete options, a fork, or an unreadable body file.
        RiskMapError: RF003.
        GitError: git failed.
    """
    context: GateContext = args.gate_context
    git, config = SubprocessGit(context.root), context.config
    gate_ref = args.gate_ref or f"origin/{config.gate_branch}"
    members = (
        [m.path for m in discover_members(context.root) if m.path != "."]
        if (context.root / "pyproject.toml").is_file()
        else []
    )
    if args.base or args.head or args.body_file:
        if not (args.base and args.head and args.body_file):
            raise UsageError("--base, --head and --body-file go together")
        try:
            body = Path(args.body_file).read_text(encoding="utf-8")
        except OSError as error:
            raise UsageError(f"cannot read {args.body_file}: {error}") from error
        step = StepResult(
            name="risk-floor",
            findings=check_risk_floor(git, config, (args.base, args.head), None, body, gate_ref, members),
        )
    else:
        path = event_path(args.event, os.environ)
        if path is None:
            raise UsageError("no input: pass --event, --base --head --body-file, or set GITHUB_EVENT_PATH")
        pr = read_event(path).pull_request
        if pr is None:
            step = StepResult(name="risk-floor", skipped_reason="push event")
        elif pr.from_fork:
            raise UsageError("pull requests from another repository are not supported")
        else:
            found = check_risk_floor(git, config, (pr.base_sha, pr.head_sha), pr.head_ref, pr.body, gate_ref, members)
            step = StepResult(name="risk-floor", findings=found)
    result = context.with_findings(CommandResult(command="risk-floor", mode=config.mode.value, steps=[step]))
    render(result, args.format, sys.stdout, os.environ)
    return result.status
