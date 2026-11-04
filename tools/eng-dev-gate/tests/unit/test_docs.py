"""Documentation tests: the README covers every command with an example (plan task T25, AC64 support)."""

from __future__ import annotations

import re
from pathlib import Path

from eng_dev_gate.cli import COMMANDS

PACKAGE = Path(__file__).resolve().parents[2]


def _readme() -> str:
    return (PACKAGE / "README.md").read_text(encoding="utf-8")


def test_readme_lists_every_command() -> None:
    text = _readme()
    missing = [c for c in COMMANDS if not re.search(rf"^\s*(uv run )?eng-gate .*\b{re.escape(c)}\b", text, re.M)]
    assert missing == []  # every command has an example line `eng-gate ... <command>`


def test_readme_has_no_skeleton_status() -> None:
    assert "not implemented yet" not in _readme()


def test_readme_documents_exit_codes_and_diagnostics() -> None:
    text = _readme()
    for code in ("0", "1", "2", "3"):
        assert re.search(rf"\b{code}\b", text)
    assert "awaiting owner" in text


def test_changelog_has_release_section() -> None:
    text = (PACKAGE / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(r"^## 0\.1\.0\b", text, re.M)
