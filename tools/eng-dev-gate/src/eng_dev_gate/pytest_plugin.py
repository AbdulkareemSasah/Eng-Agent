"""The gate's pytest plugin, loaded with ``-p eng_dev_gate.pytest_plugin`` (spec 4.12).

It loads the Hypothesis profile ``ci`` with ``derandomize=True`` (process/11 section 3) and fails the session when
any test is deselected (CV003, process/05 section 3), whatever way the deselection was made.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

DESELECTED_EXIT_CODE = 10  # pytest uses 0 to 5 itself; the tests step maps this value to CV003
_DESELECTED = pytest.StashKey[int]()


def _count(config: pytest.Config) -> int:
    return config.stash.get(_DESELECTED, 0)


def pytest_configure(config: pytest.Config) -> None:
    """Load the Hypothesis ``ci`` profile when Hypothesis is installed (it is optional for a package)."""
    config.stash[_DESELECTED] = 0
    try:
        from hypothesis import settings
    except ImportError:  # Hypothesis is a development dependency of some packages only
        return
    settings.register_profile("ci", derandomize=True)
    settings.load_profile("ci")


@pytest.hookimpl(wrapper=True)
def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> Generator[None, Any, Any]:  # Any: the wrapper protocol passes the hook result through
    """Count items that disappear from the list during modification, whoever removes them."""
    before = len(items)
    result = yield
    config.stash[_DESELECTED] = _count(config) + max(0, before - len(items))
    return result


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Replace the exit status by ``DESELECTED_EXIT_CODE`` when a test was deselected."""
    if _count(session.config):
        session.exitstatus = DESELECTED_EXIT_CODE


def pytest_terminal_summary(terminalreporter: Any, config: pytest.Config) -> None:  # Any: pytest's TerminalReporter
    """Say why the session failed."""
    if count := _count(config):
        terminalreporter.write_line(f"CV003: {count} test(s) deselected; the gate runs every test", red=True)
