"""The ``Git`` port and its subprocess adapter (spec 4.1).

Runs ``git -c core.quotepath=off`` without a shell, with NUL-separated output, and maps every failure to a typed
error (exit 3). It never prints and never writes to the repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from eng_dev_gate.results import EnvironmentFaultError

GIT_TIMEOUT_SECONDS = 120  # generous bound for a local git call; a hung git is an environment fault, not a rule result


class GitError(EnvironmentFaultError):
    """Git is missing, failed, timed out or returned unparseable output (exit 3)."""


class PathNotFoundError(GitError):
    """A path does not exist at the requested ref (for example a plan missing from the gate branch)."""


class Change(BaseModel):
    """A changed path from ``--name-status``: ``status`` is the letter (A, M, D, R, C, T); ``old_path`` for R and C."""

    model_config = ConfigDict(frozen=True)

    status: str
    path: str
    old_path: str | None = None

    @property
    def paths(self) -> tuple[str, ...]:
        """All paths the change touches: a rename or copy contributes both (spec 4.5 step 6)."""
        return (self.old_path, self.path) if self.old_path is not None else (self.path,)


class NumstatEntry(BaseModel):
    """A path from ``--numstat``; binary files have ``binary`` set and zero counts."""

    model_config = ConfigDict(frozen=True)

    path: str
    old_path: str | None = None
    added: int = 0
    deleted: int = 0
    binary: bool = False


class Git(Protocol):
    """Port to git; tests may provide a fake."""

    def name_status(self, base: str, head: str) -> list[Change]:
        """Changed paths between two commits, renames detected."""
        ...

    def numstat(self, base: str, head: str) -> list[NumstatEntry]:
        """Added and deleted line counts per path between two commits."""
        ...

    def show(self, ref: str, path: str) -> str:
        """Content of ``path`` at ``ref``."""
        ...

    def merge_base(self, a: str, b: str) -> str:
        """Best common ancestor commit of two refs."""
        ...

    def rev_parse(self, ref: str) -> str:
        """Full commit id of ``ref``."""
        ...


class SubprocessGit:
    """:class:`Git` over the ``git`` executable, run in ``cwd``."""

    def __init__(self, cwd: Path, executable: str = "git") -> None:
        self._cwd = cwd
        self._executable = executable

    def _run(self, *args: str) -> str:
        command = [self._executable, "-c", "core.quotepath=off", *args]
        try:
            done = subprocess.run(  # noqa: S603  # B-057: no shell; the arguments are a list
                command, cwd=self._cwd, capture_output=True, timeout=GIT_TIMEOUT_SECONDS, check=False
            )
            if done.returncode != 0:
                detail = done.stderr.decode("utf-8", errors="replace").strip()
                raise GitError(f"git {args[0]} failed with exit {done.returncode}: {detail}")
            return done.stdout.decode("utf-8")
        except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError) as error:
            raise GitError(f"git {args[0]} could not run: {error}") from error

    def name_status(self, base: str, head: str) -> list[Change]:
        """Return ``git diff --name-status -z -M base head`` as changes.

        Raises:
            GitError: git failed or its output is malformed.
        """
        tokens = self._run("diff", "--name-status", "-z", "-M", base, head).split("\0")
        changes: list[Change] = []
        i = 0
        while i < len(tokens) and tokens[i]:
            status = tokens[i][0]
            width = 3 if status in "RC" else 2
            fields = tokens[i : i + width]
            if len(fields) < width or not all(fields):
                raise GitError("malformed git name-status output")
            changes.append(Change(status=status, path=fields[-1], old_path=fields[1] if width == 3 else None))
            i += width
        return changes

    def numstat(self, base: str, head: str) -> list[NumstatEntry]:
        """Return ``git diff --numstat -z -M base head`` as entries.

        Raises:
            GitError: git failed or its output is malformed.
        """
        tokens = self._run("diff", "--numstat", "-z", "-M", base, head).split("\0")
        entries: list[NumstatEntry] = []
        i = 0
        while i < len(tokens) and tokens[i]:
            counts = tokens[i].split("\t", 2)
            if len(counts) != 3:
                raise GitError("malformed git numstat output")
            added, deleted, path = counts
            old_path = None
            if path == "":  # rename or copy: the old and new paths are the next two tokens
                if i + 2 >= len(tokens):
                    raise GitError("malformed git numstat output")
                old_path, path = tokens[i + 1], tokens[i + 2]
                if not old_path or not path:
                    raise GitError("malformed git numstat output")
                i += 2
            binary = added == "-" and deleted == "-"
            try:
                entries.append(
                    NumstatEntry(
                        path=path,
                        old_path=old_path,
                        added=0 if binary else int(added),
                        deleted=0 if binary else int(deleted),
                        binary=binary,
                    )
                )
            except ValueError as error:
                raise GitError("malformed git numstat counts") from error
            i += 1
        return entries

    def show(self, ref: str, path: str) -> str:
        """Return the content of ``path`` at ``ref``.

        Raises:
            PathNotFoundError: the path does not exist at ``ref``.
            GitError: the ref is invalid or git failed.
        """
        if not self._run("ls-tree", "-z", ref, "--", path):
            raise PathNotFoundError(f"{path} does not exist at {ref}")
        return self._run("show", f"{ref}:{path}")

    def merge_base(self, a: str, b: str) -> str:
        """Return the merge base of ``a`` and ``b``; GitError if there is none."""
        return self._run("merge-base", a, b).strip()

    def rev_parse(self, ref: str) -> str:
        """Return the full commit id of ``ref``; GitError if it does not resolve."""
        return self._run("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").strip()
