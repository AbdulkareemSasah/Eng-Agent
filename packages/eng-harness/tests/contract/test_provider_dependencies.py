"""The provider dependencies are declared, locked at exact versions and each has its package ADR (spec 0009 AC46)."""

import re
import tomllib
from pathlib import Path

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
    project = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = {_name(r): r for r in project["dependencies"]}
    locked = {p["name"]: p["version"] for p in tomllib.loads(LOCK.read_text(encoding="utf-8"))["package"]}
    for name, adr in ADRS.items():
        assert name in declared, f"{name} is not a runtime dependency"
        assert re.fullmatch(r"\d+(\.\d+)*", locked[name]), f"{name} is not locked at an exact version"
        assert (PACKAGE / "docs" / "adr" / adr).is_file()
    assert "[openai]" in declared["pydantic-ai-slim"]
    assert re.search(r"==\s*" + re.escape(locked["pydantic-ai-slim"]) + r"$", declared["pydantic-ai-slim"])
