"""Every rule has a typical and a boundary test (plan 0005 T4; spec 0005 AC12, process/10 section 4)."""

import importlib
from pathlib import Path

from eng_harness.decisions._rules import Rule, RuleRegistry, RuleTestFinding, discover, missing_rule_tests

bearing_only: Rule = importlib.import_module("rules.fixtures.fixture_rules").bearing_only
RULE_TESTS = Path(__file__).resolve().parents[1] / "rules"


def test_every_rule_has_typical_and_boundary_tests() -> None:
    assert missing_rule_tests(discover(), RULE_TESTS) == ()


def test_missing_rule_tests_reports_a_fixture_gap(tmp_path: Path) -> None:
    registry = RuleRegistry([bearing_only])
    expected = "test_fixture_rules.py"
    assert missing_rule_tests(registry, tmp_path) == (
        RuleTestFinding("fixture_point.bearing_only", expected, "test_bearing_only_typical"),
        RuleTestFinding("fixture_point.bearing_only", expected, "test_bearing_only_boundary"),
    )
    (tmp_path / expected).write_text("def test_bearing_only_typical():\n    pass\n", encoding="utf-8")
    assert missing_rule_tests(registry, tmp_path) == (
        RuleTestFinding("fixture_point.bearing_only", expected, "test_bearing_only_boundary"),
    )
    (tmp_path / expected).write_text(
        "def test_bearing_only_typical():\n    pass\n\n"
        "class TestBoundary:\n    def test_bearing_only_boundary(self):\n        pass\n",
        encoding="utf-8",
    )
    assert missing_rule_tests(registry, tmp_path) == ()
