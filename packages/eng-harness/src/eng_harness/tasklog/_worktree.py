"""Read-only validation of the task-log worktree (spec 0015 AC13, §4.7).

Purpose: `check_log_worktree` refuses a candidate worktree with `WorktreeRefused` unless it is the sparse
`tasklog/` plus `.gate/` checkout of this repository on the local branch `eng-tasklog` with a shared ancestor with
the integration branch; every git invocation is read-only, so the owner's checkout, index and HEAD are never changed.
Errors: `WorktreeRefused` carries the failed rule in `.rule` (`outside_repository`, `under_runs`, `main_checkout`,
`not_a_worktree`, `not_sparse`, `detached_head`, `wrong_branch`, `has_upstream`, `no_merge_base`).
"""

import subprocess
from pathlib import Path

__all__ = ["ALLOWED_WORKTREE_ENTRIES", "LOG_BRANCH", "LOG_REF", "WorktreeRefused", "check_log_worktree"]

LOG_BRANCH = "eng-tasklog"
"""The local branch the log worktree must have checked out (spec 0015 AC13)."""
LOG_REF = f"refs/heads/{LOG_BRANCH}"
"""The full ref of `LOG_BRANCH`, the only HEAD the log worktree may have (spec 0015 AC13)."""
ALLOWED_WORKTREE_ENTRIES = frozenset({"tasklog", ".gate"})
"""The only top-level entries a sparse log worktree may check out (spec 0015 AC13)."""

_RUNS_DIR = "runs"
"""The folder the log worktree must stay outside of (spec 0015 AC13, §4.6)."""
_GIT_NAME = ".git"
"""The worktree metadata entry, skipped when listing checked-out top-level entries."""


class WorktreeRefused(Exception):  # noqa: N818  # B-626: refusal name fixed by the T3b tests (lead decision)
    """A refused log worktree: `.rule` names the failed check (spec 0015 AC13)."""

    def __init__(self, rule: str) -> None:
        super().__init__(f"log worktree refused: {rule}")
        self.rule = rule


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one read-only git command in `path` without touching the checkout, index or HEAD."""
    return subprocess.run(  # noqa: S603  # B-626: fixed git name, read-only subcommands, no shell
        ["git", "-C", str(path), *args],  # noqa: S607  # B-626: git on PATH, fixed read-only argv
        capture_output=True,
        text=True,
        check=False,
    )


def check_log_worktree(repo_root: Path, worktree: Path, integration_branch: str) -> None:
    """Refuse `worktree` unless it is the log worktree of `repo_root` (spec 0015 AC13, §4.7).

    The rules run in order and the first failure raises `WorktreeRefused`: the worktree must resolve inside the
    repository but outside `runs/`, must not be the main checkout, must be a working tree of the same repository,
    must be sparse with only `tasklog` and `.gate` checked out, must have HEAD on `eng-tasklog` with no upstream,
    and `eng-tasklog` must share an ancestor with `origin/<integration_branch>`.
    """
    root = repo_root.resolve()
    candidate = worktree.resolve()
    if not candidate.is_relative_to(root):
        raise WorktreeRefused("outside_repository")
    if candidate.is_relative_to(root / _RUNS_DIR):
        raise WorktreeRefused("under_runs")
    if candidate == root:
        raise WorktreeRefused("main_checkout")
    toplevel = _git(candidate, "rev-parse", "--show-toplevel")
    if toplevel.returncode:
        raise WorktreeRefused("not_a_worktree")
    if Path(toplevel.stdout.strip()).resolve() != candidate:
        raise WorktreeRefused("not_a_worktree")
    worktree_common = _git(candidate, "rev-parse", "--path-format=absolute", "--git-common-dir")
    root_common = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if worktree_common.returncode or root_common.returncode:
        raise WorktreeRefused("not_a_worktree")
    if worktree_common.stdout.strip() != root_common.stdout.strip():
        raise WorktreeRefused("not_a_worktree")
    sparse = _git(candidate, "config", "--bool", "--get", "core.sparseCheckout")
    if sparse.returncode or sparse.stdout.strip() != "true":
        raise WorktreeRefused("not_sparse")
    entries = frozenset(entry.name for entry in candidate.iterdir() if entry.name != _GIT_NAME)
    if not entries.issubset(ALLOWED_WORKTREE_ENTRIES):
        raise WorktreeRefused("not_sparse")
    head = _git(candidate, "symbolic-ref", "-q", "HEAD")
    if head.returncode:
        raise WorktreeRefused("detached_head")
    if head.stdout.strip() != LOG_REF:
        raise WorktreeRefused("wrong_branch")
    upstream = _git(candidate, "rev-parse", "--abbrev-ref", f"{LOG_BRANCH}@{{upstream}}")
    if not upstream.returncode:
        raise WorktreeRefused("has_upstream")
    base = _git(candidate, "merge-base", LOG_BRANCH, f"origin/{integration_branch}")
    if base.returncode:
        raise WorktreeRefused("no_merge_base")
