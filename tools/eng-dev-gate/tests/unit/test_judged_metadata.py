"""Tests of the metadata reader that runs inside the judged tree's environment (B-086)."""

from __future__ import annotations

import ast
import json
import runpy
import sys
from pathlib import Path

import pytest
from eng_dev_gate import judged_metadata
from support.dists import add_dist


def test_collect_reads_the_fields_the_license_policy_needs(tmp_path: Path) -> None:
    site = tmp_path / "site"
    add_dist(
        site,
        "Some-Dist",
        "License-Expression: MIT",
        "License: free text",
        "Classifier: License :: OSI Approved :: MIT License",
        "Requires-Dist: other>=1",
    )
    add_dist(site, "bare")
    found = {entry["name"]: entry for entry in judged_metadata.collect([str(site)])}
    assert found["Some-Dist"] == {
        "name": "Some-Dist",
        "expression": "MIT",
        "license": "free text",
        "classifiers": ["License :: OSI Approved :: MIT License"],
        "requires": ["other>=1"],
    }
    assert found["bare"] == {"name": "bare", "expression": "", "license": "", "classifiers": [], "requires": []}


def test_collect_without_a_path_reads_the_running_environment() -> None:
    names = {str(entry["name"]).lower() for entry in judged_metadata.collect()}
    assert "pytest" in names


def test_collect_skips_a_distribution_without_a_name(tmp_path: Path) -> None:
    folder = tmp_path / "site" / "x-1.0.dist-info"
    folder.mkdir(parents=True)
    (folder / "METADATA").write_text("Metadata-Version: 2.4\nVersion: 1.0\n", encoding="utf-8")
    assert judged_metadata.collect([str(tmp_path / "site")]) == []


def test_script_entry_point_writes_the_json_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "metadata.json"
    monkeypatch.setattr(sys, "argv", ["judged_metadata.py", str(out)])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(Path(judged_metadata.__file__)), run_name="__main__")
    assert stopped.value.code == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert any(entry["name"].lower() == "pytest" for entry in written["distributions"])


def test_reader_imports_nothing_from_the_gate_package() -> None:
    """It runs in the judged environment, where ``eng_dev_gate`` may be the pull request's copy."""
    tree = ast.parse(Path(judged_metadata.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import reaches the package of the judged tree"
            imported.add(node.module or "")
    assert not {name for name in imported if name.split(".")[0] == "eng_dev_gate"}


def test_script_writes_the_interpreter_and_the_distribution_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC54a: the file also holds ``sys.executable`` and ``packages_distributions()`` of the judged environment."""
    site = tmp_path / "site"
    add_dist(site, "Some-Dist")
    (site / "Some_Dist-1.0.dist-info" / "top_level.txt").write_text("somemod\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(site))
    out = tmp_path / "metadata.json"
    monkeypatch.setattr(sys, "argv", ["judged_metadata.py", str(out)])
    with pytest.raises(SystemExit):
        runpy.run_path(str(Path(judged_metadata.__file__)), run_name="__main__")
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["executable"] == sys.executable
    assert written["packages"]["somemod"] == ["Some-Dist"]
    assert "Some-Dist" in {entry["name"] for entry in written["distributions"]}
