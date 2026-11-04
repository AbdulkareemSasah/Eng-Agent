"""Fixture: a temporary repository for ``test-first``: a gate branch, a base test file, and a one-call runner."""

from __future__ import annotations

import json
from collections.abc import Mapping

from eng_dev_gate.checks.test_first import handle
from eng_dev_gate.checks.test_first_run import Runner

from support.pullrequest import make_gate_repo
from support.repo import Repo, RunResult

BASE_TEST = "def test_one() -> None:\n    assert 1 + 1 == 2\n"
BASE_TEST_PATH = "pkg/tests/test_a.py"
NEW_TEST = "def test_two() -> None:\n    assert 2 + 2 == 4\n"
SRC = {"pkg/src/new.py": "y = 2\n"}
LIB = "pkg/src/fixpkg/__init__.py"  # the toy package under test; its value is 1 at the base
WORKSPACE = {
    "pyproject.toml": '[project]\nname = "root"\nversion = "0"\n\n[tool.uv.workspace]\nmembers = ["pkg"]\n',
    "pkg/pyproject.toml": '[project]\nname = "fixpkg-dist"\nversion = "0"\n\n[tool.eng-gate]\nprofile = "tool"\n'
    'layer = "tool"\nimport_names = ["fixpkg"]\ncoverage_line = 95\ncoverage_branch = 90\n',
    LIB: "VALUE = 1\n",
}


def tf_repo(repo: Repo, *, plan: str | None = None, base_files: Mapping[str, str] | None = None) -> str:
    """Create the gate repository with a toy workspace and ``pkg/tests/test_a.py``; return the base SHA."""
    files = {BASE_TEST_PATH: BASE_TEST, **WORKSPACE, **(base_files or {})}
    return make_gate_repo(repo, plan=plan, base_files=files)


def head_of(repo: Repo) -> str:
    """The current ``HEAD`` commit."""
    return repo.git("rev-parse", "HEAD").strip()


def tf_run(
    repo: Repo, base: str, title: str, *extra: str, runner: Runner | None = None
) -> tuple[RunResult, str, dict[str, str]]:
    """Run ``test-first --base --head --title`` with JSON output, with ``runner`` in place of the subprocess one.

    Returns the run, the command status, and ``{code: "path message" lines}`` of the error findings.
    """
    result = repo.run(
        ["--format", "json", "test-first", "--base", base, "--head", head_of(repo), "--title", title, *extra],
        {"test-first": lambda args: handle(args, runner)},
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
