"""Workspace member discovery from ``[tool.uv.workspace]`` of the root ``pyproject.toml``."""

from __future__ import annotations

import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict

from eng_dev_gate.globs import matches_any
from eng_dev_gate.results import UsageError


class Member(BaseModel):
    """A workspace member: project ``name``, POSIX ``path`` relative to the root, absolute ``directory``."""

    model_config = ConfigDict(frozen=True)

    name: str
    path: str
    directory: Path


def _load(path: Path) -> dict[str, Any]:  # Any: TOML tables are untyped data at this boundary
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise UsageError(f"cannot read {path}: {error}") from error


def _string_list(table: dict[str, Any], key: str, required: bool) -> list[str]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value) or (required and not value):
        raise UsageError(f"[tool.uv.workspace].{key} must be {'a non-empty ' if required else 'a '}list of strings")
    return value


def discover_members(root: Path) -> list[Member]:
    """Return the members of the uv workspace at ``root``, sorted by path.

    Member patterns are expanded relative to ``root``; folders without a ``pyproject.toml`` are skipped for a glob
    pattern but are an error for an explicit path; ``exclude`` patterns remove members.

    Raises:
        UsageError: no root ``pyproject.toml``, no ``[tool.uv.workspace]`` table, malformed TOML, an explicit
            member without ``pyproject.toml``, or a member without ``[project].name``.
    """
    table = _load(root / "pyproject.toml").get("tool", {}).get("uv", {}).get("workspace")
    if not isinstance(table, dict):
        raise UsageError(f"{root / 'pyproject.toml'} has no [tool.uv.workspace] table")
    patterns = _string_list(table, "members", required=True)
    excludes = _string_list(table, "exclude", required=False)
    found: dict[str, Path] = {}
    for pattern in patterns:
        explicit = not any(c in pattern for c in "*?[")
        candidates = [root / pattern] if explicit else sorted(p for p in root.glob(pattern) if p.is_dir())
        for directory in candidates:
            rel = PurePosixPath(directory.relative_to(root).as_posix()).as_posix()
            if matches_any(rel, excludes):
                continue
            if not (directory / "pyproject.toml").is_file():
                if explicit:
                    raise UsageError(f"workspace member {rel} has no pyproject.toml")
                continue
            found[rel] = directory
    members = []
    for rel in sorted(found):
        name = _load(found[rel] / "pyproject.toml").get("project", {}).get("name")
        if not isinstance(name, str) or not name:
            raise UsageError(f"workspace member {rel} has no [project].name")
        members.append(Member(name=name, path=rel, directory=found[rel]))
    return members
