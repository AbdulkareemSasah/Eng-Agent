"""Helpers of the forbidden tests: the committed policy and a scanner for a source text."""

from __future__ import annotations

from eng_dev_gate.checks.forbidden.engine import ForbiddenConfig, Rule, parse_config, scan_file
from eng_dev_gate.checks.forbidden.rules_a import RULES_A
from eng_dev_gate.report import Finding

from support.toy import POLICY_FILE, POLICY_TEXT

MARK = "# <-"  # a source line that must be flagged ends with this marker


def policy() -> ForbiddenConfig:
    """Return the committed ``.gate/forbidden.yml`` parsed."""
    return parse_config(POLICY_TEXT, str(POLICY_FILE))


def scan(source: str, local: str = "src/pkg/mod.py", rules: tuple[Rule, ...] = RULES_A) -> list[Finding]:
    """Scan ``source`` as the file ``local`` (relative to its package) of the package ``pkgs/x``."""
    return scan_file(f"pkgs/x/{local}", local, source.encode("utf-8"), policy(), rules)


def marked(source: str) -> list[int]:
    """Return the 1-based numbers of the lines that end with :data:`MARK`."""
    return [n for n, line in enumerate(source.splitlines(), 1) if line.rstrip().endswith(MARK)]


def lines(findings: list[Finding], code: str) -> list[int]:
    """Return the sorted lines of the findings with ``code``."""
    return sorted(f.line for f in findings if f.code == code and f.line is not None)
