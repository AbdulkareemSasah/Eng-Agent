"""IDEA adapter gap entries (plan 0014 T6; spec 0014 AC6, section 4.4, IG-1, IG-3, IG-4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import anyio
import pytest
from helpers.idea_classification import GAP

from eng_harness.errors import HarnessCode, NotImplementedGap
from eng_harness.servers import ServerManager, ServersConfig

# Spec 0014 section 4.4 Gap (20): creation is IG-4; idea_set_loads is IG-1 and IG-3; other gap tools are IG-3.
_CREATE = frozenset({"idea_create_project", "idea_create_project_from_template"})
_EDIT = GAP - _CREATE - {"idea_set_loads"}


def _idea_config(tmp_path: Path, control: Path, *, route: str = "native") -> ServersConfig:
    import hashlib

    from eng_harness.adapters.idea import idea_allowlist

    fake = Path(__file__).resolve().parents[2] / "fakes" / "sasaah_idea" / "server.py"
    if not control.exists():
        control.write_text(json.dumps({"faults": [], "seed": {}}), encoding="utf-8")
    wrapper = tmp_path / "sasaah-idea-mcp"
    wrapper.write_text(
        f'#!/bin/sh\nexport SASAAH_IDEA_FAKE_CONTROL="{control}"\nexec "{sys.executable}" "{fake}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    exe = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    allowlist = idea_allowlist()
    section: dict[str, Any] = {
        "adapter": "sasaah-idea-mcp",
        "command": str(wrapper),
        "args": ["--disable-script"],
        "route": route,
        "audit_log": False,
        "client_grace_s": 2,
        "shutdown_grace_s": 5,
        "max_restarts_per_run": 1,
        "build": {"sasaah_commit": allowlist.sasaah_commit, "exe_sha256": exe},
        "host_key": "idea",
        "roles": {"main": {"classes": ["session", "call", "long"], "call_timeout_s": 30}},
    }
    if route == "rest":
        section["service_url"] = "http://127.0.0.1:9"
    return ServersConfig.model_validate({"servers": {"idea": section}})


def _calls(control: Path) -> list[dict[str, Any]]:
    data = json.loads(control.read_text(encoding="utf-8"))
    calls = data.get("calls", [])
    assert isinstance(calls, list)
    return calls


def test_create_project_gap(tmp_path: Path) -> None:
    """AC6: idea_create_project and idea_create_project_from_template raise NotImplementedGap IG-4; nothing is sent."""
    from eng_harness.adapters.idea._gaps import create_project, raise_gap, refuse_tool

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)

    async def body() -> None:
        async with ServerManager(config, tmp_path / "run") as manager:
            for call in (
                create_project,
                lambda: refuse_tool("idea_create_project"),
                lambda: refuse_tool("idea_create_project_from_template"),
                lambda: raise_gap("IG-4"),
            ):
                with pytest.raises(NotImplementedGap) as caught:
                    call()
                assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
                assert "IG-4" in caught.value.evidence
            assert manager.session_epoch("idea") == 0

    anyio.run(body)
    assert _calls(control) == []


def test_set_loads_gap(tmp_path: Path) -> None:
    """AC6: idea_set_loads raises NotImplementedGap with IG-1 and IG-3; nothing is sent."""
    from eng_harness.adapters.idea._gaps import refuse_tool, set_loads

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)

    async def body() -> None:
        async with ServerManager(config, tmp_path / "run") as manager:
            for call in (set_loads, lambda: refuse_tool("idea_set_loads")):
                with pytest.raises(NotImplementedGap) as caught:
                    call()
                assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
                assert "IG-1" in caught.value.evidence
                assert "IG-3" in caught.value.evidence
            assert manager.session_epoch("idea") == 0

    anyio.run(body)
    assert _calls(control) == []


@pytest.mark.parametrize("tool", sorted(_EDIT))
def test_project_model_edits_gap(tool: str, tmp_path: Path) -> None:
    """AC6: each in-memory project-model edit tool raises NotImplementedGap IG-3; nothing is sent."""
    from eng_harness.adapters.idea._gaps import IDEA_GAPS, refuse_tool

    assert "IG-3" in IDEA_GAPS
    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)

    async def body() -> None:
        async with ServerManager(config, tmp_path / "run") as manager:
            with pytest.raises(NotImplementedGap) as caught:
                refuse_tool(tool)
            assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
            assert caught.value.evidence == ("IG-3",)
            assert manager.session_epoch("idea") == 0

    anyio.run(body)
    assert _calls(control) == []
