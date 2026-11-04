"""FB002 (spec 4.8, AC30): dynamic code execution."""

from __future__ import annotations

from support.forbidden import lines, marked, scan

SOURCE = """\
import builtins
import os
import os as operating
import re
import runpy
import subprocess
from os import popen as spawn
from runpy import run_path
eval("1")  # <-
exec("x = 1")  # <-
compile("1", "f", "eval")  # <-
__import__("os")  # <-
os.system("ls")  # <-
os.popen("ls")  # <-
runpy.run_module("m")  # <-
runpy.run_path("p")  # <-
subprocess.run(["ls"], shell=True)  # <-
operating.system("ls")  # <-
spawn("ls")  # <-
run_path("p")  # <-
builtins.eval("1")  # <-
subprocess.run(["ls"])
subprocess.run("ls", shell=False)
re.compile("a")
obj.eval("1")
evaluation = "eval"
"""


def test_flags_dynamic_execution() -> None:
    findings = scan(SOURCE)
    assert lines(findings, "FB002") == marked(SOURCE)
    assert {f.code for f in findings} == {"FB002"}
    assert len(findings) == len(marked(SOURCE))
