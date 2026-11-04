"""The command line and the progress display cannot answer a request (spec 0006 AC2)."""

import ast
from pathlib import Path

import eng_harness.cli as cli_module

SRC = Path(__file__).resolve().parents[2] / "src" / "eng_harness"
ANSWER_NAMES = {"ApprovalAnswer", "InputAnswer", "BasisSetupAnswer"}
ALLOWED_FROM_PAGES = {"accept_answers_file", "PageServer", "PageApprovalPort", "PageInputPort", "PageBasisSetupPort"}


def _guarded() -> list[Path]:
    assert Path(cli_module.__file__).parent == SRC / "cli", "the rule guards the cli package"
    files = sorted((SRC / "cli").rglob("*.py")) + sorted((SRC / "progress").rglob("*.py")) + [SRC / "__main__.py"]
    return [path for path in files if path.exists()]


def _violations(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("eng_harness.pages._answers") and module != "eng_harness.pages._answers_file":
                found.append(f"{path.name}:{node.lineno} imports {module}")
            if module in {"eng_harness.pages", "eng_harness.pages._answers_file"}:
                found.extend(
                    f"{path.name}:{node.lineno} imports {a.name} from pages"
                    for a in node.names
                    if a.name not in ALLOWED_FROM_PAGES
                )
        elif isinstance(node, ast.Import):
            found.extend(
                f"{path.name}:{node.lineno} imports {a.name}"
                for a in node.names
                if a.name.startswith("eng_harness.pages._answers")
            )
        if isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in ANSWER_NAMES:
                found.append(f"{path.name}:{node.lineno} names {name}")
    return found


def test_no_answer_construction_outside_pages() -> None:
    files = _guarded()
    assert any(path.name == "_parser.py" for path in files)
    assert [v for path in files for v in _violations(path)] == []


def test_rule_detects_a_violation(tmp_path: Path) -> None:
    sample = tmp_path / "bad.py"
    sample.write_text("from eng_harness.pages import InputAnswer\nx = InputAnswer()\n", encoding="utf-8")
    assert _violations(sample)
