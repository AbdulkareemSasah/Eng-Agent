"""The user-level task-log push file (spec 0015 section 4.6; ADR-0034 D6).

Standard library only: the pre-push hook embeds this file's source (plan 0015 T8h), so it must import nothing from
`eng_harness` or `pydantic`.
"""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

__all__ = ["PushConfig", "PushFileError", "default_push_file", "read_push_file"]

_PUSH_KEYS = ("push", "integration_branch", "remote")
"""The only keys the push file may hold (spec 0015 4.6: `push`, `integration_branch`, the remote URL)."""
_APP_DIRNAME = "eng-harness"
"""The folder of the push file inside the user's configuration folder (spec 0015 4.6)."""
_PUSH_FILENAME = "tasklog-push.toml"
"""The push file name inside `_APP_DIRNAME` (spec 0015 4.6)."""
_GIT_DIRNAME = ".git"
"""The entry whose presence in a folder or any parent marks a git working tree."""
_APPDATA_VARIABLE = "APPDATA"
"""The variable holding the user's configuration folder on Windows (spec 0015 4.6)."""
_XDG_CONFIG_VARIABLE = "XDG_CONFIG_HOME"
"""The variable holding the user's configuration folder elsewhere, else `~/.config` (spec 0015 4.6)."""


class PushFileError(Exception):
    """The push file is absent, invalid or inside a git working tree; raised before any push."""


@dataclass(frozen=True)
class PushConfig:
    """The validated push file: the push permission, the integration branch and the remote URL."""

    push: bool
    integration_branch: str
    remote: str


def _inside_work_tree(path: Path) -> bool:
    """Whether `path` resolves to a file inside a git working tree (spec 0015 4.6).

    The walk for a `.git` entry needs no subprocess and works without git; resolving first also catches a file
    reached through a link from outside.
    """
    try:
        resolved = path.resolve()
    except OSError, RuntimeError:
        resolved = path.absolute()
    return any((parent / _GIT_DIRNAME).exists() for parent in (resolved.parent, *resolved.parent.parents))


def read_push_file(path: Path) -> PushConfig:
    """Read and validate the user-level push file at `path` (spec 0015 4.6).

    Raises:
        PushFileError: the file is absent, invalid (unknown or missing keys, wrong types, a blank branch or
            remote URL) or inside a git working tree. Messages name the key, never the value, because the
            remote URL may carry credentials.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise PushFileError(f"{path}: push file not found") from error
    except OSError as error:
        raise PushFileError(f"{path}: cannot read push file: {error}") from error
    if _inside_work_tree(path):
        raise PushFileError(f"{path}: push file must not lie inside a git working tree")
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PushFileError(f"{path}: invalid push file: {error}") from error
    unknown = set(data) - set(_PUSH_KEYS)
    if unknown:
        raise PushFileError(f"{path}: unknown push file key {min(unknown)!r}")
    missing = set(_PUSH_KEYS) - set(data)
    if missing:
        raise PushFileError(f"{path}: missing push file key {min(missing)!r}")
    push = data["push"]
    if not isinstance(push, bool):
        raise PushFileError(f"{path}: push file key 'push' must be a boolean")
    branch = data["integration_branch"]
    if not isinstance(branch, str) or not branch.strip():
        raise PushFileError(f"{path}: push file key 'integration_branch' must be a non-blank string")
    remote = data["remote"]
    if not isinstance(remote, str) or not remote.strip():
        raise PushFileError(f"{path}: push file key 'remote' must be a non-blank string")
    return PushConfig(push=push, integration_branch=branch, remote=remote)


def default_push_file() -> Path:
    """The user-level push file (spec 0015 4.6): `%APPDATA%/eng-harness/tasklog-push.toml` on Windows, else
    `$XDG_CONFIG_HOME/eng-harness/tasklog-push.toml` or `~/.config/eng-harness/tasklog-push.toml`."""
    if os.name == "nt":
        root = os.getenv(_APPDATA_VARIABLE) or str(Path.home() / "AppData" / "Roaming")
    else:
        root = os.getenv(_XDG_CONFIG_VARIABLE) or str(Path.home() / ".config")
    return Path(root) / _APP_DIRNAME / _PUSH_FILENAME
