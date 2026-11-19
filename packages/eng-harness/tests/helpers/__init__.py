"""Shared helpers for eng-harness tests."""

import json
import os
from pathlib import Path
from typing import Any

import pytest


def load_json_dict(path: Path) -> dict[str, Any]:
    """Load a JSON object from ``path``."""
    with path.open("rb") as handle:
        data = json.load(handle)
    assert isinstance(data, dict)
    return data


def load_repo_json(path: Path, *, reason: str) -> dict[str, Any]:
    """Load a JSON object from a workspace-root file, skipping only under ``MUTANT_UNDER_TEST`` when absent."""
    if not path.is_file() and "MUTANT_UNDER_TEST" in os.environ:
        pytest.skip(reason)
    return load_json_dict(path)
