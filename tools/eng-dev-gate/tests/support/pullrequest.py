"""Fixture: a temporary repository holding a gate branch with a plan and a spec, and pull-request events (spec 9).

The gate branch is recorded as ``origin/build/v1`` (or ``origin/main``) with ``update-ref``, so the default
``--gate-ref`` of ``gate-check`` is exercised without a network.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from eng_dev_gate import gate_root

from support.repo import Repo, RunResult

PACKAGE_DIR = "tools/eng-dev-gate/src/eng_dev_gate"

PLAN_PATH = "pkg/docs/plans/0001-x.md"
SPEC_PATH = "pkg/docs/specs/0001-x.md"
PLAN_TASK = f"Plan-Task: {PLAN_PATH}#T1"
BODY = f"Work-Item: B-001\n{PLAN_TASK}\nRisk: r1\n"
OWNER_IDENTITIES = "identities:\n  owner_login: owner\n  agent_logins: [agent]\n  reviewer_app: reviewer\n"


def gate_yml(*, bootstrap: bool = True) -> str:
    """The root ``.gate/gate.yml`` of the fixture."""
    return (
        f"bootstrap:\n  enabled: {str(bootstrap).lower()}\n  gate_branch: build/v1\nmain_branch: main\n"
        + ("" if bootstrap else OWNER_IDENTITIES)
        + "spec_globs: ['**/docs/specs/*.md']\nplan_globs: ['**/docs/plans/*.md']\n"
        "test_globs: ['**/tests/**', '**/test_*.py']\ngenerated_globs: ['uv.lock', '**/AGENTS.md']\n"
        "spike_globs: ['spikes/**']\n"
        "limits:\n  diff_lines: 200\n  max_task_lines: 400\n  test_run_seconds: 600\n  max_file_bytes: 1048576\n"
    )


def plan_text(
    *,
    status: str = "approved",
    files: Sequence[str] = ("pkg/src/**",),
    max_changed_lines: int = 10,
    spec: str = SPEC_PATH,
) -> str:
    """A plan with the task ``T1`` (and a second task ``T2``) for the spec ``spec``."""
    globs = ", ".join(f'"{f}"' for f in files)
    return (
        f"---\nid: plan-1\nissue: B-001\nspec: {spec}\nstatus: {status}\nsize: small\nrisk: r1\ntasks:\n"
        f"  - id: T1\n    title: One\n    files: [{globs}]\n    max_changed_lines: {max_changed_lines}\n"
        "    max_sessions: 2\n    tests_first: []\n    covers: [AC1]\n    depends_on: []\n"
        '  - id: T2\n    title: Two\n    files: ["pkg/other/**"]\n    max_changed_lines: 50\n'
        "    max_sessions: 1\n    covers: [AC1]\n    depends_on: [T1]\n---\n\n# Plan\n"
    )


def spec_text(status: str = "approved") -> str:
    """A spec with one acceptance criterion."""
    return f"---\nid: spec-1\nissue: B-001\nstatus: {status}\nsize: small\nrisk: r1\n---\n\n- AC1. Given x, then y.\n"


def make_gate_repo(
    repo: Repo, *, bootstrap: bool = True, base_files: Mapping[str, str] | None = None, plan: str | None = None
) -> str:
    """Commit the gate files, record the gate branch as ``origin/<gate_branch>``, branch off and return the base SHA."""
    files = {
        ".gate/gate.yml": gate_yml(bootstrap=bootstrap),
        PLAN_PATH: plan if plan is not None else plan_text(),
        SPEC_PATH: spec_text(),
        "pkg/src/keep.py": "x = 1\n",
        **(base_files or {}),
    }
    base = repo.commit(files, "chore: base")
    repo.git("update-ref", "refs/remotes/origin/" + ("build/v1" if bootstrap else "main"), base)
    repo.branch("feat/x")
    return base


def write_event(
    repo: Repo, base: str, body: str, *, base_ref: str = "build/v1", head_repo: str = "o/r", name: str = "event.json"
) -> Path:
    """Write a pull-request event for the current ``HEAD`` against ``base`` and return its path (outside the tree)."""
    head = repo.git("rev-parse", "HEAD").strip()
    pr = {
        "number": 7,
        "title": "feat(x): y (B-001)",
        "body": body,
        "draft": False,
        "base": {"ref": base_ref, "sha": base, "repo": {"full_name": "o/r"}},
        "head": {"ref": "feat/x", "sha": head, "repo": {"full_name": head_repo}},
        "user": {"login": "agent"},
        "labels": [],
    }
    path = repo.root.parent / name
    path.write_text(json.dumps({"pull_request": pr}), encoding="utf-8")
    return path


def base_checkout(repo: Repo, base: str, where: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Check out ``base`` into ``where`` (the gate root of spec 4.16) and make it the running package's home.

    With bootstrap off a head run is CF009, so a normal-mode pull request is judged from this checkout.
    """
    repo.git("worktree", "add", "-q", "--detach", str(where), base)
    monkeypatch.setattr(gate_root, "running_package", lambda: where / PACKAGE_DIR)
    return where


def gate_check(repo: Repo, event: Path, *extra: str, gate: Path | None = None) -> tuple[RunResult, dict[str, str]]:
    """Run ``gate-check`` with JSON output; return the result and ``{code: "path message" lines}`` of the errors."""
    root_args = ["--gate-root", str(gate)] if gate else []
    result = repo.run([*root_args, "--format", "json", "gate-check", "--event", str(event), *extra])
    errors: dict[str, str] = {}
    if result.out:
        data = json.loads(result.out)
        for step in data["steps"]:
            for finding in step["findings"]:
                if finding["severity"] == "error":
                    errors[finding["code"]] = (
                        errors.get(finding["code"], "") + f"{finding['path'] or ''} {finding['message']}\n"
                    )
    return result, errors
