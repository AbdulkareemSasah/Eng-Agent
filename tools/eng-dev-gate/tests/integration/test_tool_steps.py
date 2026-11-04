"""Integration tests of the lock, format, lint and types steps with the real tools on a toy workspace."""

from __future__ import annotations

import json
import subprocess

from eng_dev_gate.checks.check import make_handler
from eng_dev_gate.toolrun import SubprocessToolRunner
from support.repo import Repo, RunResult
from support.toy import make_workspace

BAD_MODULE = "import os\n\n\ndef f(a: int)->str:\n    return a\n"


def _check(repo: Repo, *argv: str) -> RunResult:
    argv = (
        "--skip",
        ["--format", "json", "check", "--skip", "tests,secrets,docs-fresh,licenses,mutation,workflows", *argv],
    return repo.run(["--format", "json", "check", *argv], {"check": make_handler(SubprocessToolRunner())})


def _statuses(result: RunResult) -> dict[str, str]:
    return {s["name"]: s["status"] for s in json.loads(result.out)["steps"]}


def _uv_lock(repo: Repo) -> None:
    subprocess.run(["uv", "lock"], cwd=repo.root, check=True, capture_output=True)  # noqa: S607  # B-034: uv from PATH


def test_ruff_mypy_on_toy_package(repo: Repo) -> None:
    make_workspace(repo, ["a"])
    clean = _check(repo, "--skip", "lock")
    assert clean.code == 0, clean.out
    assert set(_statuses(clean).values()) == {"pass"}
    repo.commit({"pkgs/a/src/a/mod.py": BAD_MODULE})
    bad = _check(repo, "--skip", "lock")
    assert bad.code == 1
    assert _statuses(bad) == {
        "config": "pass", "format": "fail", "lint": "fail", "types": "fail", "forbidden": "pass", "ratchet": "pass",
    }  # fmt: skip
    codes = {f["code"] for s in json.loads(bad.out)["steps"] for f in s["findings"]}
    assert codes == {"ST001"}


def test_stray_config_files_cannot_change_a_tool(repo: Repo) -> None:
    """A ruff.toml next to the package does not relax the explicit configuration."""
    long_line = "# " + "x" * 130 + "\n"
    make_workspace(repo, ["a"], module='"""Doc."""\n' + long_line)
    repo.commit({"pkgs/a/ruff.toml": "line-length = 500\n"})
    assert _statuses(_check(repo, "--only", "lint")) == {"lint": "fail"}


def test_stale_lock_is_st001(repo: Repo) -> None:
    make_workspace(repo, ["a"])
    _uv_lock(repo)
    assert _statuses(_check(repo, "--only", "lock")) == {"lock": "pass"}
    pyproject = repo.root / "pkgs" / "a" / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('version = "0.1.0"', 'version = "0.2.0"'), encoding="utf-8")
    stale = _check(repo, "--only", "lock")
    assert stale.code == 1
    (step,) = json.loads(stale.out)["steps"]
    assert step["name"] == "lock"
    assert step["findings"][0]["code"] == "ST001"
