"""Tests of the Git port on temporary repositories (spec 4.1, 4.5 steps 4, 6, 7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from eng_dev_gate.gitio import Change, GitError, PathNotFoundError, SubprocessGit
from eng_dev_gate.results import EnvironmentFaultError
from support.repo import Repo

BODY = "line one\nline two\nline three\nline four\nline five\n"


def test_name_status_with_rename(repo: Repo) -> None:
    """A rename is reported with old and new path; both count as changed paths (AC10)."""
    base = repo.commit({"a/old.py": BODY, "keep.py": "x\n"})
    repo.rename("a/old.py", "b/new.py")
    repo.write({"added.py": "y\n", "keep.py": "x\nz\n"})
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "more")
    head = repo.git("rev-parse", "HEAD").strip()
    changes = SubprocessGit(repo.root).name_status(base, head)
    by_path = {c.path: c for c in changes}
    renamed = by_path["b/new.py"]
    assert renamed.status == "R"
    assert renamed.old_path == "a/old.py"
    assert set(renamed.paths) == {"a/old.py", "b/new.py"}
    assert by_path["added.py"] == Change(status="A", path="added.py", old_path=None)
    assert by_path["keep.py"].status == "M"
    assert len(changes) == 3


def test_name_status_unicode_path_is_not_quoted(repo: Repo) -> None:
    """core.quotepath=off and NUL separation: non-ASCII names come back verbatim."""
    base = repo.commit({"seed.txt": "s\n"})
    head = repo.commit({"dir/café n.txt": "x\n"})
    assert [c.path for c in SubprocessGit(repo.root).name_status(base, head)] == ["dir/café n.txt"]


def test_numstat_counts_rename_and_binary(repo: Repo) -> None:
    """numstat gives additions and deletions; a pure rename counts zero; binary files have no counts."""
    base = repo.commit({"a.py": BODY, "m.py": "1\n2\n3\n"})
    repo.git("mv", "a.py", "c.py")
    repo.write({"m.py": "1\nTWO\n3\n4\n"})
    (repo.root / "blob.bin").write_bytes(b"\x00\x01\x02")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "change")
    head = repo.git("rev-parse", "HEAD").strip()
    entries = {e.path: e for e in SubprocessGit(repo.root).numstat(base, head)}
    assert (entries["m.py"].added, entries["m.py"].deleted) == (2, 1)
    assert (entries["c.py"].added, entries["c.py"].deleted, entries["c.py"].old_path) == (0, 0, "a.py")
    assert entries["blob.bin"].binary
    assert entries["blob.bin"].added == 0
    assert not entries["m.py"].binary


def test_show_and_missing_path(repo: Repo) -> None:
    """show reads a file at a ref; an absent path is PathNotFoundError, a bad ref is GitError."""
    repo.commit({"docs/p.md": "plan\n"})
    git = SubprocessGit(repo.root)
    assert git.show("HEAD", "docs/p.md") == "plan\n"
    with pytest.raises(PathNotFoundError):
        git.show("HEAD", "docs/absent.md")
    with pytest.raises(GitError):
        git.show("no-such-ref", "docs/p.md")


def test_merge_base_and_rev_parse(repo: Repo) -> None:
    """merge_base of a branch and main is the fork point."""
    fork = repo.commit({"a": "1\n"})
    repo.branch("feat")
    repo.commit({"b": "2\n"})
    repo.git("checkout", "-q", "main")
    repo.commit({"c": "3\n"})
    git = SubprocessGit(repo.root)
    assert git.merge_base("main", "feat") == fork
    assert git.rev_parse("feat^") == fork


def test_failures_are_typed_environment_errors(repo: Repo, tmp_path: Path) -> None:
    """A failing git command is a typed environment error (exit 3); so is a missing git executable."""
    repo.commit({"a": "1\n"})
    assert issubclass(GitError, EnvironmentFaultError)
    with pytest.raises(GitError):
        SubprocessGit(repo.root).rev_parse("nope")
    with pytest.raises(GitError):
        SubprocessGit(tmp_path / "not-a-repo").rev_parse("HEAD")
    with pytest.raises(GitError):
        SubprocessGit(repo.root, executable="git-does-not-exist").rev_parse("HEAD")


@pytest.mark.parametrize(
    ("method", "output"),
    [
        ("name_status", "R100\0only-one-path\0"),
        ("name_status", "M\0"),
        ("numstat", "1\t2"),
        ("numstat", "1\t2\t\0old\0"),
        ("numstat", "x\ty\tfile\0"),
    ],
)
def test_malformed_git_output_is_git_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, method: str, output: str
) -> None:
    """Output that does not follow the documented NUL format is a GitError, never a guess."""
    git = SubprocessGit(tmp_path)
    monkeypatch.setattr(git, "_run", lambda *_args: output)
    with pytest.raises(GitError):
        getattr(git, method)("a", "b")
