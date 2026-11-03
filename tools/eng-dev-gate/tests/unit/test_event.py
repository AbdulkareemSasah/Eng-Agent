"""Tests of the GitHub event file reader (spec 4.5 inputs; exit 2 for an unreadable event file)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eng_dev_gate.event import event_path, read_event
from eng_dev_gate.results import UsageError


def _pr(**overrides: object) -> dict[str, object]:
    pr: dict[str, object] = {
        "number": 7,
        "title": "feat(x): y (B-001)",
        "body": "Plan-Task: p#T1",
        "draft": False,
        "base": {"ref": "build/v1", "sha": "b" * 40, "repo": {"full_name": "o/r"}},
        "head": {"ref": "feat/x", "sha": "a" * 40, "repo": {"full_name": "o/r"}},
        "user": {"login": "agent"},
        "labels": [{"name": "one"}, {"name": "two"}],
    }
    pr.update(overrides)
    return {"pull_request": pr}


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "event.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_pull_request_event(tmp_path: Path) -> None:
    """The documented fields are read; labels become names."""
    event = read_event(_write(tmp_path, _pr()))
    assert event.kind == "pull_request"
    pr = event.pull_request
    assert pr is not None
    assert (pr.number, pr.title, pr.body, pr.draft) == (7, "feat(x): y (B-001)", "Plan-Task: p#T1", False)
    assert (pr.base_ref, pr.base_sha, pr.head_ref, pr.head_sha) == ("build/v1", "b" * 40, "feat/x", "a" * 40)
    assert pr.user_login == "agent"
    assert pr.labels == ("one", "two")
    assert not pr.from_fork


def test_null_body_is_empty_and_fork_is_detected(tmp_path: Path) -> None:
    """A null body reads as empty; a head repository other than the base repository is a fork."""
    head = {"ref": "f", "sha": "a" * 40, "repo": {"full_name": "other/r"}}
    pr = read_event(_write(tmp_path, _pr(body=None, head=head))).pull_request
    assert pr is not None
    assert pr.body == ""
    assert pr.from_fork


def test_deleted_head_repository_counts_as_fork(tmp_path: Path) -> None:
    """A null head repository cannot be proven to be this repository."""
    head = {"ref": "f", "sha": "a" * 40, "repo": None}
    pr = read_event(_write(tmp_path, _pr(head=head))).pull_request
    assert pr is not None
    assert pr.from_fork


def test_push_event(tmp_path: Path) -> None:
    """A push event has no pull request."""
    event = read_event(_write(tmp_path, {"ref": "refs/heads/main", "before": "0" * 40, "after": "1" * 40}))
    assert event.kind == "push"
    assert event.pull_request is None


@pytest.mark.parametrize("content", ["not json", "[]", "{}", '{"pull_request": {"number": 1}}'])
def test_malformed_event_is_usage_error(tmp_path: Path, content: str) -> None:
    """Unreadable or incomplete event files exit 2 (UsageError)."""
    path = tmp_path / "event.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(UsageError):
        read_event(path)


def test_missing_event_file_is_usage_error(tmp_path: Path) -> None:
    """A missing file is an unreadable event file."""
    with pytest.raises(UsageError):
        read_event(tmp_path / "absent.json")


def test_event_path_option_beats_environment() -> None:
    """--event wins over GITHUB_EVENT_PATH; neither gives None (no event, local run)."""
    assert event_path("x.json", {"GITHUB_EVENT_PATH": "y.json"}) == Path("x.json")
    assert event_path(None, {"GITHUB_EVENT_PATH": "y.json"}) == Path("y.json")
    assert event_path(None, {}) is None
