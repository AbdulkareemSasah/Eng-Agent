"""The user-level push file reader (plan 0015 T4a; spec 0015 AC26, section 4.6)."""

from pathlib import Path

import pytest

from eng_harness.tasklog._pushconf import PushFileError, read_push_file


def test_push_file_inside_repo_refused(tmp_path: Path) -> None:
    """A push file inside a git working tree is refused (spec 0015 4.6, AC26; ADR-0034 D6)."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)  # the marker of a git working tree's top level
    push_file = repo / "tasklog-push.toml"
    push_file.write_text(
        'push = true\nintegration_branch = "build/v1"\nremote = "https://example.invalid/owner/repo.git"\n',
        encoding="utf-8",
    )
    with pytest.raises(PushFileError):
        read_push_file(push_file)
