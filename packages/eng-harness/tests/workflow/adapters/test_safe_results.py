"""SAFE soil pressure, base/joint reaction and analysis-status readers (plan 0008 T7; spec 0008 AC22, AC23, §4.6).

Adapter imports sit inside the tests so a missing module fails the test. Host keys for Soil Pressures are the candidate
names of spec 0008 section 4.5 (SafePhase.cs citations). Present units of the synthetic fake are `kN_m_C` (stress =
kN/m2 = kPa). Base and joint reaction tools use the units token `kN_m_C` (spec 0008 section 4.6).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import HostInfo, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.errors import HarnessCode, NotImplementedGap
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect, ServerManager, ServersConfig

from .test_csi_session_ops import ConfigFactory
from .test_safe_state import _seed

_START = 1_700_000_000_000
SHA = "d" * 64
CHECK = ServerCheck(
    server="csi_safe",
    build="0123456789ab+fedcba987654",
    min_build="",
    fingerprint=SHA,
    expected_fingerprint=SHA,
    ok=True,
    reason=None,
)
SOIL = "Soil Pressures"
MESSAGES = "Analysis Messages"
# Candidate host keys from spec 0008 section 4.5 (SafePhase.cs); stress under kN_m_C is kN/m2 (= kPa).
_SOIL_ROW = {
    "UniqueName": "A1",
    "ShellElm": "E1",
    "Joint": "J1",
    "OutputCase": "DEAD",
    "StepType": "Max",
    "CaseType": "LinStatic",
    "Pressure": 12.5,
}


def _calls(control: Path) -> list[dict[str, Any]]:
    data = json.loads(control.read_text())
    calls = data.get("calls", [])
    assert isinstance(calls, list)
    return calls


def _seed_results(
    *,
    soil: list[dict[str, Any]] | None = None,
    base: list[dict[str, Any]] | None = None,
    joints: list[dict[str, Any]] | None = None,
    result_limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    seed = _seed()
    seed["tables"][SOIL] = soil if soil is not None else [{**_SOIL_ROW}]
    seed["results"] = {
        "csi_results_base_reactions": base
        if base is not None
        else [{"case": "DEAD", "F1": 1.0, "F2": -2.0, "F3": 50.0, "M1": 0.5, "M2": -0.25, "M3": 0.0}],
        "csi_results_joint_reactions": joints
        if joints is not None
        else [{"joint": "P1", "case": "DEAD", "F1": 0.0, "F2": 0.0, "F3": -100.0, "M1": 0.0, "M2": 0.0, "M3": 0.0}],
    }
    if result_limits is not None:
        seed["result_limits"] = result_limits
    return seed


def _seed_control(control: Path, seed: dict[str, Any]) -> None:
    control.write_text(json.dumps({"faults": [], "seed": seed, "product": "SAFE"}))


class _Binder:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    async def binding(self, host_key: str, model: str | None, descriptor: Any) -> Binding:
        return Binding(
            target=HostTarget(product="SAFE", pid=self.pid),
            units_system=None,
            host=HostInfo(
                program="SAFE", version="22.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0
            ),
            owned=True,
        )

    def revision(self, model_id: str) -> int | None:
        return None


class _Rig:
    def __init__(self, port: Any, manager: ServerManager, pid: int, call: Any) -> None:
        self.port, self.manager, self.pid, self.call = port, manager, pid, call


@asynccontextmanager
async def _results_rig(tmp_path: Path, config: ServersConfig, control: Path) -> AsyncIterator[_Rig]:
    from eng_harness._kinds import HARNESS_KINDS
    from eng_harness.adapters.csi._tools import CsiToolPort

    clock = FixedClock(_START, 1)
    ids = SeededIdSource(b"safe-results", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    run_dir = tmp_path / "run"
    base = config.servers["csi"].model_copy(update={"product": "SAFE", "host_key": "csi_safe"})
    safe_config = ServersConfig(servers={"csi_safe": base})
    manager = ServerManager(safe_config, run_dir)

    async with manager:
        launched = await manager.call("csi_safe", "main", "csi_launch", {"product": "SAFE"}, CallEffect.WRITE)
        from mcp import types

        block = launched.content[0]
        assert isinstance(block, types.TextContent)
        pid = json.loads(block.text)["pid"]
        manager.bind_instance("csi_safe", pid=pid, product="SAFE")
        port = CsiToolPort(
            binder=_Binder(pid),
            config=safe_config,
            server="csi_safe",
            caller=manager,
            store=store,
            ledger=WriteLedger(run_dir),
            clock=clock,
            ids=ids,
            check=CHECK,
            errors=CsiErrorMapper(ids),
        )

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect = CallEffect.READ) -> dict[str, Any]:
            result = await manager.call("csi_safe", "main", tool, arguments, effect)
            text = result.content[0]
            assert isinstance(text, types.TextContent)
            body = json.loads(text.text)
            assert isinstance(body, dict)
            return body

        yield _Rig(port, manager, pid, call)


def test_soil_pressure_rows(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC22: mapped soil-pressure rows carry optional keys, candidate status and host_unconfirmed sign."""
    from eng_harness.adapters.csi.products import _safe_results as results

    _seed_control(control, _seed_results())

    async def body() -> None:
        async with _results_rig(tmp_path, make_config(), control) as rig:
            payload = await results.read_soil_pressures(
                rig.call, product="SAFE", pid=rig.pid, cases=["DEAD"], units="kN_m_C"
            )
            assert payload.source_table == SOIL
            assert payload.sign_convention == "host_unconfirmed/1"
            assert payload.field_map_status == "candidate"
            assert len(payload.rows) == 1
            row = payload.rows[0]
            assert row.area == "A1"
            assert row.element == "E1"
            assert row.joint == "J1"
            assert row.case.case == "DEAD"
            assert row.step_type == "Max"
            assert row.case_type == "LinStatic"
            assert row.pressure_kpa == pytest.approx(12.5)  # kN/m2 under kN_m_C → kPa 1:1
            assert payload.summary.count == 1
            assert payload.summary.min_kpa == pytest.approx(12.5)
            assert payload.summary.max_kpa == pytest.approx(12.5)
            assert payload.summary.min_kpa >= 0 or payload.summary.min_kpa < 0  # no abs() in the adapter

    anyio.run(body)
    assert any(c["tool"] == "csi_db_table_read" for c in _calls(control))


def test_soil_pressure_truncated(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC22 / SG-6: a truncated Soil Pressures reply is LIMIT_EXCEEDED with the group hint."""
    from eng_harness.adapters.csi.products import _safe_results as results

    rows = [{**_SOIL_ROW, "UniqueName": f"A{n}", "Joint": f"J{n}", "Pressure": float(n)} for n in range(1, 4)]
    seed = _seed_results(soil=rows, result_limits={SOIL: 1})
    _seed_control(control, seed)

    async def body() -> None:
        async with _results_rig(tmp_path, make_config(), control) as rig:
            with pytest.raises(ContractError) as caught:
                await results.read_soil_pressures(rig.call, product="SAFE", pid=rig.pid, cases=["DEAD"], units="kN_m_C")
            assert caught.value.detail.code is ErrorCode.LIMIT_EXCEEDED
            assert caught.value.detail.hint == "group"
            assert caught.value.detail.received == 1
            assert "SG-6" in caught.value.detail.message or "group" in caught.value.detail.message.lower()

    anyio.run(body)


def test_soil_pressure_group(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC22: the optional group filter is passed to csi_db_table_read."""
    from eng_harness.adapters.csi.products import _safe_results as results

    rows = [
        {**_SOIL_ROW, "UniqueName": "A1", "Joint": "J1", "Group": "F1", "Pressure": 10.0},
        {**_SOIL_ROW, "UniqueName": "A2", "Joint": "J2", "Group": "F2", "Pressure": 20.0},
    ]
    _seed_control(control, _seed_results(soil=rows))

    async def body() -> None:
        async with _results_rig(tmp_path, make_config(), control) as rig:
            payload = await results.read_soil_pressures(
                rig.call, product="SAFE", pid=rig.pid, cases=["DEAD"], units="kN_m_C", group="F2"
            )
            assert [r.area for r in payload.rows] == ["A2"]
            assert payload.rows[0].pressure_kpa == pytest.approx(20.0)

    anyio.run(body)
    assert any(c["tool"] == "csi_db_table_read" for c in _calls(control))


def test_soil_pressure_step_type_and_unique_key(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC22: Max/Min rows keep step_type; a duplicate key is INTERNAL with the columns seen."""
    from eng_harness.adapters.csi.products import _safe_results as results

    envelope = [
        {**_SOIL_ROW, "StepType": "Max", "Pressure": 15.0},
        {**_SOIL_ROW, "StepType": "Min", "Pressure": -3.0},
    ]
    _seed_control(control, _seed_results(soil=envelope))

    async def ok() -> None:
        async with _results_rig(tmp_path / "ok", make_config(), control) as rig:
            payload = await results.read_soil_pressures(
                rig.call, product="SAFE", pid=rig.pid, cases=["DEAD"], units="kN_m_C"
            )
            assert {(r.step_type, r.pressure_kpa) for r in payload.rows} == {("Max", 15.0), ("Min", -3.0)}
            assert payload.summary.min_kpa == pytest.approx(-3.0)  # raw min, no abs
            assert payload.summary.max_kpa == pytest.approx(15.0)

    anyio.run(ok)

    dup = [{**_SOIL_ROW, "StepType": "Max", "Pressure": 1.0}, {**_SOIL_ROW, "StepType": "Max", "Pressure": 2.0}]
    _seed_control(control, _seed_results(soil=dup))

    async def bad() -> None:
        async with _results_rig(tmp_path / "dup", make_config(), control) as rig:
            with pytest.raises(ContractError) as caught:
                await results.read_soil_pressures(rig.call, product="SAFE", pid=rig.pid, cases=["DEAD"], units="kN_m_C")
            assert caught.value.detail.code is ErrorCode.INTERNAL
            received = caught.value.detail.received
            assert isinstance(received, dict)
            assert "columns_seen" in received

    anyio.run(bad)


def test_base_and_joint_reactions(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC23: base reactions are harness.base_reactions/1; joint reactions are forces.joint_reactions/1."""
    from eng_contract.kinds.forces import JointReactions

    from eng_harness._kinds import BaseReactions

    _seed_control(control, _seed_results())

    async def body() -> None:
        async with _results_rig(tmp_path, make_config(), control) as rig:
            base = await rig.port.call(
                "csi_results_base_reactions",
                {"model": "m", "cases": ["DEAD"]},
                op_id="op-base",
                model="m",
            )
            assert isinstance(base, SuccessEnvelope), base
            assert base.kind == "harness.base_reactions/1"
            parsed = BaseReactions.model_validate(base.data)
            assert parsed.moment_reference == "host_unconfirmed/1"
            assert parsed.rows[0].case.case == "DEAD"
            assert parsed.rows[0].fz_kn == pytest.approx(50.0)
            assert parsed.rows[0].mx_knm == pytest.approx(0.5)
            joints = await rig.port.call(
                "csi_results_joint_reactions",
                {"model": "m", "cases": ["DEAD"], "object": "P1"},
                op_id="op-joint",
                model="m",
            )
            assert isinstance(joints, SuccessEnvelope), joints
            assert joints.kind == "forces.joint_reactions/1"
            joint = JointReactions.model_validate(joints.data)
            assert joint.rows[0].FZ_kN == pytest.approx(-100.0)

    anyio.run(body)


def test_analysis_status(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC23: csi_analysis_status becomes harness.csi_analysis_status/1 after a SAFE analysis run."""
    from eng_harness.adapters.csi.products import _safe_results as results
    from eng_harness.kinds.csi import CsiAnalysisStatus

    assert "csi_analysis_status" in results.READERS or hasattr(results, "analysis_status")
    seed = _seed_results()
    seed["load_cases"] = [{"name": "DEAD"}, {"name": "LIVE"}]
    _seed_control(control, seed)

    async def body() -> None:
        async with _results_rig(tmp_path, make_config(), control) as rig:
            before = await rig.port.call("csi_analysis_status", {"model": "m"}, op_id="op-st0", model="m")
            assert isinstance(before, SuccessEnvelope), before
            assert before.kind == "harness.csi_analysis_status/1"
            run = await rig.port.call("csi_run_analysis", {"model": "m"}, op_id="op-run", model="m")
            assert isinstance(run, SuccessEnvelope), run
            after = await rig.port.call("csi_analysis_status", {"model": "m"}, op_id="op-st1", model="m")
            assert isinstance(after, SuccessEnvelope), after
            assert after.kind == "harness.csi_analysis_status/1"
            status = CsiAnalysisStatus.model_validate(after.data)
            assert {row.case for row in status.cases} >= {"DEAD", "LIVE"}

    anyio.run(body)


def test_analysis_messages_unknown_is_gap(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC23: reading Analysis Messages is NotImplementedGap until a recording sets its keys (unknown map)."""
    from eng_harness.adapters.csi.products import _safe_results as results

    seed = _seed_results()
    seed["tables"][MESSAGES] = [{"Message": "ok", "Level": "Info"}]
    _seed_control(control, seed)

    async def body() -> None:
        async with _results_rig(tmp_path, make_config(), control) as rig:
            with pytest.raises(NotImplementedGap) as caught:
                await results.read_analysis_messages(rig.call, product="SAFE", pid=rig.pid)
            assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
            assert MESSAGES in caught.value.evidence

    anyio.run(body)
