"""Helpers of the tests of FB004 to FB006 and FB008: a scanner that sets the module globs of the package."""

from __future__ import annotations

import re

from eng_dev_gate.checks.forbidden.engine import ModuleGlobs, scan_file
from eng_dev_gate.checks.forbidden.rules_b import RULES_B
from eng_dev_gate.report import Finding

from support.forbidden import policy

ALL_MODULES = ModuleGlobs(
    check=("src/pkg/checks/**",), calc=("src/pkg/calc/**",), block=("src/pkg/blocks/**",), rule=("src/pkg/rules/**",)
)


def scan_b(source: str, local: str, modules: ModuleGlobs = ALL_MODULES) -> list[Finding]:
    """Scan ``source`` as the file ``local`` of the package ``pkgs/x`` with the rules of part 2 and ``modules``."""
    return scan_file(f"pkgs/x/{local}", local, source.encode("utf-8"), policy(), RULES_B, modules)


def expected_lines(source: str) -> list[int]:
    """Return the line of every finding the markers announce: ``# <-`` is one finding, ``# <-2`` is two."""
    found: list[int] = []
    for number, line in enumerate(source.splitlines(), 1):
        if match := re.search(r"# <-(\d?)\s*$", line):
            found.extend([number] * int(match.group(1) or "1"))
    return found
