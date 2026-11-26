"""Block, rule and workflow modules never import `eng_harness.tasklog` (plan 0015 T1; spec 0015 AC32)."""

import ast
import tomllib
from pathlib import Path

import eng_harness.tasklog as tasklog_module

PACKAGE = Path(tasklog_module.__file__).resolve().parents[3]  # packages/eng-harness
GUARDED = tasklog_module.__name__  # "eng_harness.tasklog"


def _is_tasklog(name: str) -> bool:
    """Whether the dotted `name` is the tasklog package or one of its modules."""
    return name == GUARDED or name.startswith(GUARDED + ".")


def _imports_tasklog(source: str) -> list[str]:
    """The static imports of the tasklog package in one module, as `<line>: <what>` in line order."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend(
                (node.lineno, f"{node.lineno}: import of {alias.name}")
                for alias in node.names
                if _is_tasklog(alias.name)
            )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                names = [node.module or "", *(alias.name for alias in node.names)]
                if any(name == "tasklog" or name.startswith("tasklog.") for name in names):
                    found.append(
                        (node.lineno, f"{node.lineno}: relative import of {'.' * node.level}{node.module or ''}")
                    )
            elif node.module == "eng_harness" and any(
                alias.name == "tasklog" or alias.name.startswith("tasklog.") for alias in node.names
            ):
                found.append((node.lineno, f"{node.lineno}: import of tasklog from eng_harness"))
            elif node.module is not None and _is_tasklog(node.module):
                found.append((node.lineno, f"{node.lineno}: import from {node.module}"))
    return [text for _, text in sorted(found)]


def _globs(*keys: str) -> list[str]:
    pyproject = PACKAGE / "pyproject.toml"
    table = tomllib.loads(pyproject.read_text(encoding="utf-8"))["tool"]["eng-gate"]
    return [pattern for key in keys for pattern in table[key]]


def modules(root: Path, globs: list[str]) -> list[Path]:
    """Every `.py` file under the directories that the `<dir>/**` globs name, relative to `root`."""
    found: set[Path] = set()
    for pattern in globs:
        assert pattern.endswith("/**"), pattern  # the form the package uses; others need this helper extended
        found.update(path for path in (root / pattern.removesuffix("/**")).rglob("*.py") if path.is_file())
    return sorted(found)


def test_blocks_do_not_import_tasklog() -> None:
    """AC32: no block, rule or workflow module imports the tasklog package (FB004 names top-level modules only)."""
    assert GUARDED == "eng_harness.tasklog"
    assert _imports_tasklog("import eng_harness.tasklog\n") == ["1: import of eng_harness.tasklog"]
    assert _imports_tasklog("from eng_harness.tasklog._records import TaskRecord\n") == [
        "1: import from eng_harness.tasklog._records"
    ]
    assert _imports_tasklog("from eng_harness import tasklog\n") == ["1: import of tasklog from eng_harness"]
    assert _imports_tasklog("from ..tasklog import scope\n") == ["1: relative import of ..tasklog"]
    assert _imports_tasklog("import eng_harness.tasklogger\nimport eng_harness.ctx\n") == []
    files = modules(PACKAGE, _globs("block_modules", "rule_modules"))  # workflows ride in block_modules
    names = {path.name for path in files}
    assert {"_change_set.py", "_requests.py"} <= names  # the merged workflow modules are scanned, not skipped
    problems = {
        path.relative_to(PACKAGE).as_posix(): found
        for path in files
        if (found := _imports_tasklog(path.read_text(encoding="utf-8")))
    }
    assert problems == {}
