"""Fixture: a scripted ``ToolRunner`` that stands for ``uv`` and the metadata reader of the judged environment."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from eng_dev_gate.toolrun import ToolResult


def environment_payload(packages: Mapping[str, Sequence[str]] | None = None, executable: str = sys.executable) -> str:
    """The JSON file ``judged_metadata.py`` writes: interpreter, installed distributions and the module map."""
    return json.dumps({"executable": executable, "distributions": [], "packages": dict(packages or {})})


class EnvironmentRunner:
    """Answers ``uv lock --check`` with ``lock``, the metadata run by writing ``payload`` to its output path argument.

    Every other command (the type checker, for example) succeeds with empty output. ``calls`` records all of them.
    """

    def __init__(self, payload: str | None = None, lock: int = 0) -> None:
        self.payload = environment_payload() if payload is None else payload
        self.lock = lock
        self.calls: list[tuple[list[str], Path]] = []

    def run(self, argv: Sequence[str], cwd: Path, *, timeout_seconds: float | None = None) -> ToolResult:
        self.calls.append((list(argv), cwd))
        if argv[:2] == ["uv", "lock"]:
            return ToolResult(exit_code=self.lock, output="lock output")
        if argv[0] == "uv" and "-I" in argv:
            Path(argv[-1]).write_text(self.payload, encoding="utf-8")
        return ToolResult(exit_code=0, output="")
