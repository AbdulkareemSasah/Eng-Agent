"""Unit tests of the result reading and the interpreter choice of ``test-first`` part 2 (spec 4.7 step 4.3)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from eng_dev_gate.checks.test_first_run import RunFaultError, interpreter, outcomes

JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">
<testcase classname="tests.test_a" name="test_one"><failure message="x">boom</failure></testcase>
<testcase classname="tests.test_a.TestX" name="test_m" />
<testcase classname="tests.test_a" name="test_p[1]" />
<testcase classname="tests.test_a" name="test_p[2]"><failure message="x" /></testcase>
<testcase classname="tests.test_a" name="test_s"><skipped type="pytest.skip" message="" /></testcase>
<testcase classname="tests.test_a" name="test_e"><error message="setup" /></testcase>
<testcase classname="" name="tests.test_b"><error message="collection failure">x</error></testcase>
</testsuite></testsuites>"""


def _read(tmp_path: Path, *tests: str) -> dict[str, set[str]]:
    report = tmp_path / "junit.xml"
    report.write_text(JUNIT, encoding="utf-8")
    return outcomes(report, tests)


def test_outcomes_by_test(tmp_path: Path) -> None:
    """Failures and errors are `failed`, skips and xfails `skipped`; parametrized cases are all kept."""
    found = _read(
        tmp_path,
        "tests/test_a.py::test_one",
        "tests/test_a.py::TestX::test_m",
        "tests/test_a.py::test_p",
        "tests/test_a.py::test_s",
        "tests/test_a.py::test_e",
    )
    assert found == {
        "tests/test_a.py::test_one": {"failed"},
        "tests/test_a.py::TestX::test_m": {"passed"},
        "tests/test_a.py::test_p": {"passed", "failed"},
        "tests/test_a.py::test_s": {"skipped"},
        "tests/test_a.py::test_e": {"failed"},
    }


def test_collection_error_fails_every_test_of_the_module(tmp_path: Path) -> None:
    """A collection error is reported under the module name, with no class name: it fails each of its tests."""
    found = _read(tmp_path, "tests/test_b.py::test_x", "tests/test_b.py::TestY::test_z")
    assert found == {"tests/test_b.py::test_x": {"failed"}, "tests/test_b.py::TestY::test_z": {"failed"}}


def test_missing_result_is_tf009(tmp_path: Path) -> None:
    """A test without a result, a missing report and an unreadable report are TF009 (exit 3)."""
    with pytest.raises(RunFaultError, match="TF009"):
        _read(tmp_path, "tests/test_a.py::test_unknown")
    with pytest.raises(RunFaultError, match="TF009"):
        outcomes(tmp_path / "absent.xml", ["tests/test_a.py::test_one"])
    broken = tmp_path / "broken.xml"
    broken.write_text("<testsuites>", encoding="utf-8")
    with pytest.raises(RunFaultError, match="TF009"):
        outcomes(broken, ["tests/test_a.py::test_one"])
    assert RunFaultError("TF009", "x").exit_code == 3


def test_interpreter(tmp_path: Path) -> None:
    """A head run uses the interpreter of the gate; a judged run the environment built from the judged tree."""
    assert interpreter(tmp_path, judged=False) == [sys.executable]
    judged = interpreter(tmp_path, judged=True)
    assert judged[:2] == ["uv", "run"]
    assert judged[judged.index("--project") + 1] == str(tmp_path)
    assert {"--locked", "--all-packages"} <= set(judged)
    assert judged[-1] == "python"
