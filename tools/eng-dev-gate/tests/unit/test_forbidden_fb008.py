"""FB008 (spec 4.8, AC36): pytest hooks and options that deselect tests, in ``tests/`` and ``conftest.py``."""

from __future__ import annotations

import pytest
from support.forbidden import lines
from support.forbidden_b import expected_lines, scan_b

SOURCE = """\
import pytest

collect_ignore = ["test_x.py"]  # <-
collect_ignore_glob = ["gen_*"]  # <-
collect_ignore += ["more.py"]  # <-
conftest.collect_ignore = []  # <-


def pytest_collection_modifyitems(config, items):  # <-
    config.hook.pytest_deselected(items=items)  # <-


async def pytest_ignore_collect(collection_path):  # <-
    return True


def pytest_deselected(items):  # <-
    return None


def helper(request):
    request.config.hook.pytest_deselected(items=[])  # <-
    request.config.hook.pytest_runtest_setup(item=None)
    collect_ignore_note = "collect_ignore"
    ignore = collect_ignore_note
    return ignore


def pytest_collection_finish(session):
    return None


def pytest_configure(config):
    return None
"""


@pytest.mark.parametrize("local", ["tests/test_x.py", "tests/unit/conftest.py", "conftest.py"])
def test_collection_hooks(local: str) -> None:
    findings = scan_b(SOURCE, local)
    assert lines(findings, "FB008") == expected_lines(SOURCE)
    assert {f.code for f in findings} == {"FB008"}
    assert len(findings) == len(expected_lines(SOURCE))
