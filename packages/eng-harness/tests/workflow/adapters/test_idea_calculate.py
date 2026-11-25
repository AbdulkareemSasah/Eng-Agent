"""IDEA calculation on both routes, stub refusal and host-verdict reads (plan 0014 T8; spec 0014 AC11 to AC13)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from eng_contract.envelope import HostInfo
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from eng_contract.verdicts import VerdictStatus
from fakes.sasaah_idea.test_server import make_ideacon
from pydantic import JsonValue

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters.idea import idea_allowlist
from eng_harness.adapters.idea._calculate import CalculateProvenance
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


def _provenance(
    *, model_id: str = "mdl_01HF7YAT00361949KDC0CXNRAC", revision: int = 1, tick: int = 1
) -> CalculateProvenance:
    """Caller-supplied clock and host binding (spec 0002 section 4.5.3); build string is a test label."""
    clock = FixedClock(_START, tick)
    return CalculateProvenance(
        clock=clock,
        host=HostInfo(program="idea", version="", model_id=model_id, model_revision=revision),
        tool_version="test-build+deadbeefdead",
    )


def test_stub_refused_rest(tmp_path: Path) -> None:
    """AC11: a stub reply of idea_calculate fails HOST_ERROR / OFFLINE_STUB; no verdict is produced."""
    from eng_harness.adapters.idea import _calculate as calculate

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="rest")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    store = _TrackingStore(_store(tmp_path))

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
                    store=store.as_store(),
                    ids=SeededIdSource(b"idea-calc-stub", FixedClock(_START)),
                    provenance=_provenance(),
                )
            assert raised.value.detail.code is ErrorCode.HOST_ERROR
            assert raised.value.detail.host_code == "OFFLINE_STUB"
            kinds = _kinds_put(store)
            assert "harness.run_output/1" in kinds
            assert "verdicts.set/1" not in kinds

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
                    provenance=_provenance(),
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
                    provenance=_provenance(),
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
                provenance=_provenance(),
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
                provenance=_provenance(),
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
                    provenance=_provenance(),
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
                provenance=_provenance(),
            )
            zero = [
                v
                for v in result.verdicts.verdicts
                if v.status is VerdictStatus.NEEDS_ENGINEER and v.ratio == pytest.approx(0.0)
            ]
            assert zero
            assert any("exactly zero" in a.lower() or "may be missing" in a.lower() for a in zero[0].assumptions)

    anyio.run(body)


def test_rest_calculate_happy_path(tmp_path: Path) -> None:
    """AC11/AC12: open project, calculate_rest succeeds; verdicts present; draft true; offline_stub false."""
    from eng_harness.adapters.idea import _calculate as calculate

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="rest")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    store = _store(tmp_path)

    async def body() -> None:
        async with ServerManager(config, tmp_path / "run") as manager:
            opened = await manager.call("idea", "main", "idea_open_project", {"path": str(model)}, CallEffect.WRITE)
            assert opened.is_error is False
            result = await calculate.calculate_rest(
                sessions=manager,
                server="idea",
                role="main",
                connection_ids=[1],
                design_code=_DESIGN_CODE,
                load_map_confirmed=False,
                approved=True,
                store=store,
                ids=SeededIdSource(b"idea-calc-rest-ok", FixedClock(_START)),
                provenance=_provenance(),
            )
            assert result.raw.route == "rest"
            assert result.raw.offline_stub is False
            assert result.verdicts.verdicts
            assert result.verdicts.draft is True
            assert all(v.source.value == "host" for v in result.verdicts.verdicts)
            assert result.raw_envelope.kind == "harness.idea_check_raw/1"
            assert result.verdict_envelope.kind == "verdicts.set/1"

    anyio.run(body)


def test_get_check_results_after_calculate(tmp_path: Path) -> None:
    """AC11: get_check_results after a successful calculate_rest returns host verdicts (not a stub)."""
    from eng_harness.adapters.idea import _calculate as calculate

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="rest")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    store = _store(tmp_path)

    async def body() -> None:
        async with ServerManager(config, tmp_path / "run") as manager:
            opened = await manager.call("idea", "main", "idea_open_project", {"path": str(model)}, CallEffect.WRITE)
            assert opened.is_error is False
            calc = await calculate.calculate_rest(
                sessions=manager,
                server="idea",
                role="main",
                connection_ids=[1],
                design_code=_DESIGN_CODE,
                load_map_confirmed=False,
                approved=True,
                store=store,
                ids=SeededIdSource(b"idea-calc-then-get", FixedClock(_START)),
                provenance=_provenance(),
            )
            assert calc.raw.offline_stub is False
            result = await calculate.get_check_results(
                sessions=manager,
                server="idea",
                role="main",
                connection_id=1,
                design_code=_DESIGN_CODE,
                load_map_confirmed=False,
                store=store,
                ids=SeededIdSource(b"idea-get-checks", FixedClock(_START)),
                provenance=_provenance(),
            )
            assert result.raw.route == "rest"
            assert result.raw.offline_stub is False
            assert result.verdicts.verdicts
            assert result.verdicts.draft is True
            assert result.raw_envelope.kind == "harness.idea_check_raw/1"
            assert result.verdict_envelope.kind == "verdicts.set/1"

    anyio.run(body)


class _TrackingStore:
    """Wraps ResultStore.put and records kinds (failure-evidence vs verdict probe; no private attrs)."""

    def __init__(self, inner: ResultStore) -> None:
        self._inner = inner
        self.kinds: list[str] = []

    def put(self, kind: str, payload: Any, producer: Any, parents: Any = (), complete: bool = True) -> Any:
        self.kinds.append(kind)
        return self._inner.put(kind, payload, producer, parents=parents, complete=complete)

    def get(self, result_id: str) -> Any:
        return self._inner.get(result_id)

    def as_store(self) -> ResultStore:
        """Present as ResultStore for typed call sites (runtime is the wrapper)."""
        return cast(ResultStore, self)


def _kinds_put(store: _TrackingStore) -> list[str]:
    """Kinds recorded by `_TrackingStore.put` (failure-evidence vs verdict)."""
    return list(store.kinds)


def test_rest_reply_claiming_native_route_refused(tmp_path: Path) -> None:
    """AC11 / 0002 §4.5.5: a rest reply that claims route native is UNEXPECTED_REPLY (stub backend ignored)."""
    from mcp.types import CallToolResult, TextContent

    from eng_harness.adapters.idea import _calculate as calculate

    store = _TrackingStore(_store(tmp_path))
    body = {
        "route": "native",
        "backend": "file",
        "offline_stub": False,
        "connections": [
            {
                "connection_id": 1,
                "name": "CON1",
                "passed": True,
                "calculated": True,
                "checks": [
                    {
                        "name": "Plates",
                        "check_value": 40.0,
                        "check_status": True,
                        "skipped": False,
                        "message": "OK",
                        "load_case_id": None,
                    }
                ],
                "errors": [],
                "warnings": [],
            }
        ],
    }

    class _Sessions:
        async def call(self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect) -> Any:
            if tool == "idea_status":
                return CallToolResult(
                    content=[TextContent(type="text", text='{"service":{"reachable":true,"service_version":"1"}}')],
                    is_error=False,
                )
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(body))], is_error=False)

    async def run() -> None:
        with pytest.raises(ContractError) as raised:
            await calculate.calculate_rest(
                sessions=_Sessions(),
                server="idea",
                role="main",
                connection_ids=[1],
                design_code=_DESIGN_CODE,
                load_map_confirmed=False,
                approved=True,
                store=store.as_store(),
                ids=SeededIdSource(b"idea-calc-route", FixedClock(_START)),
                provenance=_provenance(),
            )
        assert raised.value.detail.code is ErrorCode.HOST_ERROR
        assert raised.value.detail.host_code == "UNEXPECTED_REPLY"
        kinds = _kinds_put(store)
        assert "harness.run_output/1" in kinds
        assert "verdicts.set/1" not in kinds
        assert "harness.idea_check_raw/1" not in kinds

    anyio.run(run)


def test_stub_refused_native_stores_failure_evidence(tmp_path: Path) -> None:
    """AC11: stub through calculate_native stores failure evidence only (not a verdict)."""
    from mcp.types import CallToolResult, TextContent

    from eng_harness.adapters.idea import _calculate as calculate

    store = _TrackingStore(_store(tmp_path))
    work = tmp_path / "joint.ideaCon"
    work.write_bytes(b"idea-native-stub")
    stub_body: dict[str, Any] = {
        "route": "native",
        "backend": None,
        "offline_stub": True,
        "notice": "offline",
        "connections": [],
    }

    class _Sessions:
        async def call(self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect) -> Any:
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(stub_body))], is_error=False)

    async def body() -> None:
        with pytest.raises(ContractError) as raised:
            await calculate.calculate_native(
                sessions=_Sessions(),
                server="idea",
                role="main",
                path=work,
                connection_id=None,
                design_code=_DESIGN_CODE,
                load_map_confirmed=False,
                store=store.as_store(),
                ids=SeededIdSource(b"idea-calc-nstub", FixedClock(_START)),
                provenance=_provenance(),
            )
        assert raised.value.detail.code is ErrorCode.HOST_ERROR
        assert raised.value.detail.host_code == "OFFLINE_STUB"
        kinds = _kinds_put(store)
        assert "harness.run_output/1" in kinds
        assert "verdicts.set/1" not in kinds

    anyio.run(body)


def test_unexpected_shape_stores_failure_evidence_rest(tmp_path: Path) -> None:
    """AC11/AC12 §4.9: unexpected-shape reply is stored as failure evidence, never as a verdict."""
    from mcp.types import CallToolResult, TextContent

    from eng_harness.adapters.idea import _calculate as calculate

    store = _TrackingStore(_store(tmp_path))
    body = {"unexpected": True, "payload": "malformed"}

    class _Sessions:
        async def call(self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect) -> Any:
            if tool == "idea_status":
                return CallToolResult(
                    content=[TextContent(type="text", text='{"service":{"reachable":true,"service_version":"1"}}')],
                    is_error=False,
                )
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(body))], is_error=False)

    async def run() -> None:
        with pytest.raises(ContractError) as raised:
            await calculate.calculate_rest(
                sessions=_Sessions(),
                server="idea",
                role="main",
                connection_ids=[1],
                design_code=_DESIGN_CODE,
                load_map_confirmed=False,
                approved=True,
                store=store.as_store(),
                ids=SeededIdSource(b"idea-calc-ushape", FixedClock(_START)),
                provenance=_provenance(),
            )
        assert raised.value.detail.host_code == "UNEXPECTED_REPLY"
        kinds = _kinds_put(store)
        assert "harness.run_output/1" in kinds
        assert "verdicts.set/1" not in kinds
        assert "harness.run_output/1" in store.kinds

    anyio.run(run)


def test_connection_with_checks_and_errors_keeps_fail(tmp_path: Path) -> None:
    """AC12 additive: non-empty errors keep check-row verdicts (including host FAIL) and add ERROR."""
    from eng_harness.adapters.idea import _calculate as calculate

    rows = [
        {
            "connection_id": 1,
            "name": "CON1",
            "passed": False,
            "calculated": True,
            "checks": [
                {
                    "name": "Plates",
                    "check_value": 150.0,
                    "check_status": False,
                    "skipped": False,
                    "message": "over",
                    "load_case_id": None,
                }
            ],
            "errors": ["kernel failed"],
            "warnings": [],
        }
    ]
    payload = calculate._verdicts_from_connections(
        rows,
        design_code=_DESIGN_CODE,
        route="native",
        load_map_confirmed=True,
    )
    assert any(v.status is VerdictStatus.FAIL for v in payload.verdicts)
    assert any(v.check_id == "idea:connection" and v.status is VerdictStatus.ERROR for v in payload.verdicts)
    assert any("kernel failed" in a for v in payload.verdicts for a in v.assumptions)


def test_mixed_errors_and_uncalculated_keeps_error(tmp_path: Path) -> None:
    """AC12: one errored calculated connection + one uncalculated must not become PRECONDITION_FAILED."""
    from eng_harness.adapters.idea import _calculate as calculate

    rows = [
        {
            "connection_id": 1,
            "name": "BAD",
            "passed": False,
            "calculated": True,
            "checks": [],
            "errors": ["kernel failed"],
            "warnings": [],
        },
        {
            "connection_id": 2,
            "name": "PENDING",
            "passed": False,
            "calculated": False,
            "checks": [],
            "errors": [],
            "warnings": [],
        },
    ]
    payload = calculate._verdicts_from_connections(
        rows,
        design_code=_DESIGN_CODE,
        route="native",
        load_map_confirmed=True,
    )
    assert any(v.status is VerdictStatus.ERROR and "kernel failed" in " ".join(v.assumptions) for v in payload.verdicts)


def test_timeout_calculate_rest_carries_op_id(tmp_path: Path) -> None:
    """AC18: calculate_rest passes op_id into TIMEOUT_UNKNOWN_OUTCOME via the timeout_calculate fault."""
    from eng_harness.adapters.idea import _calculate as calculate

    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control, route="rest")
    model = make_ideacon(tmp_path / "joint.ideaCon")
    store = _store(tmp_path)

    async def body() -> None:
        async with ServerManager(config, tmp_path / "run") as manager:
            opened = await manager.call("idea", "main", "idea_open_project", {"path": str(model)}, CallEffect.WRITE)
            assert opened.is_error is False
            _fault(control, "timeout_calculate", tool="idea_calculate")
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
                    ids=SeededIdSource(b"idea-calc-to", FixedClock(_START)),
                    provenance=_provenance(),
                    op_id="op_calc_timeout_1",
                )
            assert raised.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
            assert raised.value.detail.op_id == "op_calc_timeout_1"

    anyio.run(body)


def test_stored_verdict_set_stale_after_revision_bump(tmp_path: Path) -> None:
    """R1 / 0002 §4.5.3: stored IDEA verdict carries model_revision; later revision → REF_STALE."""
    from eng_contract.envelope import LiteralInput
    from eng_contract.kinds.verdicts import VerdictSet
    from eng_contract.refs import RefRule, resolve_ref
    from eng_contract.store import ModelStateStore
    from eng_contract.verdicts import Subject, SubjectKind, Verdict, VerdictSource

    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.idea import _calculate as calculate
    from eng_harness.adapters.idea._verdicts import HOST_ASSUMPTION

    clock = FixedClock(_START, 1)
    ids = SeededIdSource(b"idea-calc-stale", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS.extend(IDEA_KINDS), ids, clock)
    states = ModelStateStore(workspace, clock)
    identity = IdentityStore(workspace=workspace, states=states, ids=ids)
    model_path = tmp_path / "joint.ideaCon"
    model_path.write_bytes(b"idea-model-v1")
    resolved = identity.resolve(model_path)
    prov = CalculateProvenance(
        clock=clock,
        host=HostInfo(
            program="idea",
            version="",
            model_id=resolved.model_id,
            model_revision=resolved.revision,
        ),
        tool_version="test-build+deadbeefdead",
    )
    verdict = Verdict(
        source=VerdictSource.HOST,
        check_id="idea:plates",
        code=_DESIGN_CODE,
        clause=None,
        subject=Subject(kind=SubjectKind.JOINT, id="CON1", station_mm=None, case=None),
        demand=None,
        capacity=None,
        ratio=0.4,
        ratio_limit=1.0,
        status=VerdictStatus.PASS,
        governing=False,
        trace_ref=None,
        assumptions=[HOST_ASSUMPTION],
    )
    counts = dict.fromkeys(VerdictStatus, 0)
    counts[VerdictStatus.PASS] = 1
    verdicts = VerdictSet(verdicts=[verdict], traces=[], counts=counts, draft=False)
    raw_payload: dict[str, JsonValue] = {"route": "native", "backend": None, "offline_stub": False, "connections": []}
    _raw_env, verd_env = calculate._store_pair(
        store=store,
        tool="idea_native_calculate",
        raw_payload=raw_payload,
        verdicts=verdicts,
        provenance=prov,
        inputs={"path": LiteralInput(literal=model_path.name)},
        files=(),
        started_at=clock.now(),
        duration_ms=0,
    )
    assert verd_env.provenance.host is not None
    assert verd_env.provenance.host.model_revision == resolved.revision
    assert verd_env.provenance.tool == "sasaah-idea-mcp/idea_native_calculate"
    assert verd_env.provenance.tool_version == "test-build+deadbeefdead"
    model_path.write_bytes(b"idea-model-v2-changed")
    identity.record_save(resolved.model_id, model_path, fingerprint="fp2")
    current = identity.resolve(model_path).revision
    assert current > resolved.revision

    def current_revision(model_id: str) -> int | None:
        return current if model_id == resolved.model_id else None

    with pytest.raises(ContractError) as raised:
        resolve_ref(
            verd_env.result_id,
            RefRule(kinds=frozenset({"verdicts.set/1"})),
            store,
            current_revision,
        )
    assert raised.value.detail.code is ErrorCode.REF_STALE


def _native_ok_body() -> dict[str, Any]:
    """Minimal live native check reply (spec 0014 §4.5 raw kind); values are test labels only."""
    return {
        "route": "native",
        "backend": None,
        "offline_stub": False,
        "connections": [
            {
                "connection_id": 1,
                "name": "CON1",
                "passed": True,
                "calculated": True,
                "checks": [
                    {
                        "name": "Plates",
                        "check_value": 50.0,
                        "check_status": True,
                        "skipped": False,
                        "message": "OK",
                        "load_case_id": "LC1",
                    }
                ],
                "errors": [],
                "warnings": [],
            }
        ],
    }


class _RecordingSessions:
    """Fake session manager: records every host call and answers with one fixed reply."""

    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.calls: list[str] = []

    async def call(self, server: str, role: str, tool: str, args: dict[str, Any], effect: CallEffect) -> Any:
        from mcp.types import CallToolResult, TextContent

        self.calls.append(tool)
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(self.reply))], is_error=False)


def test_native_missing_path_refused_before_host_call(tmp_path: Path) -> None:
    """0002 §4.5.3: a missing native file is PRECONDITION_FAILED on `path`; no host call, no invented hash."""
    from eng_harness.adapters.idea import _calculate as calculate

    sessions = _RecordingSessions(_native_ok_body())
    store = _TrackingStore(_store(tmp_path))

    async def body() -> None:
        with pytest.raises(ContractError) as raised:
            await calculate.calculate_native(
                sessions=sessions,
                server="idea",
                role="main",
                path=tmp_path / "missing.ideaCon",
                connection_id=None,
                design_code=_DESIGN_CODE,
                load_map_confirmed=False,
                store=store.as_store(),
                ids=SeededIdSource(b"idea-calc-missing", FixedClock(_START)),
                provenance=_provenance(),
            )
        assert raised.value.detail.code is ErrorCode.PRECONDITION_FAILED
        assert raised.value.detail.field == "path"
        assert str(tmp_path) not in raised.value.detail.message

    anyio.run(body)
    assert sessions.calls == []
    assert _kinds_put(store) == []


def test_native_file_provenance_hash_and_size(tmp_path: Path) -> None:
    """0002 §4.5.3: provenance `files` carries the real sha256 and byte size of the native input file."""
    from eng_harness.adapters.idea import _calculate as calculate

    work = tmp_path / "joint.ideaCon"
    content = b"idea-native-provenance-bytes"
    work.write_bytes(content)
    sessions = _RecordingSessions(_native_ok_body())

    async def body() -> None:
        result = await calculate.calculate_native(
            sessions=sessions,
            server="idea",
            role="main",
            path=work,
            connection_id=None,
            design_code=_DESIGN_CODE,
            load_map_confirmed=False,
            store=_store(tmp_path),
            ids=SeededIdSource(b"idea-calc-files", FixedClock(_START)),
            provenance=_provenance(),
        )
        for envelope in (result.raw_envelope, result.verdict_envelope):
            files = envelope.provenance.files
            assert len(files) == 1
            assert files[0].name == work.name
            assert files[0].sha256 == hashlib.sha256(content).hexdigest()
            assert files[0].size_bytes == len(content)

    anyio.run(body)
    assert sessions.calls == ["idea_native_calculate"]
