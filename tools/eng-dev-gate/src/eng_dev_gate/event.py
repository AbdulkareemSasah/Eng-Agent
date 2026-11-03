"""Reader of the GitHub event file (spec 4.5 inputs). Its content is data and never executed."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from eng_dev_gate.results import UsageError


class _Repo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    full_name: str


class _Label(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str


class _Ref(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ref: str
    sha: str
    repo: _Repo | None = None


class _User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    login: str


class _RawPullRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    number: int
    title: str
    body: str | None = None
    draft: bool = False
    base: _Ref
    head: _Ref
    user: _User
    labels: list[_Label] = []


class PullRequest(BaseModel):
    """The pull-request fields the gate uses."""

    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    body: str
    draft: bool
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str
    user_login: str
    labels: tuple[str, ...]
    from_fork: bool


class Event(BaseModel):
    """A parsed event: ``pull_request`` is set only for ``kind == "pull_request"``."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["pull_request", "push"]
    pull_request: PullRequest | None = None


def event_path(option: str | None, env: Mapping[str, str]) -> Path | None:
    """Return the event file: the ``--event`` option, else ``GITHUB_EVENT_PATH``, else None (no event)."""
    chosen = option or env.get("GITHUB_EVENT_PATH")
    return Path(chosen) if chosen else None


def _pull_request(raw: _RawPullRequest) -> PullRequest:
    base_repo = raw.base.repo.full_name if raw.base.repo else None
    head_repo = raw.head.repo.full_name if raw.head.repo else None
    return PullRequest(
        number=raw.number,
        title=raw.title,
        body=raw.body or "",
        draft=raw.draft,
        base_ref=raw.base.ref,
        base_sha=raw.base.sha,
        head_ref=raw.head.ref,
        head_sha=raw.head.sha,
        user_login=raw.user.login,
        labels=tuple(label.name for label in raw.labels),
        from_fork=head_repo is None or head_repo != base_repo,
    )


def read_event(path: Path) -> Event:
    """Read and validate the event file.

    Args:
        path: the event JSON file.

    Returns:
        A ``pull_request`` event (with the pull request) or a ``push`` event.

    Raises:
        UsageError: the file is unreadable, not JSON, not an object, of an unknown kind or lacks required fields.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise UsageError(f"unreadable event file {path}: {error}") from error
    if not isinstance(data, dict):
        raise UsageError(f"event file {path} is not a JSON object")
    if "pull_request" in data:
        try:
            return Event(
                kind="pull_request", pull_request=_pull_request(_RawPullRequest.model_validate(data["pull_request"]))
            )
        except ValidationError as error:
            raise UsageError(f"invalid pull_request in event file {path}: {error}") from error
    if "ref" in data and "after" in data:
        return Event(kind="push")
    raise UsageError(f"event file {path} is neither a pull_request nor a push event")
