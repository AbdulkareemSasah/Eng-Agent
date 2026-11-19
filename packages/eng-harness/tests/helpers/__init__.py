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
    """Load a JSON object from a workspace-root file, skipping only under ``MUTANT_UNDER_TEST`` when absent.

    ``reason`` documents which workspace file the caller needs. The skip string itself is a string literal so the
    ratchet can read the issue reference and expiry (RT002, RT003; same form as B-369).
    """
    if not path.is_file() and "MUTANT_UNDER_TEST" in os.environ:
        assert "B-" in reason, reason
        assert "expires " in reason, reason
        pytest.skip("workspace-root file absent under MUTANT_UNDER_TEST (B-301); expires 2026-12-31")
    return load_json_dict(path)
