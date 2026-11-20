"""Shared helpers for Revit edit workflow tests (plan 0011 T8)."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import anyio
from eng_harness.adapters.revit import revit_allowlist
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._buildcheck import BuildExpectation
from eng_harness.servers._config import ServerConfig
from eng_harness.servers._launcher import LaunchedProcess, LaunchSpec, PosixLauncher

_FAKE = Path(__file__).resolve().parents[2] / "fakes" / "sasaah_revit" / "server.py"
PIPE = r"\\.\pipe\sasaah-revit-edits"
LENGTH_SPEC = "autodesk.spec.aec:length-2.0.0"
FAMILY = "Concrete-Rectangular-Column"
BOUND = Path(r"C:\models\edits.rvt")
B_FT = 1.0
H_FT = 1.0


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


def expectation(role: str) -> BuildExpectation:
    base = revit_allowlist(role=role).build_expectation()
    return replace(base, status_tool="revit_connection_status")


def length_param(name: str, raw_ft: float, *, read_only: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "rawValue": raw_ft,
        "displayValue": f"{raw_ft} ft",
        "specId": LENGTH_SPEC,
        "builtInParameter": name.upper(),
        "storageType": "Double",
        "isReadOnly": read_only,
    }


def seed_model(
    *,
    elements: list[dict[str, Any]] | None = None,
    types: list[dict[str, Any]] | None = None,
    active_path: str | None = None,
    document_path: str | None = None,
) -> dict[str, Any]:
    column = {
        "element_id": 3001,
        "unique_id": "col-3001",
        "category": "OST_StructuralColumns",
        "family": FAMILY,
        "type_id": 2001,
        "type_name": "C300x300",
        "level_id": 100,
        "level_name": "Level 1",
        "location_kind": "curve",
        "i": {"x": 0.0, "y": 0.0, "z": 0.0},
        "j": {"x": 0.0, "y": 0.0, "z": 3000.0},
        "parameters": [length_param("b", B_FT), length_param("h", H_FT)],
    }
    type_row = {
        "type_id": 2001,
        "family": FAMILY,
        "name": "C300x300",
        "family_id": 1001,
        "category": "OST_StructuralColumns",
        "parameters": [length_param("b", B_FT), length_param("h", H_FT)],
        "instance_ids": [3001],
    }
    path = document_path or str(BOUND)
    return {
        "pipe_name": PIPE,
        "targets": [{"pipe_name": PIPE, "revit_version": "2026"}],
        "catalog_version": "test-catalog",
        "ping_status": "ok",
        "document": {
            "path": path,
            "title": "edits",
            "is_workshared": False,
            "revit_version": "2026",
        },
        "active_path": active_path if active_path is not None else path,
        "levels": [{"element_id": 100, "name": "Level 1", "elevation_mm": 0.0}],
        "grids": [],
        "elements": elements if elements is not None else [column],
        "types": types if types is not None else [type_row],
        "worksets": [],
        "warnings": [],
        "destructive_toolset": True,
        "code_toolset": False,
        "next_type_id": 2100,
        "next_element_id": 4000,
    }


def role_map() -> dict[str, dict[str, Any]]:
    return {
        FAMILY: {
            "section_b": {"name": "b", "status": "candidate"},
            "section_h": {"name": "h", "status": "candidate"},
            "material": {"name": "Material", "status": "candidate"},
        }
    }


def revit_config(
    tmp_path: Path,
    control: Path,
    *,
    seed: Mapping[str, Any] | None = None,
    faults: list[dict[str, Any]] | None = None,
) -> ServersConfig:
    control.write_text(
        json.dumps({"faults": faults or [], "seed": dict(seed or seed_model())}),
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
            "pipe_name": PIPE,
            "client_grace_s": 5,
            "host_key": "revit",
            "parameters": role_map(),
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


def run_scenario(tmp_path: Path, config: ServersConfig, body: Callable[[ServerManager], Any]) -> None:
    check = {"revit/read": expectation("read"), "revit/write": expectation("write")}

    async def scenario() -> None:
        async with ServerManager(config, tmp_path / "run", launcher=RecordingLauncher(), check=check) as manager:
            await body(manager)

    anyio.run(scenario)


async def call_dump(
    manager: ServerManager, tool: str, arguments: dict[str, Any], effect: CallEffect, *, role: str = "read"
) -> dict[str, Any]:
    result = await manager.call("revit", role, tool, arguments, effect)
    return result.model_dump(by_alias=True)
