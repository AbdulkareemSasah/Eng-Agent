"""The ``workflows`` step (spec 4.14): WF001 to WF005 over workflow and composite action files.

WF000 (a file that does not parse) is added like FB000. All findings are errors; paths are relative to the root.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from eng_dev_gate.report import Finding, Severity

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

ACTIONS = "tools/eng-dev-gate/actions"
CI = ".github/workflows/ci.yml"
JOBS = ("gate", "gate-check", "risk-floor", "test-first", "ci-review", "agents-drift", "security", "windows", "build")
PUSH_ONLY = "windows"
PR_ONLY = "github.event_name == 'pull_request'"
BASE_CHECKOUT = {"ref": "${{ github.event.pull_request.base.sha }}", "path": ".gate-base", "persist-credentials": False}
PINNED = re.compile(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}")
INJECTION = re.compile(
    r"\$\{\{[^}]*\b(github\.event\.pull_request\.(title|body|head\.ref)|github\.head_ref)\b[^}]*\}\}"
)
ENG_GATE = re.compile(r"\beng-gate\b")


class _Map(dict[Any, Any]):
    """A mapping that remembers the line where it starts."""

    line: int | None = None


class _Loader(yaml.SafeLoader):
    """Safe loader whose mappings carry their line."""


def _construct_map(loader: yaml.SafeLoader, node: yaml.MappingNode) -> _Map:
    mapping = _Map(loader.construct_mapping(node, deep=True))
    mapping.line = node.start_mark.line + 1
    return mapping


_Loader.add_constructor("tag:yaml.org,2002:map", _construct_map)


def _mapping(value: object) -> _Map:
    return value if isinstance(value, _Map) else _Map()


def _items(value: object) -> list[_Map]:
    return [_mapping(v) for v in value] if isinstance(value, list) else []


def _finding(code: str, path: str, message: str, line: int | None = None) -> Finding:
    return Finding(code=code, severity=Severity.ERROR, path=path, line=line, message=message)


def _triggers(document: _Map) -> list[str]:
    on = document.get("on", document.get(True))  # YAML 1.1 reads the key ``on`` as True
    return [str(k) for k in on] if isinstance(on, (list, dict)) else [str(on)]


def _lint_steps(path: str, holders: list[_Map]) -> list[Finding]:
    findings: list[Finding] = []
    for holder in holders:
        uses = holder.get("uses")
        if isinstance(uses, str) and not uses.startswith("./") and not PINNED.fullmatch(uses):
            findings.append(
                _finding("WF001", path, f"{uses!r} is not pinned by a 40-character commit SHA", holder.line)
            )
        run = holder.get("run")
        if isinstance(run, str) and INJECTION.search(run):
            findings.append(
                _finding("WF003", path, "an attacker-controlled expression is used inside run:", holder.line)
            )
    return findings


def _steps(job: _Map) -> list[_Map]:
    return _items(job.get("steps"))


def _checkout(step: _Map) -> bool:
    return str(step.get("uses", "")).startswith("actions/checkout@")


def _job_problems(name: str, steps: list[_Map]) -> list[str]:
    """Return what departs from the steps of spec 4.14 in job ``name``."""
    pull_request = name != PUSH_ONLY
    problems: list[str] = []
    local = [s for s in steps if str(s.get("uses", "")).startswith("./")]
    if not pull_request:  # a push job uses the head variants only (the commit is already on a protected branch)
        if any(s["uses"] not in (f"./{ACTIONS}/setup", f"./{ACTIONS}/{name}") for s in local):
            problems.append("local actions must be the head variants of setup and its own action")
    else:
        head, base = [*steps, _Map(), _Map()][:2]
        head_with = _mapping(head.get("with"))
        if not _checkout(head) or "github.event.pull_request.head.sha" not in str(head_with.get("ref")):
            problems.append("the first step must check out the pull request head")
        elif head_with.get("fetch-depth") != 0:
            problems.append("the head checkout needs fetch-depth: 0")
        if not _checkout(base) or base.get("with") != BASE_CHECKOUT or base.get("if") != PR_ONLY:
            problems.append("the second step must check out the base commit into .gate-base")
        expected: list[tuple[str, object, object]] = []
        for action in ("setup", name):
            guard = f"hashFiles('.gate-base/{ACTIONS}/{action}/action.yml')"
            expected.append((f"./.gate-base/{ACTIONS}/{action}", f"{guard} != ''", {"gate-root": ".gate-base"}))
            expected.append((f"./{ACTIONS}/{action}", f"{guard} == ''", None))
        if [(s["uses"], s.get("if"), s.get("with")) for s in local] != expected:
            problems.append("local actions must be the guarded base and head variants of setup and its own action")
    if any(ENG_GATE.search(str(s.get("run", ""))) for s in steps):
        problems.append("no run: step may call eng-gate")
    return problems


def _lint_ci(root: Path, document: _Map) -> list[Finding]:
    jobs = _mapping(document.get("jobs"))
    findings = [
        _finding("WF005", CI, f"job {n!r} is not one of the jobs of spec 4.14", _mapping(j).line)
        for n, j in jobs.items()
        if n not in JOBS
    ]
    for name in JOBS:
        if name not in jobs and (name == PUSH_ONLY or (root / ACTIONS / name / "action.yml").is_file()):
            findings.append(_finding("WF005", CI, f"job {name!r} is missing"))
    for name, job in jobs.items():
        if name in JOBS:
            findings += [
                _finding("WF005", CI, f"job {name!r}: {p}", _mapping(job).line)
                for p in _job_problems(name, _steps(_mapping(job)))
            ]
    return findings


def _lint_file(root: Path, path: Path, is_workflow: bool) -> list[Finding]:
    relative = path.relative_to(root).as_posix()
    try:
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)  # noqa: S506  # B-050: SafeLoader subclass
    except (OSError, yaml.YAMLError) as error:
        return [_finding("WF000", relative, f"cannot read or parse: {error}".splitlines()[0])]
    document = _mapping(document)
    findings: list[Finding] = []
    if is_workflow:
        jobs = [_mapping(j) for j in _mapping(document.get("jobs")).values()]
        if "permissions" not in document:
            findings.append(_finding("WF002", relative, "the workflow has no top-level permissions"))
        if "pull_request_target" in _triggers(document):
            findings.append(_finding("WF004", relative, "the trigger pull_request_target is not allowed"))
        holders = [*jobs, *(s for j in jobs for s in _steps(j))]
    else:
        holders = _items(_mapping(document.get("runs")).get("steps"))
    findings += _lint_steps(relative, holders)
    if relative == CI:
        findings += _lint_ci(root, document)
    return findings


def workflows(ctx: StepContext) -> list[Finding]:
    """Lint ``.github/workflows`` and the composite actions below ``tools`` and ``packages`` of ``ctx.root``."""
    root = ctx.root
    files = [(p, True) for p in sorted((root / ".github" / "workflows").glob("*.y*ml"))]
    files += [(p, False) for top in ("tools", "packages") for p in sorted(root.glob(f"{top}/*/actions/*/action.y*ml"))]
    findings = [f for path, is_workflow in files for f in _lint_file(root, path, is_workflow)]
    if not (root / CI).is_file():
        findings.append(_finding("WF005", CI, "the workflow file is missing"))
    return findings
