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
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
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


def _session(tmp_path: Path, manager: Any, files: dict[str, Path], *, store: ResultStore | None = None) -> Any:
    from eng_harness.adapters.idea._session_ops import IdeaHostPort

    clock = FixedClock(_START)
    ids = SeededIdSource(b"idea-loads-port", clock)
    workspace = Workspace(root=tmp_path / "ws-port", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    engine = ProcessIdentity(os.getpid(), "t0", "python")
    locks = HostLocks(tmp_path / "locks", run_id="b306", engine=engine, clock=clock)
    results = store if store is not None else _store(tmp_path / "port-results")
    return IdeaHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids),
        sessions=manager,
        locks=locks,
        clock=clock,
        ids=ids,
        run_dir=tmp_path / "run",
        files=files,
        store=results,
        server="idea",
        host_key="idea",
        route="native",
        service_url=None,
    )


def _issue_codes(envelope: Any) -> list[str]:
    assert isinstance(envelope, SuccessEnvelope)
    data: Any = envelope.data
    assert data is not None
    return [str(item["code"]) for item in data["issues"]]


class _BumpNAfterWrite:
    """After a successful idea_native_set_loads, bump the written file's first `n` so read-back mismatches."""

    def __init__(self, inner: ServerManager) -> None:
        self._inner = inner

    async def call(self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect) -> Any:
        result = await self._inner.call(server, role, tool, args, effect)
        if tool != "idea_native_set_loads" or result.is_error:
            return result
        out = args.get("out_path")
        if not isinstance(out, str):
            return result
        path = Path(out)
        if not path.is_file():
            return result
        data = json.loads(path.read_text(encoding="utf-8"))
        for conn in data.get("connections", []):
            for effect_row in conn.get("loads", []):
                segments = effect_row.get("forcesOnSegments") or []
                if segments:
                    segments[0]["n"] = float(segments[0].get("n", 0.0)) + 1.0
                    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                    return result
        return result


def test_set_loads_writes_new_file(tmp_path: Path) -> None:
    """AC10: idea_native_set_loads writes a new out_path; model rebinds (new revision, new hash); old file kept."""
    from eng_harness.adapters.idea import _loads as loads

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)
    original = make_ideacon(tmp_path / "joint.ideaCon")
    run_dir = tmp_path / "run"
    store = _store(tmp_path)

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            port = _session(tmp_path, manager, files={"m": original}, store=store)
            copy_key = await port.working_copy("m", run_dir / "copies")
            path = port.model_files(copy_key)[0]
            old_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            before = await port.model_state(copy_key, port._bound[copy_key])
            assert before.loaded
            old_revision = before.revision
            old_fingerprint = before.fingerprint
            result = await port.set_loads(
                copy_key,
                plan=_plan(store, path),
                load_map=loads.load_map_file(_SYNTHETIC_MAP),
                source=store,
                readback_relative_tolerance_ratio=_TOLERANCE,
                approved=True,
            )
            assert result.out_path.exists()
            assert result.out_path.resolve() != path.resolve()
            assert path.exists()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == old_sha
            assert result.out_path.suffix == ".ideaCon"
            bound = port.model_files(copy_key)[0]
            assert bound.resolve() == result.out_path.resolve()
            after = await port.model_state(copy_key, port._bound[copy_key])
            assert after.loaded
            assert after.revision is not None and old_revision is not None
            assert after.revision > old_revision
            assert after.fingerprint != old_fingerprint
            assert after.file_sha256 == hashlib.sha256(result.out_path.read_bytes()).hexdigest()
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


def test_readback_mismatch_detected(tmp_path: Path) -> None:
    """AC10: after a mismatching write, check_model returns READBACK_MISMATCH (error)."""
    from eng_harness.adapters.idea import _loads as loads

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)
    original = make_ideacon(tmp_path / "joint.ideaCon")
    run_dir = tmp_path / "run"
    store = _store(tmp_path)

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            port = _session(tmp_path, _BumpNAfterWrite(manager), files={"m": original}, store=store)
            copy_key = await port.working_copy("m", run_dir / "copies")
            path = port.model_files(copy_key)[0]
            await port.set_loads(
                copy_key,
                plan=_plan(store, path),
                load_map=loads.load_map_file(_SYNTHETIC_MAP),
                source=store,
                readback_relative_tolerance_ratio=_TOLERANCE,
                approved=True,
            )
            checked = await port.check_model(copy_key)
            codes = _issue_codes(checked)
            assert "READBACK_MISMATCH" in codes
            data: Any = checked.data
            assert any(
                item["code"] == "READBACK_MISMATCH" and item["severity"] == Severity.ERROR.value for item in data["issues"]
            )

    anyio.run(body)


def test_zero_effect_dropped_warning(tmp_path: Path) -> None:
    """AC10: after a zero-dropped write, check_model returns LOAD_EFFECT_ZERO_DROPPED; unconfirmed map is info."""
    from eng_harness.adapters.idea import _loads as loads

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)
    original = make_ideacon(tmp_path / "joint.ideaCon")
    run_dir = tmp_path / "run"
    store = _store(tmp_path)

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            port = _session(tmp_path, manager, files={"m": original}, store=store)
            copy_key = await port.working_copy("m", run_dir / "copies")
            path = port.model_files(copy_key)[0]
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
            read = await manager.call(
                "idea",
                "main",
                "idea_native_get_loads",
                {"path": str(out), "connection_id": "CON1"},
                CallEffect.READ,
            )
            read_body = reply_body(read)
            assert read_body is not None
            kept = [effect for effect in new_loads if effect.get("name") != "ZERO"]
            port.remember_set_loads(
                copy_key,
                requested=kept,
                got=read_body["loads"],
                dropped_zero=tuple(str(name) for name in body.get("dropped_zero") or []),
                tolerance_ratio=_TOLERANCE,
                connection="CON1",
                load_map_status=loads.load_shipped_map().status,
            )
            port.rebind_to_out_path(copy_key, out)
            checked = await port.check_model(copy_key)
            codes = _issue_codes(checked)
            assert "LOAD_EFFECT_ZERO_DROPPED" in codes
            assert "LOADS_UNCONFIRMED_MAP" in codes
            data: Any = checked.data
            assert any(
                item["code"] == "LOAD_EFFECT_ZERO_DROPPED"
                and item["severity"] == Severity.WARNING.value
                and "ZERO" in item["message"]
                for item in data["issues"]
            )
            assert any(
                item["code"] == "LOADS_UNCONFIRMED_MAP" and item["severity"] == Severity.INFO.value
                for item in data["issues"]
            )

    anyio.run(body)


def test_readback_unavailable_via_check_model(tmp_path: Path) -> None:
    """AC10 / §4.10: check_model returns READBACK_UNAVAILABLE when tolerance or got is missing."""
    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)
    original = make_ideacon(tmp_path / "joint.ideaCon")
    run_dir = tmp_path / "run"
    store = _store(tmp_path)

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            port = _session(tmp_path, manager, files={"m": original}, store=store)
            copy_key = await port.working_copy("m", run_dir / "copies")
            port.remember_set_loads(
                copy_key,
                requested=[{"name": "LE1", "forcesOnSegments": []}],
                got=None,
                dropped_zero=(),
                tolerance_ratio=_TOLERANCE,
                connection="CON1",
                load_map_status="confirmed",
            )
            checked = await port.check_model(copy_key)
            assert "READBACK_UNAVAILABLE" in _issue_codes(checked)
            port.remember_set_loads(
                copy_key,
                requested=[{"name": "LE1", "forcesOnSegments": []}],
                got=[{"name": "LE1", "forcesOnSegments": []}],
                dropped_zero=(),
                tolerance_ratio=None,
                connection="CON1",
                load_map_status="confirmed",
            )
            checked2 = await port.check_model(copy_key)
            assert "READBACK_UNAVAILABLE" in _issue_codes(checked2)

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
            port = _session(tmp_path, manager, files={"m": original}, store=store)
            copy_key = await port.working_copy("m", run_dir / "copies")
            path = port.model_files(copy_key)[0]
            before = list((run_dir).rglob("*.ideaCon"))
            with pytest.raises(ContractError) as caught:
                await port.set_loads(
                    copy_key,
                    plan=_plan(store, path, p_kn=0.0),
                    load_map=loads.load_map_file(_SYNTHETIC_MAP),
                    source=store,
                    readback_relative_tolerance_ratio=_TOLERANCE,
                    approved=True,
                )
            assert caught.value.detail.code is ErrorCode.HOST_ERROR
            assert (caught.value.detail.host_code or "").lower() in {"idea_error", "idea_error".upper()} or (
                caught.value.detail.host_code == "idea_error"
            )
            after = list(run_dir.rglob("*.ideaCon"))
            assert len(after) == len(before)

    anyio.run(body)
