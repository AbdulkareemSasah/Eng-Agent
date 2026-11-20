"""Integration tests of the lock, format, lint and types steps with the real tools on a toy workspace."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from eng_dev_gate.checks.check import make_handler
from eng_dev_gate.toolrun import SubprocessToolRunner
from support.judged_tree import MISTYPED_USE, USES_DEPENDENCY, make_gate_root, make_judged_tree, stubbed_dependency
from support.repo import Repo, RunResult
from support.toy import make_workspace

BAD_MODULE = "import os\n\n\ndef f(a: int)->str:\n    return a\n"


def _check(repo: Repo, *argv: str) -> RunResult:
    argv = (
        "--skip",
        "tests,secrets,docs-fresh,licenses,mutation,workflows",
        *argv,
    )  # covered by test_coverage.py and test_secrets.py
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
        "config": "pass", "format": "fail", "lint": "fail", "types": "fail", "forbidden": "pass",
        "imports": "pass", "ratchet": "pass",
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


def _judge_types(gate: Repo, head: Repo) -> tuple[int, list[tuple[str, str]], str]:
    argv = ["--gate-root", str(gate.root), "--format", "json", "check", "--only", "types"]
    result = head.run(argv, {"check": make_handler(SubprocessToolRunner())})
    assert result.out, f"no report (exit {result.code}): {result.err[:600]}"
    (step,) = json.loads(result.out)["steps"]
    return result.code, [(f["code"], f["message"]) for f in step["findings"]], step["status"]


def test_types_resolve_in_judged_environment(tmp_path: Path) -> None:
    """AC54a: a dependency and its stub distribution that only the judged lock file installs resolve in ``types``."""
    gate = make_gate_root(tmp_path / "base")
    head = make_judged_tree(tmp_path / "head", extra_files=stubbed_dependency(USES_DEPENDENCY))
    assert _judge_types(gate, head) == (0, [], "pass")


def test_types_still_report_errors_against_the_judged_stubs(tmp_path: Path) -> None:
    """The stubs of the judged environment are used: ``f`` returns ``int``, so assigning it to ``str`` fails."""
    gate = make_gate_root(tmp_path / "base")
    head = make_judged_tree(tmp_path / "head", extra_files=stubbed_dependency(MISTYPED_USE))
    code, findings, status = _judge_types(gate, head)
    assert (code, status, [c for c, _ in findings]) == (1, "fail", ["ST001"])
    assert "Incompatible types in assignment" in findings[0][1]


def test_types_with_a_stale_lock_is_st001_of_the_step(tmp_path: Path) -> None:
    """A requirement the lock file lacks cannot be installed: ST001 of ``types``, not an environment fault."""
    gate, head = make_gate_root(tmp_path / "base"), make_judged_tree(tmp_path / "head")
    head.commit({"pkgs/a/pyproject.toml": stubbed_dependency("")["pyproject.toml"]}, "chore: stale")
    code, findings, status = _judge_types(gate, head)
    assert (code, [c for c, _ in findings], status) == (1, ["ST001"], "fail")
    assert findings[0][1].startswith("types: uv.lock of the judged tree is not up to date")
