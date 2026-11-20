"""IDEA working copy, path guards and route preconditions (plan 0014 T6; spec 0014 AC4, AC5, section 4.10)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ModelStateStore, Workspace
from fakes.sasaah_idea.test_server import make_ideacon

from eng_harness.adapters._identity import IdentityStore
from eng_harness.adapters.idea import idea_allowlist
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity
from eng_harness.servers._session import reply_body

_START = 1_700_000_000_000


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _idea_config(tmp_path: Path, control: Path, *, route: str = "native") -> ServersConfig:
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


def _seed(control: Path, **seed: Any) -> None:
    data = json.loads(control.read_text(encoding="utf-8")) if control.exists() else {"faults": [], "seed": {}}
    data["seed"] = {**data.get("seed", {}), **seed}
    control.write_text(json.dumps(data), encoding="utf-8")


def _fault(control: Path, fault: str, *, tool: str) -> None:
    data = json.loads(control.read_text(encoding="utf-8")) if control.exists() else {"faults": [], "seed": {}}
    data.setdefault("faults", []).append({"fault": fault, "tool": tool})
    control.write_text(json.dumps(data), encoding="utf-8")


def _port(
    tmp_path: Path,
    manager: ServerManager,
    *,
    route: str,
    files: dict[str, Path],
    service_url: str | None = None,
) -> Any:
    from eng_harness.adapters.idea._session_ops import IdeaHostPort

    clock = FixedClock(_START)
    ids = SeededIdSource(b"idea-session", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    engine = ProcessIdentity(os.getpid(), "t0", "python")
    locks = HostLocks(tmp_path / "locks", run_id="b305", engine=engine, clock=clock)
    return IdeaHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids),
        sessions=manager,
        locks=locks,
        clock=clock,
        ids=ids,
        run_dir=tmp_path / "run",
        files=files,
        server="idea",
        host_key="idea",
        route=route,
        service_url=service_url,
    )


def test_working_copy_hash(tmp_path: Path) -> None:
    """AC4: working_copy copies a .ideaCon into the run folder with equal hashes and derived_from lineage; no host launch."""
    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="native")
    original = make_ideacon(tmp_path / "joint.ideaCon")
    run_dir = tmp_path / "run"
    copies = run_dir / "copies"

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            before_calls = len(json.loads(control.read_text(encoding="utf-8")).get("calls", []))
            port = _port(tmp_path, manager, route="native", files={"m": original})
            copy_key = await port.working_copy("m", copies)
            assert copy_key == "m@copy"
            files = port.model_files(copy_key)
            assert len(files) == 1
            assert files[0].suffix == ".ideaCon"
            assert files[0].resolve().is_relative_to(run_dir.resolve())
            assert _sha(files[0]) == _sha(original)
            resolved = port.identity_store.resolve(files[0])
            assert resolved.derived_from is not None
            # No host instance is launched (spec 0014 section 4.10 working_copy).
            assert await port.started_instances("idea") == []
            held = await port.locate(copy_key)
            assert held is not None
            assert held.pid is None
            after = json.loads(control.read_text(encoding="utf-8")).get("calls", [])
            assert len(after) == before_calls

    anyio.run(body)


def test_out_path_new_and_distinct(tmp_path: Path) -> None:
    """AC4: out_path is always a new file in the run folder and distinct from path."""
    from eng_harness.adapters.idea._session_ops import new_out_path, require_inside_run
    from eng_harness.adapters.idea._tools import build_native_set_loads_args

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    path = run_dir / "a.ideaCon"
    path.write_text("{}", encoding="utf-8")
    out = new_out_path(path, run_dir)
    assert out.resolve() != path.resolve()
    assert out.resolve().is_relative_to(run_dir.resolve())
    assert not out.exists()
    require_inside_run(out, run_dir)
    # No tool that overwrites its input is served: the argument builder refuses path == out_path.
    with pytest.raises(ContractError) as same:
        build_native_set_loads_args(
            path=str(path),
            loads=[],
            connection_id="C1",
            out_path=str(path),
            approved=True,
        )
    assert same.value.code is ErrorCode.INVALID_ARGUMENT
    assert same.value.field == "out_path"


def test_no_path_outside_run_folder(tmp_path: Path) -> None:
    """AC4: every path passed to the server must lie inside the run folder."""
    from eng_harness.adapters.idea._session_ops import require_inside_run

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    inside = run_dir / "copies" / "joint.ideaCon"
    inside.parent.mkdir(parents=True)
    inside.write_text("{}", encoding="utf-8")
    assert require_inside_run(inside, run_dir) == inside.resolve()
    outside = tmp_path / "elsewhere" / "joint.ideaCon"
    outside.parent.mkdir()
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ContractError) as caught:
        require_inside_run(outside, run_dir)
    assert caught.value.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.field == "path"


def test_rest_route_requires_live_project(tmp_path: Path) -> None:
    """AC5: route rest raises HOST_NOT_CONNECTED when open is not backend=rest with live_project=true; project closed."""
    control = tmp_path / "control.json"
    _fault(control, "live_create_fallback", tool="idea_open_project")
    config = _idea_config(tmp_path, control, route="rest")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    run_dir = tmp_path / "run"

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            port = _port(
                tmp_path,
                manager,
                route="rest",
                files={"m": model},
                service_url="http://127.0.0.1:9",
            )
            copy_key = await port.working_copy("m", run_dir / "copies")
            with pytest.raises(ContractError) as caught:
                await port.ensure_route_ready(copy_key)
            assert caught.value.code is ErrorCode.HOST_NOT_CONNECTED
            # Project must be closed after the failed precondition (AC5).
            listed = await manager.call("idea", "main", "idea_list_connections", {}, CallEffect.READ)
            assert listed.is_error is True

    anyio.run(body)


def test_service_unreachable_host_not_connected(tmp_path: Path) -> None:
    """AC5: route rest raises HOST_NOT_CONNECTED when idea_status.service.reachable is false."""
    control = tmp_path / "control.json"
    _seed(control, service={"reachable": False, "service_version": None})
    config = _idea_config(tmp_path, control, route="rest")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    run_dir = tmp_path / "run"

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            port = _port(
                tmp_path,
                manager,
                route="rest",
                files={"m": model},
                service_url="http://127.0.0.1:9",
            )
            copy_key = await port.working_copy("m", run_dir / "copies")
            with pytest.raises(ContractError) as caught:
                await port.ensure_route_ready(copy_key)
            assert caught.value.code is ErrorCode.HOST_NOT_CONNECTED
            status = await manager.call("idea", "main", "idea_status", {}, CallEffect.READ)
            body_json = reply_body(status)
            assert body_json is not None
            assert body_json["service"]["reachable"] is False

    anyio.run(body)


def test_native_route_requires_hidden_calculator(tmp_path: Path) -> None:
    """AC5: route native raises HOST_NOT_CONNECTED when no installed version reports a hidden calculator, or path is not .ideaCon."""
    control = tmp_path / "control.json"
    _seed(
        control,
        installed=[{"version": "24.1", "has_rest_api": True, "hidden_calculator": False}],
    )
    config = _idea_config(tmp_path, control, route="native")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    run_dir = tmp_path / "run"

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            port = _port(tmp_path, manager, route="native", files={"m": model})
            copy_key = await port.working_copy("m", run_dir / "copies")
            with pytest.raises(ContractError) as caught:
                await port.ensure_route_ready(copy_key)
            assert caught.value.code is ErrorCode.HOST_NOT_CONNECTED

            # Non-.ideaCon working copy is refused the same way.
            other = tmp_path / "not-idea.txt"
            other.write_text("x", encoding="utf-8")
            port_bad = _port(tmp_path, manager, route="native", files={"x": other})
            bad_key = await port_bad.working_copy("x", run_dir / "copies-bad")
            with pytest.raises(ContractError) as bad:
                await port_bad.ensure_route_ready(bad_key)
            assert bad.value.code is ErrorCode.HOST_NOT_CONNECTED

    anyio.run(body)
