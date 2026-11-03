"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from support.repo import Repo, make_repo


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    """An empty temporary git repository."""
    return make_repo(tmp_path / "repo")
