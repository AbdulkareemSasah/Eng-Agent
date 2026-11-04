"""The module globs of ``[tool.eng-gate]`` select where FB004 and FB005 apply (spec 4.8, section 5)."""

from __future__ import annotations

import pytest
from eng_dev_gate.checks.forbidden.engine import scan_member
from eng_dev_gate.checks.forbidden.rules_b import RULES_B
from eng_dev_gate.config import ConfigError
from eng_dev_gate.workspace import Member
from support.forbidden import lines, policy
from support.repo import Repo
from support.toy import GATE_YML, POLICY_TEXT, member_pyproject, root_pyproject

TABLE = (
    '\n[tool.eng-gate]\nprofile = "tool"\nlayer = "tool"\nimport_names = ["a"]\ncoverage_line = 95\n'
    'coverage_branch = 90\nblock_modules = ["src/a/blocks/*.py"]\ncalc_modules = ["src/a/calc.py"]\n'
)
SOURCE = "import os\nX = 1\n"


def _member(repo: Repo, table: str) -> Member:
    repo.commit(
        {
            "pyproject.toml": root_pyproject(["pkgs/a"]),
            ".gate/gate.yml": GATE_YML,
            ".gate/forbidden.yml": POLICY_TEXT,
            "pkgs/a/pyproject.toml": member_pyproject("a") + table,
            "pkgs/a/src/a/blocks/beam.py": SOURCE,
            "pkgs/a/src/a/calc.py": SOURCE,
            "pkgs/a/src/a/other.py": SOURCE,
        }
    )
    return Member(name="a", path="pkgs/a", directory=repo.root / "pkgs" / "a")


def test_globs_of_the_member_table_select_the_files(repo: Repo) -> None:
    member = _member(repo, TABLE)
    findings = scan_member(repo.root, member, policy(), RULES_B, [])
    got = sorted((f.path or "", f.code, f.line or 0) for f in findings)
    assert got == [
        ("pkgs/a/src/a/blocks/beam.py", "FB004", 1),
        ("pkgs/a/src/a/blocks/beam.py", "FB005", 2),
        ("pkgs/a/src/a/calc.py", "FB005", 2),
    ]


def test_member_without_a_table_has_no_module_globs(repo: Repo) -> None:
    member = _member(repo, "")
    assert scan_member(repo.root, member, policy(), RULES_B, []) == []  # the config step reports CF006


def test_invalid_table_is_a_usage_error(repo: Repo) -> None:
    member = _member(repo, TABLE + "unknown = 1\n")
    with pytest.raises(ConfigError):
        scan_member(repo.root, member, policy(), RULES_B, [])


def test_tests_scope_does_not_need_globs(repo: Repo) -> None:
    member = _member(repo, "")
    repo.commit({"pkgs/a/tests/conftest.py": "collect_ignore = []\n", "pkgs/a/tests/test_a.py": "x = lines\n"})
    findings = scan_member(repo.root, member, policy(), RULES_B, [])
    assert lines(findings, "FB008") == [1]
