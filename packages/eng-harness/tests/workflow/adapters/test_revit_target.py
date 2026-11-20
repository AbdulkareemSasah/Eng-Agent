"""Pinned Revit pipe (plan 0011 T4; spec 0011 AC4)."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import anyio
import pytest

from eng_harness.adapters.revit import revit_allowlist
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._buildcheck import BuildExpectation
from eng_harness.servers._config import ServerConfig
from eng_harness.servers._launcher import LaunchedProcess, LaunchSpec, PosixLauncher

_FAKE = Path(__file__).resolve().parents[2] / "fakes" / "sasaah_revit" / "server.py"
_PIPE = r"\\.\pipe\sasaah-revit-pinned"
_OTHER = r"\\.\pipe\sasaah-revit-other"


class RecordingLauncher:
    """POSIX launcher that records every process and its launch spec."""

    def __init__(self) -> None:
        self.started: list[LaunchedProcess] = []
        self.specs: list[LaunchSpec] = []
        self._inner = PosixLauncher()

    def start(self, spec: LaunchSpec) -> LaunchedProcess:
        process = self._inner.start(spec)
        self.started.append(process)
        self.specs.append(spec)
        return process


def _expectation(role: str) -> BuildExpectation:
    base = revit_allowlist(role=role).build_expectation()
    return replace(base, status_tool="revit_connection_status")


def _revit_config(tmp_path: Path, control: Path, *, pipe_name: str = _PIPE) -> ServersConfig:
    control.write_text(
        json.dumps(
            {
                "faults": [],
                "seed": {
                    "pipe_name": pipe_name,
                    "targets": [
                        {"pipe_name": pipe_name, "revit_version": "2026"},
                        {"pipe_name": _OTHER, "revit_version": "2026"},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    allowlist = revit_allowlist(role="write")
    wrapper = tmp_path / "sasaah-revit-mcp"
    wrapper.write_text(
        f'#!/bin/sh\nexport SASAAH_REVIT_FAKE_CONTROL="{control}"\nexec "{sys.executable}" "{_FAKE}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    addin = tmp_path / "addin.dll"
    addin.write_bytes(b"revit-addin-bytes")
    section = ServerConfig.model_validate(
        {
            "adapter": "sasaah-revit-mcp",
            "command": str(wrapper),
            "pipe_name": pipe_name,
            "client_grace_s": 5,
            "host_key": "revit",
            "build": {
                "sasaah_commit": allowlist.sasaah_commit,
                "exe_sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest(),
                "addin_paths": [str(addin)],
                "addin_sha256": [hashlib.sha256(addin.read_bytes()).hexdigest()],
            },
            "roles": {
                "read": {"classes": ["session", "call"], "call_timeout_s": 10},
                "write": {"classes": ["attended"], "call_timeout_s": 90},
            },
        }
    )
    return ServersConfig(servers={"revit": section})


def _run(
    tmp_path: Path,
    config: ServersConfig,
    launcher: RecordingLauncher,
    body: Callable[[ServerManager], Any],
    check: Mapping[str, BuildExpectation] | None = None,
) -> None:
    async def scenario() -> None:
        async with ServerManager(config, tmp_path / "run", launcher=launcher, check=check) as manager:
            await body(manager)

    anyio.run(scenario)


def _text(result: Any) -> dict[str, Any]:
    assert len(result.content) == 1
    body: dict[str, Any] = json.loads(result.content[0].text)
    return body


@pytest.fixture
def launcher() -> RecordingLauncher:
    return RecordingLauncher()


def test_pipe_pinned(tmp_path: Path, launcher: RecordingLauncher) -> None:
    """AC4: the configured pipe is started and returned; switch_target is never callable; only that pipe is used."""
    control = tmp_path / "control.json"
    cfg = _revit_config(tmp_path, control)
    check = {"revit/read": _expectation("read"), "revit/write": _expectation("write")}

    async def body(manager: ServerManager) -> None:
        checks = await manager.preflight({})
        assert any(c.ok for c in checks), f"expected ok check, got {checks!r}"
        assert launcher.specs
        argv = launcher.specs[0].argv
        assert "--pipe-name" in argv
        assert argv[argv.index("--pipe-name") + 1] == _PIPE
        target = _text(await manager.call("revit", "read", "revit_get_current_target", {}, CallEffect.READ))
        assert target["pipe_name"] == _PIPE
        listed = await manager.list_tools("revit", "read")
        names = {tool.name for tool in listed}
        assert "revit_switch_target" not in names
        assert "revit_switch_target" not in revit_allowlist().tool_names
        available = _text(await manager.call("revit", "read", "revit_list_available_targets", {}, CallEffect.READ))
        pipes = {row["pipe_name"] for row in available["targets"]}
        assert pipes == {_PIPE, _OTHER}
        assert target["pipe_name"] == _PIPE

    _run(tmp_path, cfg, launcher, body, check=check)
