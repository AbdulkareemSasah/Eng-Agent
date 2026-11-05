"""The pack through `python -m structural_codes verify` (plan 0002 T9; PK-AC8)."""

import re
import subprocess  # B-278: the test runs this interpreter with fixed arguments
import sys
from pathlib import Path

_ROOT = Path(__file__).parents[2]


def test_verify_reports_unverified() -> None:
    """Exit 0, no failing case, program comparisons pending, no check verified (worked example missing) (PK-AC8)."""
    done = subprocess.run(  # noqa: S603  # B-278: fixed arguments, no shell, no untrusted input
        [sys.executable, "-m", "structural_codes", "verify", "--pack", str(_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (done.returncode, done.stderr) == (0, "")
    lines = done.stdout.splitlines()
    assert len(lines) == 6
    for line in lines:
        assert " not verified " in line
        assert "fail=0" in line
        assert "no passing worked_example" in line
    pending = [line for line in lines if not re.search(r"pending=0\b", line)]
    assert len(pending) == 5  # every check but the development length has a program comparison
