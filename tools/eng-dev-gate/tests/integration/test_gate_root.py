"""Tests of the gate of the base commit: gate root, provenance and head runs (spec 4.16; AC65 to AC67).

Fixtures are temporary git repositories: a base commit, a head commit, a checkout of the base (the gate root) made with
``git worktree`` and a hand-written event file. The running package is redirected with ``running_package``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from eng_dev_gate import gate_root, report
from eng_dev_gate.gate_root import GateContext
from eng_dev_gate.report import CommandResult, StepResult
from eng_dev_gate.results import Status
from support.repo import Repo, RunResult, make_repo

IDENTITIES = "identities: {owner_login: owner, agent_logins: [agent], reviewer_app: reviewer}\n"
ACTION = "tools/eng-dev-gate/actions/gate-check/action.yml"
PACKAGE_DIR = "tools/eng-dev-gate/src/eng_dev_gate"
BASE_RULES = "rules: [no-eval]\n"
HEAD_RULES = "rules: []\n"


def _gate_yml(*, bootstrap: bool, diff_lines: int) -> str:
    return (
        f"bootstrap: {{enabled: {str(bootstrap).lower()}, gate_branch: build/v1}}\nmain_branch: main\n"
        f"{'' if bootstrap else IDENTITIES}"
        "spec_globs: []\nplan_globs: []\ntest_globs: []\ngenerated_globs: []\nspike_globs: []\n"
        f"limits: {{diff_lines: {diff_lines}, max_task_lines: 400, test_run_seconds: 600, max_file_bytes: 1048576"
        f", mutation_run_seconds: 7200}}\n"
    )


def _event(path: Path, base: str, head: str | None) -> Path:
    """Write a pull-request event (``head`` given) or a push event (``head`` None)."""
    if head is None:
        data: dict[str, object] = {"ref": "refs/heads/build/v1", "after": base}
    else:

        def ref(name: str, sha: str) -> dict[str, object]:
            return {"ref": name, "sha": sha, "repo": {"full_name": "o/r"}}

        data = {
            "pull_request": {
                "number": 7, "title": "t", "body": "b", "draft": False, "user": {"login": "agent"},
                "base": ref("build/v1", base), "head": ref("feature", head),
            }
        }  # fmt: skip
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@dataclass
class World:
    """A repository on its head commit, the base checkout and the contexts the stub handler saw."""

    repo: Repo
    base: str
    head: str
    gate: Path
    event: Path
    seen: list[GateContext] = field(default_factory=list)

    def run(self, *, use_gate_root: bool = True, gate: Path | None = None) -> RunResult:
        """Run ``gate-check`` (a stub handler that renders the context's findings); the event is in the environment."""
        gate_args = ["--gate-root", str(gate or self.gate)] if use_gate_root else []
        return self.repo.run([*gate_args, "gate-check"], {"gate-check": self._handler})

    def _handler(self, args: argparse.Namespace) -> Status:
        context: GateContext = args.gate_context
        self.seen.append(context)
        result = context.with_findings(
            CommandResult(command="probe", mode=context.config.mode.value, steps=[StepResult(name="probe")])
        )
        report.render(result, "text", sys.stdout, os.environ)
        return result.status


def _world(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    base_bootstrap: bool = True,
    base_has_action: bool = False,
    pull_request: bool = True,
) -> World:
    repo = make_repo(tmp_path / "repo")
    base_files = {
        ".gate/gate.yml": _gate_yml(bootstrap=base_bootstrap, diff_lines=200),
        ".gate/forbidden.yml": BASE_RULES,
        ".gate/risk-map.yml": "base map\n",
    }
    if base_has_action:
        base_files[ACTION] = "name: gate-check\n"
    base = repo.commit(base_files)
    repo.branch("feature")
    head = repo.commit(
        {".gate/gate.yml": _gate_yml(bootstrap=False, diff_lines=5000), ".gate/forbidden.yml": HEAD_RULES}
    )
    gate = tmp_path / "gate-base"
    repo.git("worktree", "add", "-q", "--detach", str(gate), base)
    event = _event(tmp_path / "event.json", base, head if pull_request else None)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setattr(gate_root, "running_package", lambda: gate / PACKAGE_DIR)
    return World(repo, base, head, gate, event)


def test_policy_from_gate_root_not_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC65: policy files, limits and the mode come from the gate root; the tree under check is the head."""
    world = _world(tmp_path, monkeypatch)
    assert (world.repo.root / ".gate/forbidden.yml").read_text(encoding="utf-8") == HEAD_RULES  # the head weakens it
    result = world.run()
    assert result.code == 0, result.err
    (context,) = world.seen
    assert context.config.limits.diff_lines == 200  # the head says 5000
    assert context.config.mode.value == "bootstrap"  # the head says bootstrap off
    assert context.read_policy(".gate/forbidden.yml") == BASE_RULES
    assert context.read_policy(".gate/risk-map.yml") == "base map\n"
    assert context.root == world.repo.root
    assert context.findings == ()


def test_push_and_local_runs_need_no_gate_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC66: with a push event or no event there is no provenance rule; the policy is read from the root."""
    world = _world(tmp_path, monkeypatch, pull_request=False)
    result = world.run(use_gate_root=False)
    assert result.code == 0, result.err
    assert world.seen[0].policy_root == world.repo.root
    assert world.seen[0].config.limits.diff_lines == 5000
    monkeypatch.delenv("GITHUB_EVENT_PATH")
    assert world.run(use_gate_root=False).code == 0
    world.repo.git("checkout", "-q", "--detach", world.base)  # a gate root is not checked against a push either
    assert world.run().code == 0
    assert world.seen[-1].policy_root == world.gate


def test_provenance_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC66: the gate root must be the base commit and must hold the running package; otherwise CF009, exit 1."""
    world = _world(tmp_path, monkeypatch)
    assert world.run().code == 0
    # The gate root is checked out at another commit than the event's base.
    wrong = tmp_path / "wrong-base"
    world.repo.git("worktree", "add", "-q", "--detach", str(wrong), world.head)
    result = world.run(gate=wrong)
    assert result.code == 1
    assert "CF009" in result.err
    # The gate root is not a git checkout.
    plain = tmp_path / "plain"
    (plain / ".gate").mkdir(parents=True)
    (plain / ".gate/gate.yml").write_text(_gate_yml(bootstrap=True, diff_lines=200), encoding="utf-8")
    result = world.run(gate=plain)
    assert result.code == 1
    assert "CF009" in result.err
    # The running package is not inside the gate root (the head copy of the gate would judge).
    monkeypatch.setattr(gate_root, "running_package", lambda: world.repo.root / PACKAGE_DIR)
    result = world.run()
    assert result.code == 1
    assert "CF009" in result.err
    assert "running package" in result.err


@pytest.mark.parametrize("base_bootstrap", [True, False])
def test_head_run_in_both_modes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, base_bootstrap: bool) -> None:
    """AC67: a head run is AW09 in bootstrap mode and CF009 with bootstrap off, when the base has no action."""
    world = _world(tmp_path, monkeypatch, base_bootstrap=base_bootstrap)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    result = world.run(use_gate_root=False)
    if base_bootstrap:
        assert result.code == 0, result.err
        assert "::notice title=awaiting owner::AW09" in result.out
        assert "AW09" in summary.read_text(encoding="utf-8")
        assert world.seen[0].config.mode.value == "bootstrap"  # from the base, not from the head's gate.yml
        assert world.seen[0].policy_root == world.repo.root
    else:
        assert result.code == 1
        assert "CF009" in result.err
        assert not summary.exists()


def test_head_run_needs_a_gate_yml_at_the_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A head run reads the mode from the base commit; a base without gate.yml is CF007 (exit 2), not a guess."""
    repo = make_repo(tmp_path / "repo")
    base = repo.commit({"README.md": "base\n"})
    head = repo.commit({".gate/gate.yml": _gate_yml(bootstrap=True, diff_lines=200)})
    event = _event(tmp_path / "event.json", base, head)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    result = World(repo, base, head, tmp_path / "none", event).run(use_gate_root=False)
    assert result.code == 2
    assert "CF007" in result.err


@pytest.mark.parametrize("base_bootstrap", [True, False])
def test_head_run_is_refused_when_the_base_has_the_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, base_bootstrap: bool
) -> None:
    """AC67: when the base commit has the job's action, a head run is CF009 in both modes."""
    world = _world(tmp_path, monkeypatch, base_bootstrap=base_bootstrap, base_has_action=True)
    result = world.run(use_gate_root=False)
    assert result.code == 1
    assert "CF009" in result.err
    assert world.seen == []
