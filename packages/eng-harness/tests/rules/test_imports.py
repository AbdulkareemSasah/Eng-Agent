"""Imports of the modules of spec 0006 (AC60)."""

import ast
import sys
from pathlib import Path

import eng_harness.cli as cli_module

SRC = Path(__file__).resolve().parents[2] / "src" / "eng_harness"
ALLOWED = set(sys.stdlib_module_names) | {"eng_contract", "pydantic", "eng_harness"}
OWN = ("cli", "progress", "pages", "report")


def _modules() -> list[Path]:
    assert Path(cli_module.__file__).parent == SRC / "cli", "the rule guards the cli package"
    files = [SRC / "_text.py", SRC / "_html.py", SRC / "__main__.py"]
    for folder in OWN:
        files.extend(sorted((SRC / folder).rglob("*.py")))
    return [path for path in files if path.exists()]


def _third_party(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names = [node.module or ""]
        found.extend(f"{path.name}: {n}" for n in names if n.split(".")[0] not in ALLOWED)
    return found


def test_third_party_imports_limited() -> None:
    files = _modules()
    assert any(path.name == "_parser.py" for path in files)
    assert [v for path in files for v in _third_party(path)] == []


def test_rule_detects_a_violation(tmp_path: Path) -> None:
    sample = tmp_path / "bad.py"
    sample.write_text("import requests\nfrom flask import Flask\nimport json\n", encoding="utf-8")
    assert len(_third_party(sample)) == 2
