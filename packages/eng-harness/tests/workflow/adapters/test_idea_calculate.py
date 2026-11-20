"""IDEA calculation on both routes, stub refusal and host-verdict reads (plan 0014 T8; spec 0014 AC11 to AC13)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from eng_contract.verdicts import VerdictStatus
from fakes.sasaah_idea.test_server import make_ideacon

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters.idea import idea_allowlist
from eng_harness.kinds.idea import IDEA_KINDS
from eng_harness.servers import CallEffect, ServerManager, ServersConfig

_START = 1_700_000_000_000
_DESIGN_CODE = "AISC 360-16"  # design basis field connection.design_code (spec 0014 AC15); test label only


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
        section["service_url"] = "http://127.0.0.1:9/"
    return ServersConfig.model_validate({"servers": {"idea": section}})


def _fault(control: Path, fault: str, *, tool: str, **extra: Any) -> None:
    data = json.loads(control.read_text(encoding="utf-8")) if control.exists() else {"faults": [], "seed": {}}
    data.setdefault("faults", []).append({"fault": fault, "tool": tool, **extra})
    control.write_text(json.dumps(data), encoding="utf-8")


def _store(tmp_path: Path) -> ResultStore:
    clock = FixedClock(_START)
    ids = SeededIdSource(b"idea-calc-wf", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS.extend(IDEA_KINDS), ids, clock)


def test_stub_refused_rest(tmp_path: Path) -> None:
    """AC11: a stub reply of idea_calculate fails HOST_ERROR / OFFLINE_STUB; no verdict is produced."""
    from eng_harness.adapters.idea import _calculate as calculate

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="rest")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    store = _store(tmp_path)

    async def body() -> None:
        async with ServerManager(config, tmp_path / "run") as manager:
            opened = await manager.call("idea", "main", "idea_open_project", {"path": str(model)}, CallEffect.WRITE)
            assert opened.is_error is False
            _fault(control, "service_stopped", tool="idea_calculate")
            with pytest.raises(ContractError) as raised:
                await calculate.calculate_rest(
                    sessions=manager,
                    server="idea",
                    role="main",
                    connection_ids=[1],
                    design_code=_DESIGN_CODE,
                    load_map_confirmed=False,
                    approved=True,
                    store=store,
                    ids=SeededIdSource(b"idea-calc-stub", FixedClock(_START)),
                )
            assert raised.value.detail.code is ErrorCode.HOST_ERROR
            assert raised.value.detail.host_code == "OFFLINE_STUB"

    anyio.run(body)


def test_service_stopped_preflight(tmp_path: Path) -> None:
    """AC11: idea_status.service.reachable false before the call → HOST_NOT_CONNECTED without calling calculate."""
    from eng_harness.adapters.idea import _calculate as calculate

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="rest")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    store = _store(tmp_path)
    call_log: list[str] = []

    class _LoggingSessions:
        def __init__(self, inner: ServerManager) -> None:
            self._inner = inner

        async def call(self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect) -> Any:
            call_log.append(tool)
            return await self._inner.call(server, role, tool, args, effect)

    async def body() -> None:
        async with ServerManager(config, tmp_path / "run") as manager:
            opened = await manager.call("idea", "main", "idea_open_project", {"path": str(model)}, CallEffect.WRITE)
            assert opened.is_error is False
            _fault(control, "service_stopped", tool="idea_status")
            sessions = _LoggingSessions(manager)
            with pytest.raises(ContractError) as raised:
                await calculate.calculate_rest(
                    sessions=sessions,
                    server="idea",
                    role="main",
                    connection_ids=[1],
                    design_code=_DESIGN_CODE,
                    load_map_confirmed=False,
                    approved=True,
                    store=store,
                    ids=SeededIdSource(b"idea-calc-pre", FixedClock(_START)),
                )
            assert raised.value.detail.code is ErrorCode.HOST_NOT_CONNECTED
            assert "idea_calculate" not in call_log
            assert "idea_get_check_results" not in call_log
            assert "idea_status" in call_log

    anyio.run(body)


def test_live_create_fallback_offline_refused(tmp_path: Path) -> None:
    """AC11: live_create_fallback yields an offline stub; the adapter refuses it (OFFLINE_STUB)."""
    from eng_harness.adapters.idea import _calculate as calculate

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="rest")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    store = _store(tmp_path)

    async def body() -> None:
        async with ServerManager(config, tmp_path / "run") as manager:
            _fault(control, "live_create_fallback", tool="idea_open_project")
            opened = await manager.call("idea", "main", "idea_open_project", {"path": str(model)}, CallEffect.WRITE)
            assert opened.is_error is False
            with pytest.raises(ContractError) as raised:
                await calculate.calculate_rest(
                    sessions=manager,
                    server="idea",
                    role="main",
                    connection_ids=[1],
                    design_code=_DESIGN_CODE,
                    load_map_confirmed=False,
                    approved=True,
                    store=store,
                    ids=SeededIdSource(b"idea-calc-live", FixedClock(_START)),
                )
            assert raised.value.detail.code is ErrorCode.HOST_ERROR
            assert raised.value.detail.host_code == "OFFLINE_STUB"

    anyio.run(body)


def test_native_checks_to_verdicts(tmp_path: Path) -> None:
    """AC12: idea_native_calculate (save false) maps each check row to host verdicts."""
    from eng_harness.adapters.idea import _calculate as calculate

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="native")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    store = _store(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # Working copy inside the run folder (native calculate takes a path).
    work = run_dir / "joint.ideaCon"
    work.write_bytes(model.read_bytes())

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            result = await calculate.calculate_native(
                sessions=manager,
                server="idea",
                role="main",
                path=work,
                connection_id="CON1",
                design_code=_DESIGN_CODE,
                load_map_confirmed=False,
                store=store,
                ids=SeededIdSource(b"idea-calc-nat", FixedClock(_START)),
            )
            assert result.raw.route == "native"
            assert result.raw.offline_stub is False
            assert result.verdicts.verdicts
            assert all(v.source.value == "host" for v in result.verdicts.verdicts)
            # Spec 0014 AC13: ratio = check_value / 100; host pass with ratio <= 1.0 stays PASS.
            by_id = {v.check_id: v for v in result.verdicts.verdicts}
            for connection in result.raw.connections:
                for check in connection.checks:
                    from eng_harness.adapters.idea._verdicts import slug

                    verdict = by_id[f"idea:{slug(check.name)}"]
                    assert verdict.ratio == pytest.approx(check.check_value / 100.0)
                    if check.check_status and not check.skipped and check.check_value <= 100.0:
                        assert verdict.status is VerdictStatus.PASS
            assert result.verdict_envelope.kind == "verdicts.set/1"
            assert result.raw_envelope.kind == "harness.idea_check_raw/1"

    anyio.run(body)


def test_native_errors_are_error_verdicts(tmp_path: Path) -> None:
    """AC12: a non-empty connection errors list → one idea:connection verdict status ERROR with host text."""
    from eng_harness.adapters.idea import _calculate as calculate

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="native")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    store = _store(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    work = run_dir / "joint.ideaCon"
    work.write_bytes(model.read_bytes())

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            _fault(control, "errors_in_reply", tool="idea_native_calculate")
            result = await calculate.calculate_native(
                sessions=manager,
                server="idea",
                role="main",
                path=work,
                connection_id=None,
                design_code=_DESIGN_CODE,
                load_map_confirmed=False,
                store=store,
                ids=SeededIdSource(b"idea-calc-err", FixedClock(_START)),
            )
            errors = [v for v in result.verdicts.verdicts if v.check_id == "idea:connection"]
            assert len(errors) == 1
            assert errors[0].status is VerdictStatus.ERROR
            assert any("singular" in a.lower() or "cbfem" in a.lower() for a in errors[0].assumptions)
            assert all(len(a) <= 500 for a in errors[0].assumptions)

    anyio.run(body)


def test_unexpected_shape_host_error(tmp_path: Path) -> None:
    """AC12: an unexpected reply shape is HOST_ERROR with host_code UNEXPECTED_REPLY."""
    from eng_harness.adapters.idea import _calculate as calculate

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="native")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    store = _store(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    work = run_dir / "joint.ideaCon"
    work.write_bytes(model.read_bytes())

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            _fault(control, "unexpected_shape", tool="idea_native_calculate")
            with pytest.raises(ContractError) as raised:
                await calculate.calculate_native(
                    sessions=manager,
                    server="idea",
                    role="main",
                    path=work,
                    connection_id=None,
                    design_code=_DESIGN_CODE,
                    load_map_confirmed=False,
                    store=store,
                    ids=SeededIdSource(b"idea-calc-shape", FixedClock(_START)),
                )
            assert raised.value.detail.code is ErrorCode.HOST_ERROR
            assert raised.value.detail.host_code == "UNEXPECTED_REPLY"

    anyio.run(body)


def test_zero_utilization_true_needs_engineer(tmp_path: Path) -> None:
    """AC13: fake fault zero_utilization_true → NEEDS_ENGINEER (missing vs real zero cannot be told apart)."""
    from eng_harness.adapters.idea import _calculate as calculate

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="native")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    store = _store(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    work = run_dir / "joint.ideaCon"
    work.write_bytes(model.read_bytes())

    async def body() -> None:
        async with ServerManager(config, run_dir) as manager:
            _fault(control, "zero_utilization_true", tool="idea_native_calculate")
            result = await calculate.calculate_native(
                sessions=manager,
                server="idea",
                role="main",
                path=work,
                connection_id="CON1",
                design_code=_DESIGN_CODE,
                load_map_confirmed=False,
                store=store,
                ids=SeededIdSource(b"idea-calc-zero", FixedClock(_START)),
            )
            zero = [
                v
                for v in result.verdicts.verdicts
                if v.status is VerdictStatus.NEEDS_ENGINEER and v.ratio == pytest.approx(0.0)
            ]
            assert zero
            assert any("exactly zero" in a.lower() or "may be missing" in a.lower() for a in zero[0].assumptions)

    anyio.run(body)
