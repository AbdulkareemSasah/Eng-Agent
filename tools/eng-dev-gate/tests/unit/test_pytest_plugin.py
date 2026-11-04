"""Tests of the gate's pytest plugin (spec 4.12: Hypothesis profile ``ci``, deselection guard CV003)."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import cast

import pytest
from eng_dev_gate import pytest_plugin
from eng_dev_gate.checks.tests_step import DESELECTED_EXIT_CODE

pytest_plugins = ["pytester"]

FILE = "def test_a() -> None:\n    pass\n\n\ndef test_b() -> None:\n    pass\n"


def _run(pytester: pytest.Pytester, *args: str) -> pytest.RunResult:
    pytester.makepyfile(test_x=FILE)
    return pytester.runpytest_inprocess("-p", "eng_dev_gate.pytest_plugin", *args)


def test_clean_session_is_untouched(pytester: pytest.Pytester) -> None:
    result = _run(pytester)
    assert result.ret == 0
    result.assert_outcomes(passed=2)


def test_keyword_deselection_fails(pytester: pytest.Pytester) -> None:
    result = _run(pytester, "-k", "test_a")
    assert result.ret == DESELECTED_EXIT_CODE
    result.stdout.fnmatch_lines(["*CV003*1 test*deselected*"])


def test_conftest_dropping_items_fails(pytester: pytest.Pytester) -> None:
    """Removing items from the list without the hook is caught too."""
    pytester.makeconftest("def pytest_collection_modifyitems(items):\n    del items[1:]\n")
    result = _run(pytester)
    assert result.ret == DESELECTED_EXIT_CODE
    result.stdout.fnmatch_lines(["*CV003*1 test*"])


def test_hypothesis_profile_ci_is_derandomized(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        test_h="from hypothesis import settings\n\n\ndef test_profile() -> None:\n    assert settings().derandomize\n"
    )
    result = pytester.runpytest_inprocess("-p", "eng_dev_gate.pytest_plugin")
    assert result.ret == 0


def test_configure_without_hypothesis_is_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "hypothesis", None)  # makes ``import hypothesis`` raise ImportError
    config = cast("pytest.Config", SimpleNamespace(stash={}))
    pytest_plugin.pytest_configure(config)
    assert pytest_plugin._count(config) == 0
