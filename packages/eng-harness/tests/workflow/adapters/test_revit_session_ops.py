"""Revit session operations: working copy, gaps and engineer-save identity (plan 0011 T11; AC23 to AC25).

The session-ops import is inside each test so a missing module fails the test (ImportError) rather than collection.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode, Precondition, WarningCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ModelStateStore, Workspace

from eng_harness.adapters.revit import revit_allowlist
from eng_harness.errors import HarnessCode, NotImplementedGap
from eng_harness.servers import ServerManager, ServersConfig
from eng_harness.servers._buildcheck import BuildExpectation
from eng_harness.servers._config import ServerConfig
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._launcher import LaunchedProcess, LaunchSpec, PosixLauncher
from eng_harness.servers._procinfo import ProcessIdentity

_FAKE = Path(__file__).resolve().parents[2] / "fakes" / "sasaah_revit" / "server.py"
_PIPE = r"\\.\pipe\sasaah-revit-session"
_START = 1_700_000_000_000
_DESTRUCTIVE = frozenset(
    {
        "revit_set_type_parameter_values",
        "revit_set_element_parameter_values",
        "revit_set_parameter_value_by_guid",
        "revit_change_element_type",
    }
)


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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expectation(role: str) -> BuildExpectation:
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
) -> ServersConfig:
    control.write_text(
        json.dumps({"faults": faults or [], "seed": dict(seed or {})}),
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


def _port(
    tmp_path: Path,
    manager: ServerManager,
    *,
    files: dict[str, Path],
    pipe_name: str = _PIPE,
) -> Any:
    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.revit._session_ops import RevitHostPort

    clock = FixedClock(_START)
    ids = SeededIdSource(b"revit-session", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    engine = ProcessIdentity(os.getpid(), "t0", "python")
    locks = HostLocks(tmp_path / "locks", run_id="b240", engine=engine, clock=clock)
    return RevitHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids),
        sessions=manager,
        locks=locks,
        clock=clock,
        ids=ids,
        run_dir=tmp_path / "run",
        files=files,
        pipe_name=pipe_name,
        server="revit",
        host_key="revit",
    )


def _run(
    tmp_path: Path,
    config: ServersConfig,
    body: Callable[[ServerManager], Any],
) -> None:
    check = {"revit/read": _expectation("read"), "revit/write": _expectation("write")}

    async def scenario() -> None:
        async with ServerManager(config, tmp_path / "run", launcher=RecordingLauncher(), check=check) as manager:
            await body(manager)

    anyio.run(scenario)


def _calls(control: Path) -> list[dict[str, Any]]:
    data = json.loads(control.read_text(encoding="utf-8"))
    calls = data.get("calls", [])
    assert isinstance(calls, list)
    return calls


def test_working_copy(tmp_path: Path) -> None:
    """AC23: working_copy hashes equal, opens the copy, derived_from, reply checks; no discard flag."""
    control = tmp_path / "control.json"
    original = tmp_path / "original.rvt"
    original.write_bytes(b"revit-model-v1")
    config = _revit_config(tmp_path, control, seed={"pipe_name": _PIPE})

    async def body(manager: ServerManager) -> None:
        port = _port(tmp_path, manager, files={"m": original})
        copy_key = await port.working_copy("m", tmp_path / "run" / "copies")
        assert copy_key == "m@copy"
        copies = port.model_files(copy_key)
        assert len(copies) == 1
        assert copies[0].suffix == ".rvt"
        assert _sha(copies[0]) == _sha(original)
        resolved = port.identity_store.resolve(copies[0])
        assert resolved.derived_from is not None
        opens = [c for c in _calls(control) if c.get("tool") == "revit_open_model"]
        assert len(opens) == 1
        args = opens[0]["args"]
        assert args["path"] == str(copies[0])
        assert args.get("activate", True) is True
        assert "allow_discard_unsaved_changes" not in args or args["allow_discard_unsaved_changes"] is False
        held = await port.locate(copy_key)
        assert held is not None
        assert held.pid is None
        assert await port.started_instances("revit") == []

    _run(tmp_path, config, body)


def test_workshared_refused(tmp_path: Path) -> None:
    """AC23: a workshared open_model reply is PRECONDITION_FAILED (model_open) before any write."""
    control = tmp_path / "control.json"
    original = tmp_path / "central.rvt"
    original.write_bytes(b"revit-central-v1")
    config = _revit_config(
        tmp_path,
        control,
        seed={"pipe_name": _PIPE},
        faults=[{"fault": "workshared_open", "tool": "revit_open_model"}],
    )

    async def body(manager: ServerManager) -> None:
        port = _port(tmp_path, manager, files={"m": original})
        with pytest.raises(ContractError) as caught:
            await port.working_copy("m", tmp_path / "run" / "copies")
        assert caught.value.detail.code is ErrorCode.PRECONDITION_FAILED
        assert caught.value.detail.precondition is Precondition.model_open
        writes = [
            c for c in _calls(control) if isinstance(c.get("tool"), str) and str(c["tool"]).startswith("revit_set")
        ]
        assert writes == []

    _run(tmp_path, config, body)


def test_gaps_not_implemented(tmp_path: Path) -> None:
    """AC24: save and restore raise NotImplementedGap (R-G1, R-G2); started_instances empty; close is a no-op."""
    from eng_harness.adapters.revit._session_ops import RevitHostPort
    from eng_harness.ports import SavedModel

    control = tmp_path / "control.json"
    original = tmp_path / "model.rvt"
    original.write_bytes(b"rvt")
    config = _revit_config(tmp_path, control)

    async def body(manager: ServerManager) -> None:
        port = _port(tmp_path, manager, files={"m": original})
        assert isinstance(port, RevitHostPort)
        before = len(_calls(control))
        with pytest.raises(NotImplementedGap) as save_gap:
            await port.save("m", "pre_write")
        assert save_gap.value.code is HarnessCode.NOT_IMPLEMENTED
        assert "R-G1" in save_gap.value.evidence
        with pytest.raises(NotImplementedGap) as restore_gap:
            await port.restore(
                "m",
                SavedModel(
                    model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                    revision=0,
                    fingerprint="fp",
                    file_sha256="a" * 64,
                    file_name="model.rvt",
                ),
            )
        assert restore_gap.value.code is HarnessCode.NOT_IMPLEMENTED
        assert "R-G2" in restore_gap.value.evidence
        assert await port.started_instances("revit") == []
        await port.close_started("revit", [])
        assert len(_calls(control)) == before

    _run(tmp_path, config, body)


def test_engineer_save_registered(tmp_path: Path) -> None:
    """AC25: new hash with the same fingerprint keeps identity and revision; a different fingerprint is outside."""
    from eng_harness.adapters._identity import IdentityStore

    clock = FixedClock(_START)
    ids = SeededIdSource(b"revit-engineer-save", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    store = IdentityStore(workspace=workspace, states=states, ids=ids)
    path = tmp_path / "edited.rvt"
    path.write_bytes(b"revit-v1")
    first = store.resolve(path)
    assert first.revision == 0
    path.write_bytes(b"revit-v2-engineer-saved")
    same = store.register_hash(first.model_id, path, fingerprint="fp-same", previous_fingerprint="fp-same")
    assert same.model_id == first.model_id
    assert same.revision == first.revision
    assert same.warnings == ()
    again = store.resolve(path)
    assert (again.model_id, again.revision, again.warnings) == (first.model_id, first.revision, ())
    path.write_bytes(b"revit-v3-outside")
    outside = store.register_hash(first.model_id, path, fingerprint="fp-other", previous_fingerprint="fp-same")
    assert outside.model_id == first.model_id
    assert outside.revision == first.revision + 1
    assert outside.warnings == (WarningCode.MODEL_CHANGED_OUTSIDE,)
