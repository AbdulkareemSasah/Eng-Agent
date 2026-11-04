"""Unit tests of the CODEOWNERS matcher (spec 4.5 step 9: the gitignore subset ``*``, ``**``, leading and trailing ``/``)."""

from __future__ import annotations

import pytest
from eng_dev_gate.checks.codeowners import parse_patterns, protected_paths
from eng_dev_gate.results import UsageError


def test_parse_patterns_skips_comments_and_owners() -> None:
    """Blank lines, comment lines and owners are dropped; the first token of a line is the pattern."""
    text = "# header\n\n/a/ @o1 @o2\n  **/b.md  @o  # inline comment\n#/c/ @o\nd\n"
    assert parse_patterns(text) == ["/a/", "**/b.md", "d"]


@pytest.mark.parametrize("pattern", ["[ab].py", "a?.py", "!a.py", "a\\ b"])
def test_parse_patterns_rejects_syntax_outside_the_subset(pattern: str) -> None:
    """A pattern outside the subset is a usage error, never a silent under-match."""
    with pytest.raises(UsageError, match="subset"):
        parse_patterns(f"{pattern} @o\n")


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("/.github/", ".github/CODEOWNERS", True),
        ("/.github/", "sub/.github/x", False),
        ("/pyproject.toml", "pyproject.toml", True),
        ("/pyproject.toml", "pkg/pyproject.toml", False),
        ("**/pyproject.toml", "pyproject.toml", True),
        ("**/pyproject.toml", "a/b/pyproject.toml", True),
        ("**/checks/", "a/checks/x.py", True),
        ("**/checks/", "checks/x.py", True),
        ("**/checks/", "a/nochecks/x.py", False),
        ("*.md", "a/b/c.md", True),
        ("*.md", "c.mdx", False),
        ("docs/", "a/docs/x.md", True),
        ("docs/x.md", "a/docs/x.md", False),
        ("docs/x.md", "docs/x.md", True),
        ("/a/*.py", "a/x.py", True),
        ("/a/*.py", "a/b/x.py", False),
        ("/a/**/x.py", "a/b/c/x.py", True),
        ("/a/**/x.py", "a/x.py", True),
        ("/tools/eng-dev-gate/", "tools/eng-dev-gate/src/a.py", True),
        ("/tools/eng-dev-gate/", "tools/eng-dev-gate2/src/a.py", False),
    ],
)
def test_pattern_semantics(pattern: str, path: str, expected: bool) -> None:
    """A leading ``/`` or an inner slash anchors the pattern; otherwise it matches at any depth; a match covers the subtree."""
    assert protected_paths([path], [pattern]) == ([path] if expected else [])


def test_protected_paths_keeps_order_and_unique() -> None:
    """The result keeps the order of the changed paths and lists each once."""
    assert protected_paths(["b/x", "a/x", "b/x", "c/y"], ["b/", "a/"]) == ["b/x", "a/x"]
    assert protected_paths(["a"], []) == []
