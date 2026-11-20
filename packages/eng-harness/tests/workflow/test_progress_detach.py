"""A raising TerminalProgress is detached and the run continues (plan 0006 T17; AC19)."""

from pathlib import Path

import pytest


def test_raising_renderer_detached_run_continues(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    raise AssertionError("T17: raising-renderer detach re-check not yet written")
