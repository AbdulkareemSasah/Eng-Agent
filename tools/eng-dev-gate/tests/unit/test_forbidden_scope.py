"""Scope of the forbidden check (spec 4.8, AC37): spikes, tests, docstrings, comments, waivers, parse errors."""

from __future__ import annotations

from typing import Literal

import pytest
from eng_dev_gate.checks.forbidden.engine import ForbiddenConfig, Rule, Unit, scan_file, scan_member
from eng_dev_gate.checks.forbidden.rules_a import RULES_A
from eng_dev_gate.config import load_gate_config
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import UsageError
from eng_dev_gate.workspace import Member
from support.forbidden import lines, policy, scan
from support.repo import Repo
from support.toy import GATE_YML, POLICY_TEXT, member_pyproject, root_pyproject

VIOLATIONS = 'print("x")\neval("1")\nname = "csi_run_script"\n'

MODULE = '''\
"""csi_run_script"""
# print("comment"); eval("x"); csi_run_script
import os


def f() -> str:
    """csi_run_script"""
    note = "print(1) eval('x') csi_run_script"
    print("real")  # noqa: T201
    eval("1")  # noqa
    # eng-gate: allow FB002
    exec("1")  # gate: ignore[FB002]
    os.system("ls")
    return note
'''


def _workspace(repo: Repo) -> Member:
    repo.commit(
        {
            "pyproject.toml": root_pyproject(["pkgs/a", "spikes/s"]),
            ".gate/gate.yml": GATE_YML,
            ".gate/forbidden.yml": POLICY_TEXT,
            "pkgs/a/pyproject.toml": member_pyproject("a"),
            "pkgs/a/src/a/mod.py": MODULE,
            "pkgs/a/tests/test_mod.py": VIOLATIONS,
            "pkgs/a/conftest.py": VIOLATIONS,
            "spikes/s/pyproject.toml": member_pyproject("s"),
            "spikes/s/src/s/mod.py": VIOLATIONS,
        }
    )
    return Member(name="a", path="pkgs/a", directory=repo.root / "pkgs" / "a")


def test_spikes_tests_and_waivers(repo: Repo) -> None:
    member = _workspace(repo)
    spike = Member(name="s", path="spikes/s", directory=repo.root / "spikes" / "s")
    spike_globs = load_gate_config(repo.root).spike_globs
    findings = scan_member(repo.root, member, policy(), RULES_A, spike_globs)
    assert {f.path for f in findings} == {"pkgs/a/src/a/mod.py"}  # not tests, not conftest.py
    assert lines(findings, "FB007") == [9]  # docstrings, comments and plain strings are not code
    assert lines(findings, "FB002") == [10, 12, 13]  # no inline waiver exists
    assert len(findings) == 4
    assert scan_member(repo.root, spike, policy(), RULES_A, spike_globs) == []  # spike code
    assert scan_member(repo.root, spike, policy(), RULES_A, []) != []  # the glob alone excludes it


def test_unparseable_file_is_fb000() -> None:
    for data in (b"def broken(:\n", b"x = 1\n\x00\n", b"# coding: utf-8\nx = '\xff'\n"):
        (finding,) = scan_file("pkgs/x/src/p/m.py", "src/p/m.py", data, policy(), RULES_A)
        assert (finding.code, finding.severity, finding.path) == ("FB000", Severity.ERROR, "pkgs/x/src/p/m.py")
    (syntax,) = scan_file("p.py", "src/p.py", b"x = 1\ny = (\n", policy(), RULES_A)
    assert syntax.line is not None


def _marking(code: str, scope: Literal["src", "tests"]) -> Rule:
    def check(unit: Unit, _config: ForbiddenConfig) -> list[Finding]:
        return [Finding(code=code, severity=Severity.ERROR, path=unit.path, line=1, message="seen")]

    return Rule(code=code, scope=scope, check=check)


def test_scope_selects_tests_for_a_tests_rule(repo: Repo) -> None:
    """A rule with scope ``tests`` sees ``tests/**`` and every ``conftest.py``; a ``src`` rule sees ``src/**``."""
    member = _workspace(repo)
    repo.commit({"pkgs/a/tests/sub/test_deep.py": "x = 1\n", "pkgs/a/src/a/conftest.py": "x = 1\n"})
    rules = (_marking("FB901", "tests"), _marking("FB902", "src"))
    seen = scan_member(repo.root, member, policy(), rules, [])
    by_code = {c: sorted(f.path or "" for f in seen if f.code == c) for c in ("FB901", "FB902")}
    assert by_code["FB901"] == [
        "pkgs/a/conftest.py", "pkgs/a/src/a/conftest.py", "pkgs/a/tests/sub/test_deep.py", "pkgs/a/tests/test_mod.py",
    ]  # fmt: skip
    assert by_code["FB902"] == ["pkgs/a/src/a/conftest.py", "pkgs/a/src/a/mod.py"]


def test_unreadable_source_is_a_usage_error(repo: Repo) -> None:
    member = _workspace(repo)
    (repo.root / "pkgs" / "a" / "src" / "a" / "folder.py").mkdir()  # a directory that looks like a source file
    with pytest.raises(UsageError):
        scan_member(repo.root, member, policy(), RULES_A, [])


def test_calls_without_a_dotted_name_are_ignored() -> None:
    assert scan("make()(1)\nf(**options)\nitems[0](2)\nx = (lambda: 1)()\n") == []


def test_scan_of_text_has_no_waiver() -> None:
    assert lines(scan("print(1)  # noqa\n"), "FB007") == [1]
    assert lines(scan("print(1)  # fmt: skip\n"), "FB007") == [1]
