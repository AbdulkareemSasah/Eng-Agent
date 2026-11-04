"""Tests of the ratchet (spec 4.9, AC38 to AC41): marker counting, reasons, expiry dates and issue references."""

from __future__ import annotations

import json
from datetime import date

import pytest
from eng_dev_gate.checks import ratchet
from eng_dev_gate.config import load_gate_config
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import UsageError
from support.repo import Repo
from support.toy import make_workspace

TODAY = date(2026, 6, 15)


class FixedClock:
    """A clock that always reports ``TODAY``."""

    def today(self) -> date:
        return TODAY


def _run(repo: Repo) -> list[Finding]:
    config = load_gate_config(repo.root)
    return ratchet.check_ratchet(repo.root, repo.root, config, FixedClock(), False)


def _codes(findings: list[Finding]) -> list[tuple[str, Severity]]:
    return [(f.code, f.severity) for f in findings]


def _recorded(counts: dict[str, dict[str, int]]) -> dict[str, str]:
    return {".gate/ratchet.json": json.dumps({"version": 1, "counts": counts})}


MARKERS = """import unittest

import pytest

pytestmark = pytest.mark.xfail(reason="B-1, expires 2027-01-01")
NOT_A_COMMENT = "x = 1  # noqa: E501 and # type: ignore"
a = 1  # noqa: E501 B-1
b = 2  # ruff: noqa: E501 B-1
c: int = 3  # type: ignore[assignment]  # B-1
d = 4  # mypy: ignore-errors B-1
e = 5  # pragma: no cover
f = 6  # pragma: no branch
PARAMS = [pytest.param(1, marks=pytest.mark.skip(reason="B-1, expires 2027-01-01"))]


@pytest.mark.skipif(True, reason="B-1, expires 2027-01-01")
def test_one() -> None:
    pytest.skip("B-1, expires 2027-01-01")
    pytest.importorskip("json", reason="B-1, expires 2027-01-01")
    pytest.xfail("B-1, expires 2027-01-01")


class Case(unittest.TestCase):
    @unittest.skip("B-1, expires 2027-01-01")
    def test_two(self) -> None:
        self.skipTest("B-1, expires 2027-01-01")
"""


def test_counts_and_rise(repo: Repo) -> None:
    """AC38: markers are counted per bucket from comments and the syntax tree; a rise is RT001, a drop a notice."""
    counts = dict.fromkeys(ratchet.BUCKETS, 0)
    for marker in ratchet.scan_source(MARKERS, "m.py"):
        counts[marker.bucket] += 1
    assert counts == {"noqa": 2, "type_ignore": 2, "pragma_no_cover": 2, "skip": 6, "xfail": 2}

    make_workspace(repo, ["a", "b"], module="x = 1  # noqa: E501 B-1\ny = 2  # noqa: E501 B-2\n")
    repo.commit(_recorded({"pkgs/a": {"noqa": 2}}))
    findings = _run(repo)
    assert _codes(findings) == [("RT001", Severity.ERROR)]  # pkgs/b is absent from the file: its zero is exceeded
    assert "pkgs/b" in findings[0].message
    assert "noqa" in findings[0].message

    repo.commit(_recorded({"pkgs/a": {"noqa": 5}, "pkgs/b": {"noqa": 2}}))
    findings = _run(repo)
    assert _codes(findings) == [("RT001", Severity.NOTICE)]
    assert "ratchet --update" in findings[0].message
    assert "pkgs/a" in findings[0].message


def test_skip_xfail_reasons() -> None:
    """AC39: a skip or xfail needs an issue reference (RT002) and a valid (RT003), unexpired (RT004) expiry."""
    source = "\n".join(
        [
            "import pytest",
            '@pytest.mark.skip(reason="B-12, expires 2026-12-31")',
            "def test_ok() -> None: ...",
            '@pytest.mark.skip(reason="B-12, expires 2026-06-15")',
            "def test_today_is_valid() -> None: ...",
            "@pytest.mark.skip",
            "def test_bare() -> None: ...",
            '@pytest.mark.xfail(reason="see #7")',
            "def test_no_date() -> None: ...",
            '@pytest.mark.skipif(True, reason="B-3, expires 2026-13-45")',
            "def test_bad_date() -> None: ...",
            '@pytest.mark.xfail(reason="B-3, expires 2026-06-14")',
            "def test_expired() -> None: ...",
            "def test_call() -> None:",
            '    pytest.skip("expires 2027-01-01")',
            "",
        ]
    )
    findings = ratchet.marker_findings(ratchet.scan_source(source, "t.py"), "t.py", TODAY)
    expected = [("RT002", 6), ("RT003", 6), ("RT003", 8), ("RT003", 10), ("RT004", 12), ("RT002", 15)]
    assert sorted((f.code, f.line) for f in findings) == sorted(expected)
    assert {f.path for f in findings} == {"t.py"}


def test_suppression_issue_reference() -> None:
    """AC41: a noqa or type: ignore comment needs an issue reference; mypy takes it in a second comment."""
    source = "\n".join(
        [
            "a = 1  # noqa: E501",
            "b = 2  # noqa: E501 B-5",
            "c = 3  # noqa: E501 - see #5",
            "d: int = 'x'  # type: ignore[assignment]",
            "e: int = 'x'  # type: ignore[assignment]  # B-5",
            "f = 6  # pragma: no cover",
            "",
        ]
    )
    findings = ratchet.marker_findings(ratchet.scan_source(source, "s.py"), "s.py", TODAY)
    assert [(f.code, f.line) for f in findings] == [("RT006", 1), ("RT006", 4)]


def test_unparsable_source_is_a_usage_error() -> None:
    with pytest.raises(UsageError):
        ratchet.scan_source("def broken(:\n", "bad.py")
