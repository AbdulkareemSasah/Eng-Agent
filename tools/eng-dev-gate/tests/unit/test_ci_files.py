"""Tests of the root workflow and the composite actions (spec 4.14, AC59, AC62).

The files are read from the working tree of the workspace (never from git history). The jobs of tasks later than T6
are not in the workflow yet: ``NINE_JOBS`` is the complete list of process/11 section 5.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
ACTIONS = "tools/eng-dev-gate/actions"
NINE_JOBS = {
    "gate", "gate-check", "risk-floor", "test-first", "ci-review", "agents-drift", "security", "windows", "build",
}  # fmt: skip
# ci-review runs on pull requests only
PR_JOBS = ("gate", "gate-check", "agents-drift", "security", "build", "risk-floor", "test-first", "ci-review")
GATE_ROOT_RUN = 'uv run --project "$GATE_ROOT" --package eng-dev-gate eng-gate --root . --gate-root "$GATE_ROOT"'


def _load(path: str) -> dict[Any, Any]:
    loaded = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _workflow() -> dict[Any, Any]:
    return _load(".github/workflows/ci.yml")


def _action(name: str) -> dict[Any, Any]:
    return _load(f"{ACTIONS}/{name}/action.yml")


def _runs(action: dict[Any, Any]) -> str:
    return "\n".join(step["run"] for step in action["runs"]["steps"] if "run" in step)


def _all_steps(workflow: dict[Any, Any]) -> list[dict[str, Any]]:
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def test_jobs_triggers_and_local_actions() -> None:
    """AC59: thin jobs from the nine of process/11, the triggers, read-only permissions, local composite actions."""
    workflow = _workflow()
    assert set(workflow["jobs"]) == {*PR_JOBS, "windows"}
    assert set(workflow["jobs"]) <= NINE_JOBS
    triggers: dict[str, Any] = (
        workflow["on"] if "on" in workflow else workflow[True]
    )  # PyYAML (YAML 1.1) reads the key `on` as True
    assert set(triggers) == {"pull_request", "push"}
    assert triggers["pull_request"]["branches"] == ["build/v1", "main"]
    assert triggers["pull_request"]["types"] == ["opened", "synchronize", "reopened", "edited", "ready_for_review"]
    assert triggers["push"]["branches"] == ["build/v1"]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is True
    assert workflow["jobs"]["gate-check"]["if"] == "github.event_name == 'pull_request'"  # spec 4.14: PR events only
    windows_if = workflow["jobs"]["windows"]["if"]
    assert "github.event_name == 'push'" in windows_if
    assert "github.ref == 'refs/heads/build/v1'" in windows_if
    uses = [s["uses"] for s in _all_steps(workflow) if s.get("uses", "").startswith("./")]
    assert uses
    for reference in uses:
        assert re.fullmatch(rf"\./(\.gate-base/)?{ACTIONS}/[a-z-]+", reference), reference
        action_file = ROOT / reference.removeprefix("./.gate-base/").removeprefix("./") / "action.yml"
        assert yaml.safe_load(action_file.read_text(encoding="utf-8"))["runs"]["using"] == "composite"
    for step in _all_steps(workflow):  # third-party actions are pinned by a 40-digit commit SHA (WF001)
        if "uses" in step and not step["uses"].startswith("./"):
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"]), step["uses"]


def test_pr_jobs_base_first_steps() -> None:
    """Spec 4.14: head checkout, base checkout into .gate-base, then the guarded base and head variants."""
    for name in PR_JOBS:
        steps = _workflow()["jobs"][name]["steps"]
        head, base = steps[0], steps[1]
        assert head["with"]["ref"] == "${{ github.event.pull_request.head.sha || github.sha }}", name
        assert head["with"]["fetch-depth"] == 0
        assert base["with"] == {
            "ref": "${{ github.event.pull_request.base.sha }}", "path": ".gate-base", "persist-credentials": False,
        }  # fmt: skip
        assert base["if"] == "github.event_name == 'pull_request'"
        expected: list[tuple[str, str, dict[str, str] | None]] = []
        for action in ("setup", name):
            guard = f"hashFiles('.gate-base/{ACTIONS}/{action}/action.yml')"
            expected.append((f"./.gate-base/{ACTIONS}/{action}", f"{guard} != ''", {"gate-root": ".gate-base"}))
            expected.append((f"./{ACTIONS}/{action}", f"{guard} == ''", None))
        actual = [(s["uses"], s["if"], s.get("with")) for s in steps[2:6]]
        assert actual == expected, name
        assert not any("eng-gate" in s.get("run", "") for s in steps), name


def test_security_and_build_commands() -> None:
    """AC62: build covers every member, security runs the scan and the audit; no step weakens the gate."""
    build = _runs(_action("build"))
    assert "packages --names" in build
    assert 'uv build --package "$name"' in build
    gate = _runs(_action("gate"))
    assert "check --all" in gate
    assert not re.search(r"--(only|skip)\b", gate)  # the CI steps never use --only or --skip
    assert "agents drift" in _runs(_action("agents-drift"))
    assert "gate-check" in _runs(_action("gate-check"))
    security = _runs(_action("security"))
    assert "secrets --range" in security
    assert "secrets --tree" in security
    assert "uv audit --locked" in security
    assert "risk-floor" in _runs(_action("risk-floor"))
    assert "test-first" in _runs(_action("test-first"))
    for name in PR_JOBS:
        scripts = _runs(_action(name))
        assert GATE_ROOT_RUN in scripts, name  # the base variant
        assert "uv run eng-gate" in scripts, name  # the head variant
        assert "github.event" not in scripts, name  # titles and bodies are never expanded in a script (WF003)
    setup = _runs(_action("setup"))
    assert "uv sync --all-packages --locked" in setup
    assert 'uv sync --project "$GATE_ROOT" --package eng-dev-gate --locked' in setup


def test_ci_review_job() -> None:
    """AC61: the job runs only on pull requests and its action runs `review`."""
    assert _workflow()["jobs"]["ci-review"]["if"] == "github.event_name == 'pull_request'"
    assert " review" in _runs(_action("ci-review"))


def test_ignored_base_checkout_and_spikes() -> None:
    """`.gate-base/` is ignored; every spike check still runs (Linux in the gate job, Windows in the windows job)."""
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".gate-base/" in ignored
    assert f"!{ACTIONS}/build/" in ignored  # the rule `build/` would otherwise hide the build action
    jobs = _workflow()["jobs"]
    assert "spikes/*/check.py" in "\n".join(s.get("run", "") for s in jobs["gate"]["steps"])
    assert "spikes/*/windows_check.py" in "\n".join(s.get("run", "") for s in jobs["windows"]["steps"])


@pytest.mark.parametrize(
    "name",
    ["setup", "gate", "gate-check", "agents-drift", "security", "build", "risk-floor", "test-first", "ci-review"],
)
def test_actions_are_composite(name: str) -> None:
    """Each action is composite, has the optional gate-root input and names the shell of every run step."""
    action = _action(name)
    assert action["runs"]["using"] == "composite"
    assert action["inputs"]["gate-root"]["default"] == ""
    assert all("shell" in s for s in action["runs"]["steps"] if "run" in s)


def test_windows_job_only_on_push() -> None:
    """AC59: the windows job runs only on pushes to build/v1, with the head variants and the windows action."""
    job = _workflow()["jobs"]["windows"]
    assert job["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/build/v1'"
    assert job["runs-on"] == "windows-latest"
    uses = [s["uses"] for s in job["steps"] if s.get("uses", "").startswith("./")]
    assert uses == [f"./{ACTIONS}/setup", f"./{ACTIONS}/windows"]
    assert not any("pytest" in s.get("run", "") for s in job["steps"])  # the windows-tests command picks the paths
    action = _action("windows")
    assert action["runs"]["using"] == "composite"
    assert "uv run eng-gate windows-tests" in _runs(action)
    assert "github.event" not in _runs(action)


def test_gate_action_runs_only_check() -> None:
    """AC59: the gate action runs ``eng-gate check`` only; the tests step runs each member's tests."""
    action = _action("gate")
    steps = action["runs"]["steps"]
    assert len(steps) == 1
    run = steps[0]["run"]
    assert "eng-gate" in run
    assert "check --all" in run
    assert "pytest" not in run
    assert "pytest" not in str(action["description"])
