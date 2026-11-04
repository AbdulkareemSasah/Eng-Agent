"""FB004 (spec 4.8, AC32): I/O, clock, random and environment use in block and rule modules."""

from __future__ import annotations

import pytest
from support.forbidden import lines
from support.forbidden_b import expected_lines, scan_b

SOURCE = """\
import os  # <-
import os.path  # <-
import sys, json  # <-
from pathlib import Path  # <-
from urllib.request import urlopen  # <-
import time as clock  # <-
from datetime import datetime  # <-
import random  # <-
import secrets  # <-
import uuid  # <-
import requests  # <-
import httpx  # <-
import io, shutil, tempfile, socket, ssl, http, subprocess, sqlite3  # <-
import json
import math
from . import os_helpers
from .os import thing
text = open("f").read()  # <-
name = input("x")  # <-
reader = open
data = reader("f")  # <-
import builtins
builtins.open("f")  # <-
obj.open("f")
obj.input("f")
note = "import os; open('f')"
"""


@pytest.mark.parametrize("local", ["src/pkg/blocks/beam.py", "src/pkg/rules/limits.py"])
def test_flags_io_in_block_and_rule_modules(local: str) -> None:
    findings = scan_b(SOURCE, local)
    assert lines(findings, "FB004") == expected_lines(SOURCE)
    assert {f.code for f in findings} == {"FB004"}
    assert len(findings) == len(expected_lines(SOURCE))
    assert {f.path for f in findings} == {f"pkgs/x/{local}"}


@pytest.mark.parametrize("local", ["src/pkg/checks/c.py", "src/pkg/calc/c.py", "src/pkg/other.py", "tests/test_x.py"])
def test_other_modules_are_not_scanned(local: str) -> None:
    assert lines(scan_b(SOURCE, local), "FB004") == []
