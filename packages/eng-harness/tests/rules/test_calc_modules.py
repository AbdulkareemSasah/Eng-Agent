"""Calc-module rules (plan 0003 T6; spec 0003 AC3, 4.3): imports, purity, no module state, FB005 literal forms."""

import ast
from pathlib import Path

import pytest

import eng_harness.calcs as calcs_package

CALCS = Path(calcs_package.__file__).resolve().parent
MODULES = sorted(CALCS.glob("*.py"))


def check_source(source: str) -> list[str]:
    """Return the rule violations of one calc module's source (stub: the rules arrive in the implementation commit)."""
    raise NotImplementedError("calc-module rules are not written yet")


VIOLATIONS = {
    "import os": "import",
    "import eng_harness.servers": "import",
    "from eng_contract.units import convert": "import",
    "from . import _state": "import",
    "def f():\n    import math\n": "inside",
    "def f():\n    return open('x')\n": "open",
    "def f():\n    global X\n": "global",
    "CACHE = {}": "mutable",
    "ITEMS: list[int] = []": "mutable",
    "X = 0.5": "FB005",
    "def f(a):\n    return a * 2": "FB005",
    "from eng_contract.cited import Cited\nX = Cited(3, '')": "FB005",
}
ALLOWED = [
    "import math\nfrom fractions import Fraction\nfrom pydantic import BaseModel",
    "from eng_contract.units import kind_for_field, unit",
    "from eng_contract.kinds.neutral import X",
    "from eng_harness.calcs import _state\nfrom eng_harness.calc import calc",
    "from eng_contract.cited import Cited\nX = Cited(3, 'spec')\nY = [1, 2][0]\nZ: float = 1.5",
    "def f(a: list[int]) -> bool:\n    return len(a) == 2 and a[-1] > a[0]",
    "REGISTRY = Registry(kinds)",
]


def test_calc_module_rules() -> None:
    assert MODULES, "the calcs package holds at least its __init__"
    found = [f"{m.name}: {v}" for m in MODULES for v in check_source(m.read_text(encoding="utf-8"))]
    assert found == []


@pytest.mark.parametrize(("source", "word"), VIOLATIONS.items())
def test_rules_detect(source: str, word: str) -> None:
    ast.parse(source)
    assert any(word in v for v in check_source(source))


@pytest.mark.parametrize("source", ALLOWED)
def test_rules_allow(source: str) -> None:
    assert check_source(source) == []
