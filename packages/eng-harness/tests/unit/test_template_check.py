"""check_template: a report with every error and every warning (plan 0004 T4; spec 0004 AC13).

All templates are synthetic: every value is a placeholder, not an engineering value.
"""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from eng_harness.templates import TemplateIssue, TemplateRepository, check_template

CITE = "Synthetic placeholder, not an engineering value"
NAME = "synthetic-check-0.1.0.template.yaml"


def _file(tmp_path: Path, data: Any, name: str = NAME) -> Path:
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def _good() -> dict[str, Any]:
    return {
        "schema": "eng-template/1",
        "meta": {"name": "synthetic-check", "version": "0.1.0", "synthetic": True},
        "limits": {"ratio_limit_ratio": {"value": 0.5, "unit": "1", "citation": CITE}},
        "ask_each_run": [{"path": "analysis.stories", "label": "Stories", "kind": "count"}],
    }


def _pairs(issues: Iterable[TemplateIssue]) -> set[tuple[str, str]]:
    return {(issue.reason, issue.path) for issue in issues}


def test_report_lists_all_errors(tmp_path: Path) -> None:
    data = _good()
    data["extra_section"] = {}
    data["limits"]["no_cite_mm"] = {"value": 1, "unit": "mm", "citation": ""}
    data["limits"]["wrong_unit_MPa"] = {"value": 1, "unit": "kPa", "citation": CITE}
    data["limits"]["nested"] = {"bad key": {"value": 1, "unit": None, "citation": CITE}, "scalar": 3}
    data["materials"] = {"steel": {"fy_MPa": {"value": 1, "unit": "MPa", "citation": CITE, "colour": "red"}}}
    data["ask_each_run"].append({"path": "analysis.mode", "label": "Mode", "kind": "choice"})
    report = check_template(_file(tmp_path, data))
    assert not report.ok
    assert _pairs(report.errors) == {
        ("unknown_key", "extra_section"),
        ("citation_missing", "limits.no_cite_mm"),
        ("unit_mismatch", "limits.wrong_unit_MPa"),
        ("unknown_key", "limits.nested.bad key"),
        ("value_invalid", "limits.nested.scalar"),
        ("unknown_key", "materials.steel.fy_MPa.colour"),
        ("value_invalid", "ask_each_run[1]"),
    }
    assert report.file == NAME


def test_ask_collision_is_reported_when_the_pieces_are_valid(tmp_path: Path) -> None:
    data = _good()
    data["ask_each_run"].append({"path": "limits.ratio_limit_ratio", "label": "Ratio", "kind": "count"})
    report = check_template(_file(tmp_path, data))
    assert _pairs(report.errors) == {("ask_has_value", "limits.ratio_limit_ratio")}


def test_malformed_file_raises_nothing(tmp_path: Path) -> None:
    report = check_template(_file(tmp_path, "a: 1\na: 2\n"))
    assert _pairs(report.errors) == {("yaml_invalid", "")}
    missing = check_template(tmp_path / "absent-0.1.0.template.yaml")
    assert _pairs(missing.errors) == {("not_found", "")}
    listed = check_template(_file(tmp_path, "[1, 2]", "synthetic-list-0.1.0.template.yaml"))
    assert _pairs(listed.errors) == {("value_invalid", "")}
    mismatch = check_template(_file(tmp_path, _good(), "other-0.1.0.template.yaml"))
    assert _pairs(mismatch.errors) == {("meta_invalid", "meta.name")}


def test_valid_file_and_warnings(tmp_path: Path) -> None:
    path = _file(tmp_path, _good())
    assert check_template(path).ok
    assert check_template(path).warnings == ()  # no workflow knowledge, nothing to warn about
    report = check_template(path, known_paths={"limits.ratio_limit_ratio"})
    assert report.ok
    assert _pairs(report.warnings) == {("unknown_path", "analysis.stories")}
    assert _pairs(check_template(path, known_paths=set()).warnings) == {
        ("unknown_path", "limits.ratio_limit_ratio"),
        ("unknown_path", "analysis.stories"),
    }


def test_extends_checked_against_a_repository(tmp_path: Path) -> None:
    data = _good()
    data["meta"]["extends"] = "synthetic-parent@0.1.0"
    path = _file(tmp_path, data)
    source = TemplateRepository(tmp_path / "shipped", tmp_path / "user", allow_synthetic=True)
    assert _pairs(check_template(path, source=source).errors) == {("extends_invalid", "meta.extends")}
    assert check_template(path).ok  # without a source the parent is not looked up


def test_report_lists_every_ask_error_next_to_an_entry_error(tmp_path: Path) -> None:
    data = _good()
    data["limits"]["no_cite_mm"] = {"value": 1, "unit": "mm", "citation": ""}
    data["ask_each_run"] += [
        {"path": "limits.ratio_limit_ratio", "label": "Ratio", "kind": "count"},
        {"path": "analysis.stories", "label": "Again", "kind": "count"},
    ]
    report = check_template(_file(tmp_path, data))
    assert _pairs(report.errors) == {
        ("citation_missing", "limits.no_cite_mm"),
        ("ask_has_value", "limits.ratio_limit_ratio"),
        ("ask_has_value", "analysis.stories"),
    }


def test_extends_is_checked_next_to_other_errors(tmp_path: Path) -> None:
    data = _good()
    data["meta"]["extends"] = "synthetic-parent@0.1.0"
    data["limits"]["no_cite_mm"] = {"value": 1, "unit": "mm", "citation": ""}
    source = TemplateRepository(tmp_path / "shipped", tmp_path / "user", allow_synthetic=True)
    report = check_template(_file(tmp_path, data), source=source)
    assert _pairs(report.errors) == {("citation_missing", "limits.no_cite_mm"), ("extends_invalid", "meta.extends")}


def test_bad_group_key_is_reported_once(tmp_path: Path) -> None:
    data = _good()
    data["limits"]["grp"] = {"bad-key": {"x_ratio": {"value": 1, "unit": "1", "citation": CITE}}}
    report = check_template(_file(tmp_path, data))
    assert [(i.reason, i.path) for i in report.errors].count(("unknown_key", "limits.grp.bad-key")) == 1
