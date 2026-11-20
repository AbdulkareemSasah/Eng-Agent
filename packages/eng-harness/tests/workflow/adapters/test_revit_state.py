"""Revit model-state reader, chunked reads and neutral kinds (plan 0011 T7; spec 0011 AC9, AC11, §4.5, §4.9).

Workflow tests drive the synthetic fake through ServerManager and `RevitStateReader`. Parameter seeds use
`rawValue` (spec 0011 §4.6). The packaged fake default still emits `value` (outside this task's file list).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.quantity import Quantity

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters.revit import revit_allowlist
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._buildcheck import BuildExpectation
from eng_harness.servers._config import ServerConfig
from eng_harness.servers._launcher import LaunchedProcess, LaunchSpec, PosixLauncher

_FAKE = Path(__file__).resolve().parents[2] / "fakes" / "sasaah_revit" / "server.py"
_PIPE = r"\\.\pipe\sasaah-revit-state"
_LENGTH_SPEC = "autodesk.spec.aec:length-2.0.0"
_FAMILY = "Concrete-Rectangular-Column"
# 1.0 ft → 304.8 mm (eng_contract.units, NIST SP 811 international foot; spec 0011 §4.6 / §4.13).
_B_FT = 1.0
_H_FT = 1.0
_B_MM = 304.8
LIST_CAP = 1000  # spec 0011 §4.5: list_elements caps at 1000 with no offset
_BOUND = Path(r"C:\models\state.rvt")


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


def _length_param(name: str, raw_ft: float) -> dict[str, Any]:
    """A length parameter in the §4.6 shape (`rawValue` in feet, candidate specId from the fake §4.13)."""
    return {
        "name": name,
        "rawValue": raw_ft,
        "displayValue": f"{raw_ft} ft",
        "specId": _LENGTH_SPEC,
        "builtInParameter": name.upper(),
        "storageType": "Double",
        "isReadOnly": False,
    }


def _rotation_param(raw_rad: float = 0.0) -> dict[str, Any]:
    """Instance rotation role parameter: rawValue in radians (§4.6 angle; L6). No invented specId."""
    return {
        "name": "Cross-Section Rotation",
        "rawValue": raw_rad,
        "displayValue": "0.00",
        "specId": "",
        "builtInParameter": "STRUCTURAL_BEND_DIR_ANGLE",
        "storageType": "Double",
        "isReadOnly": False,
    }


def _complete_column(*, element_id: int = 3001, level_id: int = 100, unique_id: str = "col-3001") -> dict[str, Any]:
    """One column with endpoints and mapped roles so neutral kinds can emit a row (AC11)."""
    return {
        "element_id": element_id,
        "unique_id": unique_id,
        "category": "OST_StructuralColumns",
        "family": _FAMILY,
        "type_id": 2001,
        "type_name": "C300x300",
        "level_id": level_id,
        "level_name": "Level 1",
        "location_kind": "curve",
        "i": {"x": 0.0, "y": 0.0, "z": 0.0},
        "j": {"x": 0.0, "y": 0.0, "z": 3000.0},
        "parameters": [_length_param("b", _B_FT), _rotation_param(0.0)],
    }


def _seed_complete() -> dict[str, Any]:
    """Model with one complete column and one incomplete framing member."""
    column = _complete_column()
    type_row = {
        "type_id": 2001,
        "family": _FAMILY,
        "name": "C300x300",
        "family_id": 1001,
        "category": "OST_StructuralColumns",
        "parameters": [_length_param("b", _B_FT), _length_param("h", _H_FT)],
        "instance_ids": [3001],
    }
    framing = {
        "element_id": 3002,
        "unique_id": "frm-3002",
        "category": "OST_StructuralFraming",
        "family": "Concrete-Rectangular-Beam",
        "type_id": 2002,
        "type_name": "B300x600",
        "level_id": 100,
        "level_name": "Level 1",
        "location_kind": "curve",
        "i": {"x": 0.0, "y": 0.0, "z": 3000.0},
        "j": {"x": 4000.0, "y": 0.0, "z": 3000.0},
        "parameters": [],
    }
    return {
        "pipe_name": _PIPE,
        "targets": [{"pipe_name": _PIPE, "revit_version": "2026"}],
        "catalog_version": "test-catalog",
        "ping_status": "ok",
        "document": {
            "path": str(_BOUND),
            "title": "state",
            "is_workshared": False,
            "revit_version": "2026",
        },
        "active_path": str(_BOUND),
        "levels": [
            {"element_id": 100, "name": "Level 1", "elevation_mm": 0.0},
            {"element_id": 101, "name": "Level 2", "elevation_mm": 3000.0},
        ],
        "grids": [
            {
                "element_id": 110,
                "name": "A",
                "start": {"x": 0.0, "y": 0.0, "z": 0.0},
                "end": {"x": 10000.0, "y": 0.0, "z": 0.0},
                "length_mm": 10000.0,
            }
        ],
        "elements": [column, framing],
        "types": [
            type_row,
            {
                "type_id": 2002,
                "family": "Concrete-Rectangular-Beam",
                "name": "B300x600",
                "family_id": 1002,
                "category": "OST_StructuralFraming",
                "parameters": [],
                "instance_ids": [3002],
            },
        ],
        "worksets": [{"id": 1, "name": "Workset1", "kind": "UserWorkset", "element_count": 2}],
        "warnings": [],
        "destructive_toolset": True,
        "code_toolset": False,
    }


def _role_map() -> dict[str, dict[str, Any]]:
    """Family role map for the complete column (spec 0011 §4.8; names from the seed)."""
    return {
        _FAMILY: {
            "section_b": {"name": "b", "status": "candidate"},
            "section_h": {"name": "h", "status": "candidate"},
            "rotation": {"name": "Cross-Section Rotation", "status": "candidate"},
            "material": {"name": "Material", "status": "candidate"},
        }
    }


def _revit_config(
    tmp_path: Path,
    control: Path,
    *,
    seed: Mapping[str, Any] | None = None,
    faults: list[dict[str, Any]] | None = None,
    parameters: Mapping[str, Mapping[str, Any]] | None = None,
) -> ServersConfig:
    control.write_text(
        json.dumps({"faults": faults or [], "seed": dict(seed or _seed_complete())}),
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
            "pipe_name": _PIPE,
            "client_grace_s": 5,
            "host_key": "revit",
            "parameters": dict(parameters or _role_map()),
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


def _run(tmp_path: Path, config: ServersConfig, body: Callable[[ServerManager], Any]) -> None:
    check = {"revit/read": _expectation("read"), "revit/write": _expectation("write")}

    async def scenario() -> None:
        async with ServerManager(config, tmp_path / "run", launcher=RecordingLauncher(), check=check) as manager:
            await body(manager)

    anyio.run(scenario)


async def _call_dump(
    manager: ServerManager, tool: str, arguments: dict[str, Any], effect: CallEffect
) -> dict[str, Any]:
    result = await manager.call("revit", "read", tool, arguments, effect)
    return result.model_dump(by_alias=True)


def _reader(manager: ServerManager, config: ServersConfig) -> Any:
    from eng_harness.adapters.revit._parameters import load_role_map
    from eng_harness.adapters.revit._state import RevitStateReader

    section = config.servers["revit"]
    roles = load_role_map(section.parameters)

    async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        return await _call_dump(manager, tool, arguments, effect)

    return RevitStateReader(call=call, role_map=roles, catalog_version="test-catalog")


def test_kinds_and_ids(tmp_path: Path) -> None:
    """AC9: harness Revit kinds validate; every structure element carries unique_id and element_id."""
    control = tmp_path / "control.json"
    config = _revit_config(tmp_path, control)

    async def body(manager: ServerManager) -> None:
        reader = _reader(manager, config)
        read = await reader.read(bound_path=_BOUND)
        for kind in (
            "harness.revit_status/1",
            "harness.revit_levels/1",
            "harness.revit_grids/1",
            "harness.revit_structure/1",
        ):
            assert kind in HARNESS_KINDS
            HARNESS_KINDS[kind].model_validate(read.payloads[kind].model_dump(mode="json"))
        structure = read.payloads["harness.revit_structure/1"].model_dump(mode="json")
        assert structure["elements"]
        for row in structure["elements"]:
            assert row["unique_id"]
            assert isinstance(row["element_id"], int)
            assert row["element_id"] != 0
        status = read.payloads["harness.revit_status/1"].model_dump(mode="json")
        assert status["file_base_name"] == "state"
        assert status["catalog_version"] == "test-catalog"
        assert re.fullmatch("[0-9a-f]{64}", read.fingerprint or "")

    _run(tmp_path, config, body)


def test_truncation_by_level(tmp_path: Path) -> None:
    """AC9: a truncated list_elements is re-read per level; a level still truncated raises LIMIT_EXCEEDED."""
    control = tmp_path / "control.json"
    seed = _seed_complete()
    seed["elements"] = [
        _complete_column(element_id=10_000 + n, unique_id=f"col-{10_000 + n}") for n in range(LIST_CAP + 1)
    ]
    seed["types"] = [
        {
            "type_id": 2001,
            "family": _FAMILY,
            "name": "C300x300",
            "family_id": 1001,
            "category": "OST_StructuralColumns",
            "parameters": [_length_param("b", _B_FT), _length_param("h", _H_FT)],
            "instance_ids": [10_000 + n for n in range(LIST_CAP + 1)],
        }
    ]
    config = _revit_config(tmp_path, control, seed=seed)

    async def body(manager: ServerManager) -> None:
        reader = _reader(manager, config)
        with pytest.raises(ContractError) as refused:
            await reader.read(bound_path=_BOUND)
        assert refused.value.detail.code is ErrorCode.LIMIT_EXCEEDED
        assert "level" in refused.value.detail.message.lower() or "truncated" in refused.value.detail.message.lower()

    _run(tmp_path, config, body)


def test_response_too_large_halves(tmp_path: Path) -> None:
    """AC9: RESPONSE_TOO_LARGE on a details chunk halves the chunk and retries until it fits."""
    control = tmp_path / "control.json"
    faults = [{"fault": "response_too_large", "tool": "revit_get_element_details"}]
    seed = _seed_complete()
    seed["elements"] = [
        _complete_column(element_id=3001, unique_id="col-3001"),
        _complete_column(element_id=3003, unique_id="col-3003"),
    ]
    seed["types"][0]["instance_ids"] = [3001, 3003]
    config = _revit_config(tmp_path, control, seed=seed, faults=faults)

    async def body(manager: ServerManager) -> None:
        reader = _reader(manager, config)
        read = await reader.read(bound_path=_BOUND)
        structure = read.payloads["harness.revit_structure/1"].model_dump(mode="json")
        ids = {row["element_id"] for row in structure["elements"]}
        assert {3001, 3003}.issubset(ids)
        data = json.loads(control.read_text(encoding="utf-8"))
        detail_calls = [c for c in data.get("calls", []) if c.get("tool") == "revit_get_element_details"]
        assert len(detail_calls) >= 2
        sizes = [len(c["args"].get("elementIds") or []) for c in detail_calls]
        assert sizes[0] > sizes[1]

    _run(tmp_path, config, body)


def test_neutral_kinds_complete_rows_only(tmp_path: Path) -> None:
    """AC11: complete role-map rows enter frame_placements/sections; incomplete stay with info issues."""
    control = tmp_path / "control.json"
    seed = _seed_complete()
    no_rotation = _complete_column(element_id=3005, unique_id="col-3005")
    no_rotation["parameters"] = [_length_param("b", _B_FT)]
    seed["elements"].append(no_rotation)
    seed["types"][0]["instance_ids"] = [3001, 3005]
    seed["types"].append(
        {
            "type_id": 2003,
            "family": _FAMILY,
            "name": "C-partial",
            "family_id": 1001,
            "category": "OST_StructuralColumns",
            "parameters": [_length_param("b", _B_FT)],
            "instance_ids": [],
        }
    )
    config = _revit_config(tmp_path, control, seed=seed)

    async def body(manager: ServerManager) -> None:
        reader = _reader(manager, config)
        read = await reader.read(bound_path=_BOUND)
        frames = read.payloads["model.frame_placements/1"]
        sections = read.payloads["model.sections/1"]
        NEUTRAL_KINDS["model.frame_placements/1"].model_validate(frames.model_dump(mode="json"))
        NEUTRAL_KINDS["model.sections/1"].model_validate(sections.model_dump(mode="json"))
        frame_ids = {row["id"] for row in frames.model_dump(mode="json")["frames"]}
        assert "col-3001" in frame_ids
        assert "col-3005" not in frame_ids
        structure = read.payloads["harness.revit_structure/1"].model_dump(mode="json")
        assert "col-3005" in {row["unique_id"] for row in structure["elements"]}
        codes = {issue.code for issue in read.issues}
        assert "ROTATION_UNAVAILABLE" in codes
        assert "SECTION_ROLES_UNMAPPED" in codes
        section_names = {row["name"] for row in sections.model_dump(mode="json")["frame_sections"]}
        assert any("C300x300" in name for name in section_names)
        complete = next(row for row in frames.model_dump(mode="json")["frames"] if row["id"] == "col-3001")
        assert complete["kind"] == "column"
        assert complete["section"] == f"{_FAMILY}: C300x300"
        assert complete["i_joint"] is None and complete["j_joint"] is None
        assert complete["rotation_deg"] == 0.0
        by_id = {row["unique_id"]: row for row in structure["elements"]}
        b_param = by_id["col-3001"]["parameters"].get("section_b")
        assert b_param is not None
        assert Quantity.model_validate(b_param).value == pytest.approx(_B_MM)

    _run(tmp_path, config, body)
