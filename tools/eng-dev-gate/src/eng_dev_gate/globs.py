"""POSIX glob matching on ``PurePosixPath.full_match`` (spec 4.5 step 6).

``*`` does not cross ``/``, ``**`` matches any number of directories, matching is case-sensitive and the whole path
must match.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath

from eng_dev_gate.results import UsageError


def matches(path: str, pattern: str) -> bool:
    """Return whether the POSIX ``path`` (relative to the workspace root) fully matches ``pattern``.

    Raises:
        UsageError: ``pattern`` is empty.
    """
    if not pattern:
        raise UsageError("empty glob pattern")
    return PurePosixPath(path).full_match(pattern)


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    """Return whether ``path`` matches at least one of ``patterns`` (none: False)."""
    return any(matches(path, pattern) for pattern in patterns)
