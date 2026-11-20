"""The pack through `python -m structural_codes verify` (plan 0003 T3; AC17)."""

import subprocess  # B-327: the test runs this interpreter with fixed arguments
import sys
from pathlib import Path

_ROOT = Path(__file__).parents[2]


def test_verify_reports_unverified() -> None:
    """Exit 0, every boundary case passes, every check not verified (no worked example, G-WE) (AC17)."""
    done = subprocess.run(  # noqa: S603  # B-327: fixed arguments, no shell, no untrusted input
        [sys.executable, "-m", "structural_codes", "verify", "--pack", str(_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (done.returncode, done.stderr) == (0, "")
    lines = done.stdout.splitlines()
    assert len(lines) == 9
    for line in lines:
        assert " not verified " in line
        assert "fail=0" in line
        assert "no passing worked_example" in line
        assert "pass=" in line
        # Each file has one boundary case that must pass (spec 0003 §9).
        assert "pass=1" in line
