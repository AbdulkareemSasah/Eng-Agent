"""FB005 (spec 4.8, AC33): numeric literals in check, calc, block and rule modules, and the allowed forms A1 to A3."""

from __future__ import annotations

import pytest
from eng_dev_gate.checks.forbidden.engine import ModuleGlobs
from support.forbidden import lines
from support.forbidden_b import expected_lines, scan_b

SOURCE = """\
from typing import Annotated, Literal
from pkg.cited import Cited
import pkg.cited as cited_module

LIMIT = 0  # <-
ONE = 1  # <-
RATIO = 1.0  # <-
NEGATIVE = -2.5  # <-
IMAGINARY = 3j  # <-
FLAG = True
NOTHING = None
NAME = "7"
BIG = 10_000  # <-
HEX = 0x10  # <-
if ratio <= 1.0:  # <-
    pass
for _ in range(3):  # <-
    pass


def f(a: int = 5, *, b: float = 0.5) -> Literal[1, 2]:  # <-2
    c: Literal[3] = 3  # <-
    d: Annotated[int, 4]
    return a


def g(values: list[int]) -> int:
    first = values[0]
    last = values[-1]
    tail = values[1:]
    head = values[:2]
    window = values[1:-1]
    step = values[::2]  # <-
    wrong = values[0.5]  # <-
    expr = values[i + 1]  # <-
    both = values[0, 1]  # <-2
    return first + last + len(tail) * 2  # <-


def h(items: list[int]) -> bool:
    empty = len(items) == 0
    short = 0 < len(items) < 5
    mixed = len(items) + 1 == 3  # <-2
    other = count == 0  # <-
    floaty = len(items) == 0.5  # <-
    return empty or short


A = Cited(0.75, "ACI 318-14 Table 21.2.1(b)")
B = Cited(0.75, source="ACI 318-14 Table 21.2.1(b)")
C = Cited(value=0.75, source="ACI 318-14 Table 21.2.1(b)")
D = cited_module.Cited(-0.9, "ACI 318-14")
E = Cited(0.75)  # <-
F = Cited(0.75, "")  # <-
G = Cited(0.75, source="")  # <-
H = Cited(0.75, 5)  # <-2
I = Cited(x + 1, "ACI")  # <-
J = Cited(0.75, "ACI", 2)  # <-
K = Other(0.75, "ACI")  # <-
"""


def test_numeric_literal_forms() -> None:
    findings = scan_b(SOURCE, "src/pkg/calc/c.py")
    assert sorted(f.line for f in findings if f.line) == expected_lines(SOURCE)
    assert {f.code for f in findings} == {"FB005"}


@pytest.mark.parametrize(
    "local", ["src/pkg/checks/c.py", "src/pkg/calc/c.py", "src/pkg/blocks/c.py", "src/pkg/rules/c.py"]
)
def test_the_four_module_kinds_are_scanned(local: str) -> None:
    assert lines(scan_b("X = 1\n", local), "FB005") == [1]


@pytest.mark.parametrize("local", ["src/pkg/other.py", "src/pkg/checks_extra.py", "tests/test_x.py"])
def test_other_modules_are_not_scanned(local: str) -> None:
    assert lines(scan_b("X = 1\n", local), "FB005") == []


def test_no_globs_scan_nothing() -> None:
    assert scan_b("X = 1\n", "src/pkg/calc/c.py", ModuleGlobs()) == []


def test_message_names_the_value() -> None:
    (finding,) = scan_b("X = -2.5\n", "src/pkg/calc/c.py")
    assert finding.code == "FB005"
    assert "-2.5" in finding.message
    assert finding.line == 1


def test_annotations_and_docstrings_are_not_scanned() -> None:
    source = '"""Doc 1."""\nx: Literal[1, 2] = None\n\n\ndef f(a: Literal[3]) -> Literal[4]:\n    """Doc 2."""\n'
    assert scan_b(source, "src/pkg/calc/c.py") == []
