"""No locale-dependent formatting in the package (spec 0006 AC58, section 4.7)."""

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "eng_harness"
_DIRECTIVE = re.compile(r"%[aAbBcpPxX]")


def _modules() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _violations(path: Path) -> list[str]:
    found: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == "locale" for a in node.names):
                found.append(f"{path.name}:{node.lineno} imports locale")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "locale":
                found.append(f"{path.name}:{node.lineno} imports locale")
        elif isinstance(node, ast.Attribute) and node.attr == "strftime":
            found.append(f"{path.name}:{node.lineno} calls strftime")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and _DIRECTIVE.search(node.value):
            found.append(f"{path.name}:{node.lineno} locale-dependent time directive")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "format"
            and len(node.args) == 2
            and isinstance(node.args[1], ast.Constant)
            and str(node.args[1].value).endswith("n")
        ):
            found.append(f"{path.name}:{node.lineno} uses the n format type")
    return found


def test_no_locale_calls() -> None:
    assert _modules(), "no modules found"
    problems = [p for path in _modules() for p in _violations(path)]
    assert problems == []


def test_rule_detects_violations(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("import locale\nx = now.strftime('%A')\ny = format(1.0, 'n')\n", encoding="utf-8")
    assert len(_violations(bad)) == 4
