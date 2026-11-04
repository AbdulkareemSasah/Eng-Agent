"""Fixture: a toy member with ``[tool.eng-gate]`` thresholds and its own tests, for the ``tests`` step."""

from __future__ import annotations

from support.repo import Repo
from support.toy import GATE_YML, root_pyproject

MODULE = (
    '"""Toy module."""\n\n\n'
    "def sign(value: int) -> int:\n"
    '    """Return -1, 0 or 1."""\n'
    "    if value < 0:\n"
    "        return -1\n"
    "    if value > 0:\n"
    "        return 1\n"
    "    return 0\n"
)
FULL_TESTS = (
    "from a.mod import sign\n\n\ndef test_sign() -> None:\n    assert (sign(-2), sign(0), sign(3)) == (-1, 0, 1)\n"
)
PARTIAL_TESTS = "from a.mod import sign\n\n\ndef test_sign() -> None:\n    assert sign(3) == 1\n"


def member_pyproject(line: int = 95, branch: int = 90) -> str:
    """Return the toy member ``pyproject.toml`` with the given coverage thresholds."""
    return (
        '[project]\nname = "a"\nversion = "0.1.0"\nrequires-python = ">=3.14"\ndependencies = []\n'
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["src"]\n'
        '[tool.eng-gate]\nprofile = "tool"\nlayer = "tool"\nimport_names = ["a"]\n'
        f"coverage_line = {line}\ncoverage_branch = {branch}\n"
    )


def make_toy(repo: Repo, tests: str = FULL_TESTS, extra: dict[str, str] | None = None, **limits: int) -> None:
    """Write workspace root plus member ``pkgs/a`` with module, tests and optional ``extra`` files."""
    files = {
        "pyproject.toml": root_pyproject(["pkgs/a"]),
        ".gate/gate.yml": GATE_YML,
        "pkgs/a/pyproject.toml": member_pyproject(**limits),
        "pkgs/a/src/a/__init__.py": "",
        "pkgs/a/src/a/mod.py": MODULE,
        "pkgs/a/tests/test_mod.py": tests,
    }
    files.update({f"pkgs/a/{k}": v for k, v in (extra or {}).items()})
    repo.commit(files)
