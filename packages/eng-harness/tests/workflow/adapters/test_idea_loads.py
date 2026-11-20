"""IDEA set_loads write, read-back and check_model issues (plan 0014 T7; spec 0014 AC10, section 4.7, 4.10)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import HostInfo, Provenance
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.issues import Severity
from eng_contract.store import LocationClass, ModelStateStore, ResultStore, Workspace
from fakes.sasaah_idea.test_server import make_ideacon

from eng_harness.adapters._identity import IdentityStore
from eng_harness.adapters.idea import idea_allowlist
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity
from eng_harness.servers._session import reply_body

_START = 1_700_000_000_000
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "idea"
_SYNTHETIC_MAP = _FIXTURES / "load_map_synthetic.toml"
_MODEL = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"
# Basis field checks.readback_relative_tolerance_ratio (spec 0014 section 5); synthetic test value, not engineering.
_TOLERANCE = 1e-9


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
    return ServersConfig.model_validate({"servers": {"idea": section}})


def _seed(control: Path, **seed: Any) -> None:
    data = json.loads(control.read_text(encoding="utf-8")) if control.exists() else {"faults": [], "seed": {}}
    data["seed"] = {**data.get("seed", {}), **seed}
    control.write_text(json.dumps(data), encoding="utf-8")


def _store(tmp_path: Path) -> ResultStore:
    from eng_harness._kinds import HARNESS_KINDS

    clock = FixedClock(_START)
    ids = SeededIdSource(b"idea-loads-wf", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS, ids, clock)


def _put_row(store: ResultStore, *, p_kn: float = 25.0) -> str:
    from typing import cast

    from pydantic import JsonValue

    payload = cast(
        dict[str, JsonValue],
        {
            "sign_convention": "host_local/1",
            "rows": [
                {
                    "member": "B1",
                    "case": {"case": "DEAD", "case_type": "load_case"},
                    "end": "i",
                    "station_mm": 0.0,
                    "P_kN": p_kn,
                    "V2_kN": 0.0,
                    "V3_kN": 0.0,
                    "T_kNm": 0.0,
                    "M2_kNm": 0.0,
                    "M3_kNm": 0.0,
                }
            ],
        },
    )
    prov = Provenance(
        tool="harness",
        tool_version="1",
        host=HostInfo(program="ETABS", version="22", model_id=_MODEL, model_revision=1),
        inputs={},
        started_at="2026-01-01T00:00:00.000Z",
        duration_ms=0,
    )
    return store.put("forces.member_end/1", payload, prov).result_id


def _plan(store: ResultStore, path: Path, *, p_kn: float = 25.0) -> Any:
    from eng_harness.adapters.idea import _loads as loads

    rid = _put_row(store, p_kn=p_kn)
    return loads.LoadPlan.model_validate(
        {
            "path": str(path),
            "connection": "CON1",
            "member_map": {"B1": [{"beam_segment_id": 1, "position_host": 0.0}]},
            "effects": [
                {
                    "name": "LE1",
                    "entries": [
                        {
                            "beam_segment_id": 1,
                            "position_host": 0.0,
                            "row": {"$ref": f"{rid}#/rows/0"},
                        }
                    ],
                }
            ],
        }
    )


def _session(tmp_path: Path, manager: ServerManager, files: dict[str, Path]) -> Any:
    from eng_harness.adapters.idea._session_ops import IdeaHostPort

    clock = FixedClock(_START)
    ids = SeededIdSource(b"idea-loads-port", clock)
    workspace = Workspace(root=tmp_path / "ws-port", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    engine = ProcessIdentity(os.getpid(), "t0", "python")
    locks = HostLocks(tmp_path / "locks", run_id="b306", engine=engine, clock=clock)
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
        route="native",
        service_url=None,
    )


def test_set_loads_writes_new_file(tmp_path: Path) -> None:
    """AC10: idea_native_set_loads writes a new out_path file; the model rebinds; old file kept."""
    from eng_harness.adapters.idea import _loads as loads

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)
    original = make_ideacon(tmp_path / "joint.ideaCon")
    run_dir = tmp_path / "run"
    store = _store(tmp_path)

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            port = _session(tmp_path, manager, files={"m": original})
            copy_key = await port.working_copy("m", run_dir / "copies")
            path = port.model_files(copy_key)[0]
            old_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            result = await loads.set_loads(
                sessions=manager,
                server="idea",
                role="main",
                plan=_plan(store, path),
                load_map=loads.load_map_file(_SYNTHETIC_MAP),
                source=store,
                current_revision=lambda _: 1,
                run_dir=run_dir,
                readback_relative_tolerance_ratio=_TOLERANCE,
                approved=True,
            )
            assert result.out_path.exists()
            assert result.out_path.resolve() != path.resolve()
            assert path.exists()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == old_sha
            assert result.out_path.suffix == ".ideaCon"
            reread = await manager.call(
                "idea",
                "main",
                "idea_native_get_loads",
                {"path": str(result.out_path), "connection_id": "CON1"},
                CallEffect.READ,
            )
            body = reply_body(reread)
            assert body is not None
            assert body["loads"][0]["forcesOnSegments"][0]["n"] == 25000.0

    anyio.run(body)


def test_readback_mismatch_detected() -> None:
    """AC10: a read-back that differs beyond the basis tolerance is READBACK_MISMATCH (error)."""
    import copy

    from eng_harness.adapters.idea import _checks as checks

    requested = [
        {
            "id": 1,
            "name": "LE1",
            "checkEquilibrium": True,
            "forcesOnSegments": [
                {
                    "beamSegmentId": 1,
                    "position": 0.0,
                    "n": 25000.0,
                    "qy": 0.0,
                    "qz": 0.0,
                    "mx": 0.0,
                    "my": 0.0,
                    "mz": 0.0,
                }
            ],
            "forcesPercentageOnSegments": [],
        }
    ]
    got: list[dict[str, Any]] = copy.deepcopy(requested)
    segments = got[0]["forcesOnSegments"]
    assert isinstance(segments, list)
    first = segments[0]
    assert isinstance(first, dict)
    first["n"] = 25001.0
    issues = checks.compare_loads_readback(
        requested=requested,
        got=got,
        tolerance_ratio=_TOLERANCE,
        connection="CON1",
    )
    assert any(i.code == "READBACK_MISMATCH" and i.severity is Severity.ERROR for i in issues)


def test_zero_effect_dropped_warning(tmp_path: Path) -> None:
    """AC10: a reply with non-empty dropped_zero becomes LOAD_EFFECT_ZERO_DROPPED naming the effects."""
    from eng_harness.adapters.idea import _checks as checks
    from eng_harness.adapters.idea import _loads as loads

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)
    original = make_ideacon(tmp_path / "joint.ideaCon")
    run_dir = tmp_path / "run"

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            port = _session(tmp_path, manager, files={"m": original})
            copy_key = await port.working_copy("m", run_dir / "copies")
            path = port.model_files(copy_key)[0]
            # Read current, append an all-zero effect, write; fake drops it and reports dropped_zero.
            got = await manager.call(
                "idea",
                "main",
                "idea_native_get_loads",
                {"path": str(path), "connection_id": "CON1"},
                CallEffect.READ,
            )
            current = reply_body(got)
            assert current is not None
            zero_effect = {
                "id": 99,
                "name": "ZERO",
                "checkEquilibrium": True,
                "forcesOnSegments": [
                    {
                        "beamSegmentId": 1,
                        "position": 0.0,
                        "n": 0.0,
                        "qy": 0.0,
                        "qz": 0.0,
                        "mx": 0.0,
                        "my": 0.0,
                        "mz": 0.0,
                    }
                ],
                "forcesPercentageOnSegments": [],
            }
            new_loads = [*(current["loads"]), zero_effect]
            # Bump the first effect so the write is not all-zero.
            new_loads[0]["forcesOnSegments"][0]["n"] = 25000.0
            from eng_harness.adapters.idea._session_ops import new_out_path
            from eng_harness.adapters.idea._tools import build_native_set_loads_args

            out = new_out_path(path, run_dir)
            args = build_native_set_loads_args(
                path=str(path),
                loads=new_loads,
                connection_id="CON1",
                out_path=str(out),
                approved=True,
            )
            reply = await manager.call("idea", "main", "idea_native_set_loads", args, CallEffect.WRITE)
            body = reply_body(reply)
            assert body is not None
            assert "ZERO" in body.get("dropped_zero", [])
            issues = checks.issues_from_set_loads_reply(body, connection="CON1")
            assert any(
                i.code == "LOAD_EFFECT_ZERO_DROPPED" and i.severity is Severity.WARNING and "ZERO" in i.message
                for i in issues
            )
            # Shipped unconfirmed map yields LOADS_UNCONFIRMED_MAP info via check_model helpers.
            info = checks.load_map_status_issue(loads.load_shipped_map(), connection="CON1")
            assert info is not None
            assert info.code == "LOADS_UNCONFIRMED_MAP"
            assert info.severity is Severity.INFO

    anyio.run(body)


def test_all_zero_loads_host_error(tmp_path: Path) -> None:
    """AC10: a plan whose every effect is zero is HOST_ERROR (idea_error) with no new file."""
    from eng_harness.adapters.idea import _loads as loads

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)
    original = make_ideacon(tmp_path / "joint.ideaCon")
    run_dir = tmp_path / "run"
    store = _store(tmp_path)

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            port = _session(tmp_path, manager, files={"m": original})
            copy_key = await port.working_copy("m", run_dir / "copies")
            path = port.model_files(copy_key)[0]
            before = list((run_dir).rglob("*.ideaCon"))
            with pytest.raises(ContractError) as caught:
                await loads.set_loads(
                    sessions=manager,
                    server="idea",
                    role="main",
                    plan=_plan(store, path, p_kn=0.0),
                    load_map=loads.load_map_file(_SYNTHETIC_MAP),
                    source=store,
                    current_revision=lambda _: 1,
                    run_dir=run_dir,
                    readback_relative_tolerance_ratio=_TOLERANCE,
                    approved=True,
                )
            assert caught.value.detail.code is ErrorCode.HOST_ERROR
            assert (caught.value.detail.host_code or "").lower() in {"idea_error", "idea_error".upper()} or (
                caught.value.detail.host_code == "idea_error"
            )
            after = list(run_dir.rglob("*.ideaCon"))
            # No additional ideaCon beyond the working copy.
            assert len(after) == len(before)

    anyio.run(body)
