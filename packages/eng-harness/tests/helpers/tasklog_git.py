"""Temporary Git repositories and worktrees for task-log tests."""

import shutil
import subprocess
from pathlib import Path

INTEGRATION_BRANCH = "build/v1"
LOG_BRANCH = "eng-tasklog"


def git(directory: Path, *args: str) -> str:
    """Run Git in a fixture directory and return stdout."""
    executable = shutil.which("git")
    assert executable is not None, "Git is required for task-log tests"
    result = subprocess.run(  # noqa: S603  # B-626: resolved executable, fixture arguments, no shell
        [executable, *args],
        cwd=directory,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, f"git {args!r} in {directory}: {result.stderr}"
    return result.stdout


def make_repository(root: Path, branch: str = INTEGRATION_BRANCH) -> Path:
    """Create a checkout whose tracked files distinguish sparse and full worktrees."""
    root.mkdir(parents=True)
    git(root, "init", "--initial-branch", branch)
    git(root, "config", "--local", "user.name", "Task Log Fixture")
    git(root, "config", "--local", "user.email", "tasklog-fixture@example.invalid")
    for relative_path, content in {
        ".gitignore": "/.eng/\n/runs/\n",
        ".gate/README.md": "Gate fixture\n",
        "tasklog/README.md": "Task log fixture\n",
        "src/example.txt": "Source fixture\n",
    }.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "-m", "Seed worktree fixture")
    return root


def add_log_worktree(repo: Path, path: Path, *, sparse: bool = True) -> Path:
    """Create the local log branch and a linked checkout at the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "-b", LOG_BRANCH, str(path))
    if sparse:
        git(path, "sparse-checkout", "set", "--no-cone", "/tasklog/", "/.gate/")
    return path


def make_log_worktree(tmp_path: Path, case: str) -> tuple[Path, Path]:
    """Build an owner checkout with a bare origin and the candidate for one validation case."""
    repo = make_repository(tmp_path / "repo")
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    git(repo, "remote", "add", "origin", str(origin))
    integration_ref = f"refs/heads/{INTEGRATION_BRANCH}"
    source = INTEGRATION_BRANCH
    if case == "unrelated_history":
        source = git(repo, "commit-tree", "HEAD^{tree}", "-m", "Unrelated integration history").strip()
    git(repo, "push", "origin", f"{source}:{integration_ref}")

    suggested = repo / ".eng" / "tasklog" / "worktree"
    match case:
        case "main_checkout":
            return repo, repo
        case "foreign_repository":
            foreign = make_repository(suggested, LOG_BRANCH)
            git(foreign, "sparse-checkout", "set", "--no-cone", "/tasklog/", "/.gate/")
            return repo, foreign
        case "plain_directory":
            suggested.mkdir(parents=True)
            return repo, suggested
        case "outside_repository":
            return repo, add_log_worktree(repo, tmp_path / "worktree")
        case "under_runs":
            return repo, add_log_worktree(repo, repo / "runs" / "worktree")

    worktree = add_log_worktree(repo, suggested, sparse=case != "full_checkout")
    match case:
        case "extra_sparse_path":
            git(worktree, "sparse-checkout", "add", "/src/")
        case "detached_head":
            git(worktree, "switch", "--detach")
        case "wrong_branch":
            git(worktree, "switch", "-c", "another-branch")
        case "has_upstream":
            git(worktree, "branch", "--set-upstream-to", f"origin/{INTEGRATION_BRANCH}")
        case "remote_advanced":
            git(worktree, "commit", "--allow-empty", "-m", "Local log commit")
            git(repo, "commit", "--allow-empty", "-m", "Advance integration branch")
            git(repo, "push", "origin", f"HEAD:{integration_ref}")
    return repo, worktree
