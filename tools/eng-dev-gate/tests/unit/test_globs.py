"""Tests of glob matching (spec 4.5 step 6: PurePosixPath.full_match semantics)."""

from __future__ import annotations

import pytest
from eng_dev_gate.globs import matches, matches_any
from eng_dev_gate.results import UsageError
from hypothesis import given, settings
from hypothesis import strategies as st


def test_full_match_semantics() -> None:
    """* does not cross /, ** spans any number of directories (also none), case-sensitive, whole path must match."""
    assert matches("src/a.py", "src/*.py")
    assert not matches("src/sub/a.py", "src/*.py")
    assert matches("src/sub/deep/a.py", "src/**/a.py")
    assert matches("src/a.py", "src/**/a.py")
    assert matches("tests/unit/test_x.py", "tests/**")
    assert not matches("src/a.py", "src")
    assert not matches("xsrc/a.py", "src/*.py")
    assert not matches("src/A.py", "src/a.py")
    assert not matches("SRC/a.py", "src/*.py")
    assert matches("a/b.py", "a/b.py")


def test_matches_any() -> None:
    """Any pattern may match; an empty list matches nothing."""
    assert matches_any("a/b.py", ["x", "a/*.py"])
    assert not matches_any("a/b.py", [])


def test_empty_pattern_is_usage_error() -> None:
    """An empty glob is a configuration error (exit 2), not a silent non-match."""
    with pytest.raises(UsageError):
        matches("a", "")


@settings(derandomize=True, max_examples=100)
@given(st.lists(st.text(alphabet="abcXYZ012_.-", min_size=1, max_size=6), min_size=1, max_size=4))
def test_literal_path_matches_itself_and_double_star_prefix(parts: list[str]) -> None:
    """Property: a path without special characters matches itself and '**/<last>' (dot-only parts excluded)."""
    parts = [p for p in parts if p.strip(".") != ""]
    if not parts:
        return
    path = "/".join(parts)
    assert matches(path, path)
    assert matches(path, "**/" + parts[-1])
