"""CODEOWNERS matcher (spec 4.5 step 9): the gitignore subset ``*``, ``**``, leading ``/`` and trailing ``/``."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from eng_dev_gate.gitio import Git, PathNotFoundError
from eng_dev_gate.globs import matches_any
from eng_dev_gate.results import UsageError

CODEOWNERS_FILES = (".github/CODEOWNERS", "CODEOWNERS")
_OUTSIDE_SUBSET = frozenset("!?[]\\")


def parse_patterns(text: str) -> list[str]:
    """Return the path patterns of a CODEOWNERS file (the first token of each non-comment line).

    Raises:
        UsageError: a pattern uses syntax outside the supported subset; matching it as a literal would under-protect.
    """
    patterns: list[str] = []
    for line in text.splitlines():
        tokens = line.split("#", 1)[0].split()
        if tokens and _OUTSIDE_SUBSET.intersection(tokens[0]):
            raise UsageError(f"CODEOWNERS pattern {tokens[0]!r} uses syntax outside the supported subset")
        patterns.extend(tokens[:1])
    return patterns


def _covers(path: str, pattern: str) -> bool:
    """Whether ``pattern`` covers ``path``: anchored by a leading or inner ``/``, else at any depth; and its subtree."""
    core = pattern.strip("/")
    anchored = pattern.startswith("/") or "/" in pattern.rstrip("/")
    root = core if anchored else f"**/{core}"
    return matches_any(path, (root, f"{root}/**"))


def protected_paths(paths: Iterable[str], patterns: Sequence[str]) -> list[str]:
    """Return the distinct ``paths`` (in order) covered by at least one of ``patterns``."""
    return [p for p in dict.fromkeys(paths) if any(_covers(p, pattern) for pattern in patterns)]


def load_patterns(git: Git, refs: Iterable[str]) -> list[str]:
    """Read the patterns of every CODEOWNERS file at each of ``refs``; raises UsageError, GitError."""
    patterns: list[str] = []
    for ref in refs:
        for name in CODEOWNERS_FILES:
            try:
                patterns += parse_patterns(git.show(ref, name))
            except PathNotFoundError:
                continue
    return patterns
