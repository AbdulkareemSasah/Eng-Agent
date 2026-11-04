"""FB003 (spec 4.8, AC31): host SDK imports outside a ``host`` directory."""

from __future__ import annotations

import pytest
from support.forbidden import lines, marked, scan

SOURCE = """\
import win32com.client  # <-
from win32com import client  # <-
import pythoncom  # <-
import pywintypes  # <-
import comtypes.client  # <-
import clr  # <-
from System.IO import Path  # <-
import Autodesk.Revit  # <-
clr.AddReference("x")  # <-
import win32comextra
import system
from . import clr
import json
"""


def test_flags_host_sdk_outside_host() -> None:
    findings = scan(SOURCE)
    assert lines(findings, "FB003") == marked(SOURCE)
    assert {f.code for f in findings} == {"FB003"}


@pytest.mark.parametrize(
    ("local", "flagged"),
    [
        ("src/pkg/host/bridge.py", False),
        ("src/host/bridge.py", False),
        ("src/pkg/sub/host/deep.py", False),
        ("src/pkg/host_utils/bridge.py", True),
        ("src/pkg/host.py", True),
        ("src/pkg/hosts/bridge.py", True),
        ("src/pkg/bridge.py", True),
    ],
)
def test_host_directory_component(local: str, flagged: bool) -> None:
    assert bool(lines(scan(SOURCE, local), "FB003")) is flagged
