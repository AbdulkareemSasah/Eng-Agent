"""Read-only log-worktree validation (plan 0015 T3b, spec AC13 and §4.7)."""

import os
from importlib import import_module
from pathlib import Path

import pytest
from helpers.tasklog_git import INTEGRATION_BRANCH, git, make_log_worktree


def _main_checkout_state(repo: Path) -> tuple[str, str, bytes, str]:
    index = Path(git(repo, "rev-parse", "--git-path", "index").strip())
    return (
        git(repo, "rev-parse", "HEAD"),
        git(repo, "symbolic-ref", "HEAD"),
        (repo / index).read_bytes(),
        git(repo, "--no-optional-locks", "status", "--porcelain"),
    )


@pytest.mark.parametrize(
    ("case", "rule"),
    [
        pytest.param("outside_repository", "outside_repository", id="outside_repository"),
        pytest.param("under_runs", "under_runs", id="under_runs"),
        pytest.param("main_checkout", "main_checkout", id="main_checkout"),
        pytest.param("foreign_repository", "not_a_worktree", id="foreign_repository"),
        pytest.param("plain_directory", "not_a_worktree", id="plain_directory"),
        pytest.param("full_checkout", "not_sparse", id="full_checkout"),
        pytest.param("extra_sparse_path", "not_sparse", id="extra_sparse_path"),
        pytest.param("detached_head", "detached_head", id="detached_head"),
        pytest.param("wrong_branch", "wrong_branch", id="wrong_branch"),
        pytest.param("has_upstream", "has_upstream", id="has_upstream"),
        pytest.param("unrelated_history", "no_merge_base", id="unrelated_history"),
        pytest.param("valid", None, id="valid"),
        pytest.param("remote_advanced", None, id="remote_advanced"),
    ],
)
def test_worktree_refusals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, rule: str | None) -> None:
    """Enforce AC13 and preserve the owner checkout on both success and refusal (§4.7)."""
    for name in os.environ.copy():
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-01-01T00:00:00Z")
    repo, worktree = make_log_worktree(tmp_path, case)
    source = repo / "src" / "example.txt"
    source.write_text("Owner's staged changes\n", encoding="utf-8")
    git(repo, "add", "--", "src/example.txt")
    source.write_text("Owner's later unstaged changes\n", encoding="utf-8")
    before = _main_checkout_state(repo)

    # Import during the test so pytest can collect every case before the feature exists.
    module_name = "eng_harness.tasklog._worktree"
    try:
        validation = import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise
        pytest.fail(f"Missing task-log worktree validation module: {module_name}", pytrace=False)

    try:
        if rule is None:
            assert validation.check_log_worktree(repo, worktree, INTEGRATION_BRANCH) is None
        else:
            with pytest.raises(validation.WorktreeRefusedError) as refused:
                validation.check_log_worktree(repo, worktree, INTEGRATION_BRANCH)
            assert refused.value.rule == rule
    finally:
        assert _main_checkout_state(repo) == before
