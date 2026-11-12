"""The provider dependencies are declared, locked at exact versions and each has its package ADR (spec 0009 AC46)."""

import os
import re
import tomllib
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2]
LOCK = PACKAGE.parents[1] / "uv.lock"
ADRS = {
    "pydantic-ai-slim": "0001-pydantic-ai-slim.md",
    "keyring": "0002-keyring.md",
    "httpx2": "0003-httpx2.md",
}


def _name(requirement: str) -> str:
    return re.split(r"[\[<>=!~ ;]", requirement, maxsplit=1)[0].lower().replace("_", "-")


def test_declared_and_locked() -> None:
    """The lock sits at the workspace root, outside the member; mutmut's copy of the member (`MUTANT_UNDER_TEST` set)
    lacks it, so only there, after the declaration and ADR assertions, a missing lock skips (as B-369, B-423, B-444).
    """
    project = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = {_name(r): r for r in project["dependencies"]}
    for name, adr in ADRS.items():
        assert name in declared, f"{name} is not a runtime dependency"
        assert (PACKAGE / "docs" / "adr" / adr).is_file()
    assert "[openai]" in declared["pydantic-ai-slim"]
    if not LOCK.is_file() and "MUTANT_UNDER_TEST" in os.environ:
        pytest.skip("the workspace lock is outside the copy the mutation step runs (B-449); expires 2026-12-31")
    locked = {p["name"]: p["version"] for p in tomllib.loads(LOCK.read_text(encoding="utf-8"))["package"]}
    for name in ADRS:
        assert re.fullmatch(r"\d+(\.\d+)*", locked[name]), f"{name} is not locked at an exact version"
    assert re.search(r"==\s*" + re.escape(locked["pydantic-ai-slim"]) + r"$", declared["pydantic-ai-slim"])
