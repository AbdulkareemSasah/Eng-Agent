"""FB007 (spec 4.8, AC35): the builtin ``print``, also through an alias."""

from __future__ import annotations

from support.forbidden import lines, marked, scan

SOURCE = """\
import builtins
import sys
from builtins import print as out
print("x")  # <-
show = print
show("y")  # <-
out("z")  # <-
builtins.print("w")  # <-
logger.info("ok")
sys.stdout.write("ok")
obj.print("x")
note = "print(1)"
def print_report() -> None: ...
print_report()
"""


def test_flags_print() -> None:
    findings = scan(SOURCE)
    assert lines(findings, "FB007") == marked(SOURCE)
    assert {f.code for f in findings} == {"FB007"}
    assert len(findings) == len(marked(SOURCE))
