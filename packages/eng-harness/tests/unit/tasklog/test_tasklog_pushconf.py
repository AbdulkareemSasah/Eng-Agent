"""The user-level push file reader (plan 0015 T4a; spec 0015 AC26, section 4.6)."""

import shutil
import subprocess
from pathlib import Path

import pytest

from eng_harness.tasklog._pushconf import PushFileError, read_push_file


def test_push_file_inside_repo_refused(tmp_path: Path) -> None:
    """A push file inside a git working tree is refused (spec 0015 4.6, AC26; ADR-0034 D6)."""
    git_exe = shutil.which("git")
    assert git_exe is not None
    repo = tmp_path / "repo"
    repo.mkdir()
    done = subprocess.run(  # noqa: S603  # B-627: fixed subcommand, PATH git, no shell
        [git_exe, "init", str(repo)], capture_output=True, check=False, timeout=60
    )
    assert done.returncode == 0
    push_file = repo / "tasklog-push.toml"
    push_file.write_text(
        'push = true\nintegration_branch = "build/v1"\nremote = "https://example.invalid/owner/repo.git"\n',
        encoding="utf-8",
    )
    with pytest.raises(PushFileError):
        read_push_file(push_file)
