"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from support.repo import Repo, make_repo


@pytest.fixture(autouse=True)
def _no_ambient_ci_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never see the event, summary or Actions variables of the CI run that executes them."""
    for name in ("GITHUB_EVENT_PATH", "GITHUB_STEP_SUMMARY", "GITHUB_ACTIONS"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    """An empty temporary git repository."""
    return make_repo(tmp_path / "repo")
