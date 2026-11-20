"""SAP2000 result readers and analysis status (plan 0012 T6; spec 0012 AC15).

Adapter imports sit inside the tests so a missing module fails the test. Force tools use the units token `kN_m_C`
(spec 0012 AC15 through `eng_contract.units`). Frame-force rows keep `station` (as `station_mm`) and envelope
`step` (host `step_type` / CaseRef.step); none are dropped or merged. Sign convention stays `host_local/1` (contract G-3).
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
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.store import LocationClass, ResultStore, Workspace

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect, ServerManager, ServersConfig

from .test_csi_session_ops import ConfigFactory

_START = 1_700_000_000_000
SHA = "d" * 64
CHECK = ServerCheck(
    server="csi_sap2000",
    build="0123456789ab+fedcba987654",
    min_build="",
    fingerprint=SHA,
    expected_fingerprint=SHA,
    ok=True,
    reason=None,
)

_SEED = {
    "load_cases": [{"name": "DEAD"}, {"name": "LIVE"}],
    "results": {
        "csi_results_joint_reactions": [
            {"joint": "J1", "case": "DEAD", "F1": 1.5, "F2": -2.0, "F3": 120.25, "M1": 0.5, "M2": -0.25, "M3": 0.0},
        ],
        "csi_results_frame_forces": [
            {
                "frame": "B1",
                "case": "1.4D",
                "kind": "combo",
                "station": 1.25,
                "step": "Max",
                "P": -10.0,
                "V2": 4.5,
                "V3": 0.0,
                "T": 0.0,
                "M2": 0.0,
                "M3": -7.75,
            },
            {
                "frame": "B1",
                "case": "1.4D",
                "kind": "combo",
                "station": 1.25,
                "step": "Min",
                "P": -8.0,
                "V2": 3.0,
                "V3": 0.0,
                "T": 0.0,
                "M2": 0.0,
                "M3": -5.0,
            },
        ],
        "csi_results_base_reactions": [
            {"case": "DEAD", "F1": 1.0, "F2": -2.0, "F3": 50.0, "M1": 0.5, "M2": -0.25, "M3": 0.0},
        ],
    },
}


def _calls(control: Path) -> list[dict[str, Any]]:
    data = json.loads(control.read_text())
    calls = data.get("calls", [])
    assert isinstance(calls, list)
    return calls


class _Binder:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    async def binding(self, host_key: str, model: str | None, descriptor: Any) -> Binding:
        return Binding(
            target=HostTarget(product="SAP2000", pid=self.pid),
            units_system=None,
            host=HostInfo(
                program="SAP2000", version="26.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0
            ),
            owned=True,
        )

    def revision(self, model_id: str) -> int | None:
        return None


class _Rig:
    def __init__(self, port: Any, manager: ServerManager, pid: int, recorder_sent: list[Any]) -> None:
        self.port, self.manager, self.pid, self.sent = port, manager, pid, recorder_sent


@asynccontextmanager
async def _results_rig(tmp_path: Path, config: ServersConfig, control: Path) -> AsyncIterator[_Rig]:
    from eng_harness._kinds import HARNESS_KINDS
    from eng_harness.adapters.csi._tools import CsiToolPort

    clock = FixedClock(_START, 1)
    ids = SeededIdSource(b"sap-results", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    run_dir = tmp_path / "run"
    base = config.servers["csi"].model_copy(update={"product": "SAP2000", "host_key": "csi_sap2000"})
    sap_config = ServersConfig(servers={"csi_sap2000": base})
    manager = ServerManager(sap_config, run_dir)
    sent: list[tuple[str, str, dict[str, Any]]] = []

    class _Recorder:
        async def call(
            self, server: str, role: str, tool: str, arguments: dict[str, Any], effect: CallEffect
        ) -> Any:
            sent.append((role, tool, dict(arguments)))
            return await manager.call(server, role, tool, arguments, effect)

    async with manager:
        launched = await manager.call("csi_sap2000", "main", "csi_launch", {"product": "SAP2000"}, CallEffect.WRITE)
        from mcp import types

        block = launched.content[0]
        assert isinstance(block, types.TextContent)
        pid = json.loads(block.text)["pid"]
        manager.bind_instance("csi_sap2000", pid=pid, product="SAP2000")
        port = CsiToolPort(
            binder=_Binder(pid),
            config=sap_config,
            server="csi_sap2000",
            caller=_Recorder(),
            store=store,
            ledger=WriteLedger(run_dir),
            clock=clock,
            ids=ids,
            check=CHECK,
            errors=CsiErrorMapper(ids),
        )
        yield _Rig(port, manager, pid, sent)


def test_reply_kinds_and_units(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC15: joint reactions, frame forces, base reactions and analysis status kinds and units."""
    from eng_contract.kinds.forces import JointReactions, MemberEnd

    from eng_harness._kinds import BaseReactions
    from eng_harness.adapters.csi.products import _sap2000_results as results
    from eng_harness.kinds.csi import CsiAnalysisStatus

    assert "csi_results_joint_reactions" in results.READERS
    assert "csi_results_frame_forces" in results.READERS
    assert "csi_results_base_reactions" in results.READERS
    assert "csi_analysis_status" in results.READERS
    assert results.TOKENS["csi_results_joint_reactions"] == "kN_m_C"
    assert results.TOKENS["csi_results_frame_forces"] == "kN_m_C"
    assert results.TOKENS["csi_results_base_reactions"] == "kN_m_C"

    control.write_text(json.dumps({"faults": [], "seed": _SEED, "product": "SAP2000"}))
    cases = {"cases": ["DEAD"], "combos": ["1.4D"]}

    async def body() -> None:
        async with _results_rig(tmp_path, make_config(), control) as rig:
            reactions = await rig.port.call(
                "csi_results_joint_reactions",
                {"model": "m", "object": "J1", **cases},
                op_id="op-joint",
                model="m",
            )
            frames = await rig.port.call(
                "csi_results_frame_forces",
                {"model": "m", **cases},
                op_id="op-frame",
                model="m",
            )
            base = await rig.port.call(
                "csi_results_base_reactions",
                {"model": "m", "cases": ["DEAD"]},
                op_id="op-base",
                model="m",
            )
            status = await rig.port.call("csi_analysis_status", {"model": "m"}, op_id="op-status", model="m")
            for reply, kind in (
                (reactions, "forces.joint_reactions/1"),
                (frames, "forces.member_end/1"),
                (base, "harness.base_reactions/1"),
                (status, "harness.csi_analysis_status/1"),
            ):
                assert isinstance(reply, SuccessEnvelope), reply
                assert reply.kind == kind
                if kind in NEUTRAL_KINDS:
                    NEUTRAL_KINDS[kind].model_validate(reply.data)

            joint = JointReactions.model_validate(reactions.data)
            assert joint.rows[0].FZ_kN == pytest.approx(120.25)
            member = MemberEnd.model_validate(frames.data)
            assert member.sign_convention == "host_local/1"
            assert len(member.rows) == 2  # Max and Min kept; none dropped or merged (AC15)
            assert {row.station_mm for row in member.rows} == {1250.0}
            assert {row.case.step for row in member.rows} == {"Max", "Min"}
            assert member.rows[0].case.case_type == "load_combination"
            parsed_base = BaseReactions.model_validate(base.data)
            assert parsed_base.moment_reference == "host_unconfirmed/1"
            assert parsed_base.rows[0].fz_kn == pytest.approx(50.0)
            CsiAnalysisStatus.model_validate(status.data)

            tools = [tool for _role, tool, _args in rig.sent]
            assert tools == [
                "csi_results_joint_reactions",
                "csi_results_frame_forces",
                "csi_results_base_reactions",
                "csi_analysis_status",
            ]
            for _role, tool, args in rig.sent[:3]:
                if tool != "csi_analysis_status":
                    assert args.get("units") == "kN_m_C"

    anyio.run(body)
    assert any(c["tool"] == "csi_results_joint_reactions" for c in _calls(control))
