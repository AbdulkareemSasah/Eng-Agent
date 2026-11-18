"""Tests of the ``packages`` command (spec 5; the ``build`` job iterates over its names)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from support.repo import Repo

GATE_YML = (
    "bootstrap: {enabled: true, gate_branch: build/v1}\nmain_branch: main\n"
    "spec_globs: []\nplan_globs: []\ntest_globs: []\ngenerated_globs: []\nspike_globs: []\n"
    "limits: {diff_lines: 200, test_run_seconds: 600, max_file_bytes: 1048576"
    ", mutation_run_seconds: 7200}\n"
)


def _workspace(repo: Repo, members: dict[str, str]) -> None:
    """Commit a workspace whose members are the keys of ``members`` (path to project name)."""
    listed = ", ".join(f'"{path}"' for path in members)
    files = {".gate/gate.yml": GATE_YML, "pyproject.toml": f"[tool.uv.workspace]\nmembers = [{listed}]\n"}
    files.update({f"{p}/pyproject.toml": f'[project]\nname = "{n}"\nversion = "0.1.0"\n' for p, n in members.items()})
    repo.commit(files)


def test_packages_names(repo: Repo) -> None:
    """--names prints one project name per line, ordered by path; --json prints name and path; the default both."""
    _workspace(repo, {"tools/zeta": "zeta-tool", "packages/alpha": "alpha-pkg"})
    named = repo.run(["packages", "--names"])
    assert (named.code, named.out) == (0, "alpha-pkg\nzeta-tool\n")
    listed = repo.run(["packages", "--json"])
    assert listed.code == 0
    assert json.loads(listed.out) == [
        {"name": "alpha-pkg", "path": "packages/alpha"},
        {"name": "zeta-tool", "path": "tools/zeta"},
    ]
    assert repo.run(["packages"]).out == "alpha-pkg\tpackages/alpha\nzeta-tool\ttools/zeta\n"


def test_packages_handles_a_single_member_and_no_workspace(repo: Repo) -> None:
    """A workspace with one member (no packages/ folder) lists it; a root without a workspace table exits 2."""
    _workspace(repo, {"tools/only": "only-tool"})
    assert repo.run(["packages", "--names"]).out == "only-tool\n"
    repo.commit({"pyproject.toml": "[project]\nname = 'x'\n"})
    broken = repo.run(["packages", "--names"])
    assert (broken.code, broken.out) == (2, "")
    assert "tool.uv.workspace" in broken.err


def test_packages_names_and_json_exclude_each_other(repo: Repo) -> None:
    """--names with --json is a usage error (exit 2)."""
    _workspace(repo, {"tools/only": "only-tool"})
    both = repo.run(["packages", "--names", "--json"])
    assert both.code == 2
    assert "not allowed with" in both.err


def test_packages_in_a_head_run_keeps_stdout_to_the_names(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AW09 (the base has no build action) goes to stderr as a notice; stdout stays the list the build job reads."""
    _workspace(repo, {"tools/only": "only-tool"})
    base = repo.git("rev-parse", "HEAD").strip()
    ref = {"ref": "build/v1", "sha": base, "repo": {"full_name": "o/r"}}
    pull_request = {"number": 7, "title": "t", "body": "b", "draft": False, "user": {"login": "agent"}}
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {**pull_request, "base": ref, "head": ref}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    result = repo.run(["packages", "--names"])
    assert (result.code, result.out) == (0, "only-tool\n")
    assert result.err.startswith("::notice title=awaiting owner::AW09")
