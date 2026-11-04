"""Fixture: a temporary repository for ``test-first``: a gate branch, a base test file, and a one-call runner."""

from __future__ import annotations

import json
from collections.abc import Mapping

from support.pullrequest import make_gate_repo
from support.repo import Repo, RunResult

BASE_TEST = "def test_one() -> None:\n    assert 1 + 1 == 2\n"
BASE_TEST_PATH = "pkg/tests/test_a.py"
NEW_TEST = "def test_two() -> None:\n    assert 2 + 2 == 4\n"
SRC = {"pkg/src/new.py": "y = 2\n"}


def tf_repo(repo: Repo, *, plan: str | None = None, base_files: Mapping[str, str] | None = None) -> str:
    """Create the gate repository with ``pkg/tests/test_a.py`` at the base; return the base SHA (HEAD is ``feat/x``)."""
    return make_gate_repo(repo, plan=plan, base_files={BASE_TEST_PATH: BASE_TEST, **(base_files or {})})


def head_of(repo: Repo) -> str:
    """The current ``HEAD`` commit."""
    return repo.git("rev-parse", "HEAD").strip()


def tf_run(repo: Repo, base: str, title: str, *extra: str) -> tuple[RunResult, str, dict[str, str]]:
    """Run ``test-first --base --head --title`` with JSON output.

    Returns the run, the command status, and ``{code: "path message" lines}`` of the error findings.
    """
    result = repo.run(
        ["--format", "json", "test-first", "--base", base, "--head", head_of(repo), "--title", title, *extra]
    )
    errors: dict[str, str] = {}
    status = ""
    if result.out:
        data = json.loads(result.out)
        status = data["status"]
        for step in data["steps"]:
            for finding in step["findings"]:
                if finding["severity"] == "error":
                    line = f"{finding['path'] or ''} {finding['message']}\n"
                    errors[finding["code"]] = errors.get(finding["code"], "") + line
    return result, status, errors
