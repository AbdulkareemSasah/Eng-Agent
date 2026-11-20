"""Revit build check and role start options (plan 0011 T4; spec 0011 AC3, section 4.3)."""

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
from eng_harness.servers import ServerManager, ServersConfig
from eng_harness.servers._buildcheck import BuildExpectation
from eng_harness.servers._config import ServerConfig
from eng_harness.servers._launcher import LaunchedProcess, LaunchSpec, PosixLauncher

# Spec 0011 section 4.4: bridge-destructive MCP names (kind destructive).
_DESTRUCTIVE = frozenset(
    {
        "revit_set_type_parameter_values",
        "revit_set_element_parameter_values",
        "revit_set_parameter_value_by_guid",
        "revit_change_element_type",
    }
)
_WRITE_TOOLS = frozenset(
    {
        "revit_open_model",
        "revit_duplicate_family_type",
        *_DESTRUCTIVE,
    }
)
_FAKE = Path(__file__).resolve().parents[2] / "fakes" / "sasaah_revit" / "server.py"
_PIPE = r"\\.\pipe\sasaah-revit-pinned"


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
    """BuildExpectation for a Revit role: status tool and destructive set from spec 0011 section 4.3."""
    base = revit_allowlist(role=role).build_expectation()
    return replace(
        base,
        status_tool="revit_connection_status",
        destructive_tools=_DESTRUCTIVE if role == "write" else frozenset(),
    )


def _revit_config(
    tmp_path: Path,
    control: Path,
    *,
    pipe_name: str = _PIPE,
    seed: Mapping[str, Any] | None = None,
    faults: list[dict[str, Any]] | None = None,
) -> tuple[ServersConfig, Path]:
    """A `[servers.revit]` section that launches the synthetic fake; exe and add-in hashes match the pin."""
    control.write_text(
        json.dumps({"faults": faults or [], "seed": dict(seed or {})}),
        encoding="utf-8",
    )
    allowlist = revit_allowlist(role="write")
    wrapper = tmp_path / "sasaah-revit-mcp"
    wrapper.write_text(
        "#!/bin/sh\n"
        f'export SASAAH_REVIT_FAKE_CONTROL="{control}"\n'
        f'exec "{sys.executable}" "{_FAKE}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    addin = tmp_path / "addin.dll"
    addin.write_bytes(b"revit-addin-bytes")
    addin_hash = hashlib.sha256(addin.read_bytes()).hexdigest()
    exe = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    section = ServerConfig.model_validate(
        {
            "adapter": "sasaah-revit-mcp",
            "command": str(wrapper),
            "pipe_name": pipe_name,
            "client_grace_s": 5,
            "host_key": "revit",
            "build": {
                "sasaah_commit": allowlist.sasaah_commit,
                "exe_sha256": exe,
                "addin_paths": [str(addin)],
                "addin_sha256": [addin_hash],
            },
            "roles": {
                "read": {"classes": ["session", "call"], "call_timeout_s": 10},
                "write": {"classes": ["attended"], "call_timeout_s": 90},
            },
        }
    )
    return ServersConfig(servers={"revit": section}), wrapper


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


def _checks() -> dict[str, BuildExpectation]:
    return {"revit/read": _expectation("read"), "revit/write": _expectation("write")}


@pytest.fixture
def launcher() -> RecordingLauncher:
    return RecordingLauncher()


@pytest.mark.parametrize(
    ("faults", "seed", "keyword"),
    [
        ([{"fault": "code_toolset_on"}], {}, "revit_compile_and_run"),
        ([{"fault": "destructive_toolset_off"}], {}, "bridgeToolsets"),
        ([], {"ping_status": "down"}, "ping_status"),
        ([], {"catalog_version": ""}, "catalog_version"),
    ],
)
def test_build_check_reasons(
    tmp_path: Path,
    launcher: RecordingLauncher,
    faults: list[dict[str, Any]],
    seed: dict[str, Any],
    keyword: str,
) -> None:
    """AC3: each build-check failure names its cause (spec 0011 section 4.3 items 4 to 6)."""
    control = tmp_path / "control.json"
    cfg, _wrapper = _revit_config(tmp_path, control, faults=faults, seed=seed)

    async def body(manager: ServerManager) -> None:
        checks = await manager.preflight({})
        write_checks = [c for c in checks if c.server == "revit"]
        assert write_checks
        failed = [c for c in write_checks if not c.ok]
        assert failed, f"expected a failed check, got {write_checks!r}"
        assert failed[0].reason is not None
        assert keyword in failed[0].reason

    _run(tmp_path, cfg, launcher, body, check=_checks())


def test_read_role_has_no_write_tool(tmp_path: Path, launcher: RecordingLauncher) -> None:
    """AC3: the read role lists no bridge tool that writes (spec 0011 section 4.3 item 4)."""
    control = tmp_path / "control.json"
    cfg, _wrapper = _revit_config(tmp_path, control)

    async def body(manager: ServerManager) -> None:
        tools = await manager.list_tools("revit", "read")
        names = {tool.name for tool in tools}
        assert names.isdisjoint(_WRITE_TOOLS)
        assert "revit_connection_status" in names
        assert "revit_list_levels" in names
        assert launcher.specs
        argv = launcher.specs[0].argv
        assert "--read-only" in argv
        assert "--pipe-name" in argv
        assert argv[argv.index("--pipe-name") + 1] == _PIPE
        assert "--bridge-timeout-ms" in argv
        assert "--disable-send-code" in argv
        assert "--disable-adaptive-bake" in argv
        assert "--no-cache-send-code-bodies" in argv
        checks = await manager.preflight({})
        assert any(c.ok for c in checks), f"expected an ok check among {checks!r}"

    _run(tmp_path, cfg, launcher, body, check=_checks())
