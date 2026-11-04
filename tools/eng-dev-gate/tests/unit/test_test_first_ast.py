"""Unit tests of the test-function listing of ``test-first`` (spec 4.7 step 4.2)."""

from __future__ import annotations

import pytest
from eng_dev_gate.checks.test_first import list_test_functions

SOURCE = """
import pytest

def test_top() -> None:
    assert 1

async def test_async() -> None:
    assert 2

def helper() -> None: ...

class TestGroup:
    def test_a(self) -> None: ...
    def other(self) -> None: ...
    class TestNested:
        def test_deep(self) -> None: ...

class Helper:
    def test_not_collected(self) -> None: ...
"""


def test_lists_top_level_and_test_class_functions() -> None:
    """Functions named ``test*`` at top level or in ``Test*`` classes are listed by qualified name."""
    assert sorted(list_test_functions(SOURCE)) == ["TestGroup::test_a", "test_async", "test_top"]


def test_dump_ignores_position_and_comments_but_not_code() -> None:
    """Moving a test or adding comments keeps its dump; changing its body or signature changes it."""
    first = list_test_functions("def test_x() -> None:\n    assert 1\n")["test_x"]
    moved = list_test_functions("# c\n\n\ndef test_x() -> None:\n    assert 1  # note\n")["test_x"]
    body = list_test_functions("def test_x() -> None:\n    assert 2\n")["test_x"]
    decorated = list_test_functions("@pytest.mark.slow\ndef test_x() -> None:\n    assert 1\n")["test_x"]
    assert first == moved
    assert len({first, body, decorated}) == 3


@pytest.mark.parametrize("source", ["def test_x(:\n", "def test_x():\n\x00"])
def test_unparseable_source_raises(source: str) -> None:
    """A source that does not parse raises ``ValueError`` or ``SyntaxError`` (a subclass of ``Exception``)."""
    with pytest.raises((SyntaxError, ValueError)):
        list_test_functions(source)
