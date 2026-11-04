"""Fixture: temporary git repositories with fixed dates and a local identity (spec section 9).

The handle runs ``git`` through a subprocess with a clean environment (no global or system configuration) and
runs the gate in-process through ``cli.main``. It never touches this repository's history.
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from eng_dev_gate.cli import Handler, main

FIXED_DATE = "2026-01-01T00:00:00+00:00"


@dataclass(frozen=True)
class RunResult:
    """Outcome of an in-process gate run."""

    code: int
    out: str
    err: str


class Repo:
    """A temporary git repository with deterministic commits."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(root),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_DATE": FIXED_DATE,
            "GIT_COMMITTER_DATE": FIXED_DATE,
        }
        root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str) -> str:
        """Run ``git`` in the repository and return stdout; raises on a non-zero exit."""
        done = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=self.root,
            env=self._env,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        return done.stdout

    def write(self, files: Mapping[str, str]) -> None:
        """Write text files (POSIX relative paths), creating folders."""
        for name, text in files.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, files: Mapping[str, str], message: str = "chore: fixture") -> str:
        """Write ``files``, commit everything and return the commit SHA."""
        self.write(files)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def rename(self, old: str, new: str, message: str = "chore: rename") -> str:
        """Move a tracked file with ``git mv``, commit and return the commit SHA."""
        (self.root / new).parent.mkdir(parents=True, exist_ok=True)
        self.git("mv", old, new)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def branch(self, name: str) -> None:
        """Create and check out a branch at the current commit."""
        self.git("checkout", "-q", "-b", name)

    def run(self, argv: Sequence[str], handlers: Mapping[str, Handler] | None = None) -> RunResult:
        """Run ``cli.main`` in-process with ``--root`` set to the repository."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--root", str(self.root), *argv], handlers)
        return RunResult(code, out.getvalue(), err.getvalue())


def make_repo(root: Path) -> Repo:
    """Create an empty repository in ``root`` (created if missing, e.g. below pytest's ``tmp_path``)."""
    return Repo(root)
