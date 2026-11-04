"""Golden data file lint (plan 0003 T6; spec 0003 AC46)."""

import json
from pathlib import Path

import pytest

from ._golden import GOLDEN_DIR, golden_files, lint_golden

GOOD = {
    "source": "eng-harness spec 0003 4.7 D3",
    "method_ref": "§4.7 D3",
    "synthetic": True,
    "derivation": "worked by hand",
    "inputs": {},
    "expected": {},
}
BAD = {
    "no source": {k: v for k, v in GOOD.items() if k != "source"},
    "blank source": {**GOOD, "source": "  "},
    "method_ref not a rule": {**GOOD, "method_ref": "somewhere"},
    "not synthetic": {**GOOD, "synthetic": False},
    "synthetic missing": {k: v for k, v in GOOD.items() if k != "synthetic"},
    "extra field": {**GOOD, "note": "x"},
    "no derivation": {**GOOD, "derivation": ""},
}


def test_sources_present() -> None:
    assert GOLDEN_DIR.is_dir()
    problems = {p.name: lint_golden(p) for p in golden_files()}
    assert {n: v for n, v in problems.items() if v} == {}


def test_lint_accepts_good(tmp_path: Path) -> None:
    path = tmp_path / "ok.json"
    path.write_text(json.dumps(GOOD), encoding="utf-8")
    assert lint_golden(path) == []


@pytest.mark.parametrize("name", BAD)
def test_lint_rejects(tmp_path: Path, name: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(BAD[name]), encoding="utf-8")
    assert lint_golden(path)


def test_lint_rejects_non_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    assert lint_golden(path)
