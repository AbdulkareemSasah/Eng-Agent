"""Tests of the ``docs-fresh`` generated-document check (spec 4.12; AC52) with a real generator module."""

from __future__ import annotations

import pytest
from eng_dev_gate.checks import generated
from eng_dev_gate.checks.registry import StepContext
from eng_dev_gate.results import EnvironmentFaultError
from eng_dev_gate.toolrun import SubprocessToolRunner
from eng_dev_gate.workspace import discover_members
from support.repo import Repo
from support.toy import make_workspace, member_pyproject

TABLE = (
    '[tool.eng-gate]\nprofile = "tool"\nlayer = "tool"\nimport_names = ["a"]\n'
    "coverage_line = 95\ncoverage_branch = 90\n"
)
GENERATOR = 'import sys\nsys.stdout.write("line one\\nargs=" + ",".join(sys.argv[1:]) + "\\n")\n'
RENDERED = "line one\nargs=x,y\n"


def _entry(module: str = "a.gen", path: str = "OUT.md") -> str:
    return f'[[tool.eng-gate.generated]]\npath = "{path}"\nmodule = "{module}"\nargs = ["x", "y"]\n'


def _context(repo: Repo, committed: bytes | None, entry: str | None = None) -> StepContext:
    make_workspace(repo, ["a"])
    repo.write({"pkgs/a/pyproject.toml": member_pyproject("a") + TABLE + (entry or _entry())})
    repo.write({"pkgs/a/a/__init__.py": "", "pkgs/a/a/gen.py": GENERATOR})
    if committed is not None:
        (repo.root / "pkgs/a/OUT.md").write_bytes(committed)
    member = discover_members(repo.root)[0]
    return StepContext(repo.root, repo.root, member, SubprocessToolRunner())


def test_freshness(repo: Repo) -> None:
    """AC52: regeneration equal to the committed document (line endings normalized) passes; a difference is GF001."""
    assert generated.generated(_context(repo, RENDERED.encode())) == []
    assert generated.generated(_context(repo, RENDERED.replace("\n", "\r\n").encode())) == []
    (stale,) = generated.generated(_context(repo, b"line one\nargs=old\n"))
    assert (stale.code, stale.severity.value, stale.path) == ("GF001", "error", "pkgs/a/OUT.md")
    assert "args=old" in stale.message
    (missing,) = generated.generated(_context(repo, None))
    assert missing.code == "GF001"


def test_no_entries_is_clean(repo: Repo) -> None:
    """A member without ``generated`` entries (or without the table) has nothing to check."""
    make_workspace(repo, ["a"])
    member = discover_members(repo.root)[0]
    assert generated.generated(StepContext(repo.root, repo.root, member, SubprocessToolRunner())) == []


@pytest.mark.parametrize("module", ["a.nowhere", "os", "a.gen --version"])
def test_generator_that_cannot_run_is_gf002(repo: Repo, module: str) -> None:
    """GF002 (exit 3): the module is missing, fails, or does not belong to a workspace package."""
    ctx = _context(repo, RENDERED.encode(), _entry(module))
    with pytest.raises(EnvironmentFaultError, match="GF002"):
        generated.generated(ctx)
