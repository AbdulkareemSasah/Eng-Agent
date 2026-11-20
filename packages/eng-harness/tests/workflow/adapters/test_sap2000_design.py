"""SAP2000 design run and results (plan 0012 T6; spec 0012 AC16).

Adapter imports sit inside the tests so a missing module fails the test. Steel and concrete design runs become raw
`harness.csi_design_run/1` / `harness.csi_design_results/1` (never a verdict, 06 §9). Concrete results for frames that
are not beams are gap SP-3. Aluminum and coldformed are `NOT_SUPPORTED_BY_VERSION` before any host call.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import FailureEnvelope, HostInfo, SuccessEnvelope
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from mcp import types

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.errors import HarnessCode, NotImplementedGap
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect, ServerManager, ServersConfig

from .test_csi_session_ops import ConfigFactory

HOST = HostInfo(program="SAP2000", version="26.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0)
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
    "load_cases": [{"name": "DEAD"}],
    "design_results": {
        "steel": [{"frame": "B1", "ratio": 0.75, "ratio_type": "PMM", "location": 1.5, "combo": "1.4D"}],
        "concrete": [
            {
                "frame": "B1",
                "location": 0.0,
                "top_combo": "1.4D",
                "top_area": 1.0,
                "bot_combo": "1.4D",
                "bot_area": 1.0,
                "shear_combo": "1.4D",
                "shear_area": 0.5,
            }
        ],
    },
}


def _calls(control: Path) -> list[dict[str, Any]]:
    data = json.loads(control.read_text())
    calls = data.get("calls", [])
    assert isinstance(calls, list)
    return calls


class Recorder:
    """Notes the role and tool of each host call."""

    def __init__(self, manager: ServerManager) -> None:
        self.manager = manager
        self.sent: list[tuple[str, str, dict[str, Any]]] = []

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        self.sent.append((role, tool, dict(arguments)))
        return await self.manager.call(server, role, tool, arguments, effect)


class Binder:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    async def binding(self, host_key: str, model: str | None, descriptor: ToolDescriptor) -> Binding:
        return Binding(target=HostTarget(product="SAP2000", pid=self.pid), host=HOST, owned=True)

    def revision(self, model_id: str) -> int | None:
        return None


def _sap_config(config: ServersConfig) -> ServersConfig:
    server = config.servers["csi"].model_copy(update={"product": "SAP2000", "host_key": "csi_sap2000"})
    return ServersConfig(servers={"csi_sap2000": server})


def _run(
    config: ServersConfig,
    run_dir: Path,
    store: ResultStore,
    control: Path,
    body: Any,
) -> Recorder:
    from eng_harness.adapters.csi._tools import CsiToolPort

    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"sap-design", clock)
    recorder_box: dict[str, Recorder] = {}

    async def scenario() -> None:
        async with ServerManager(config, run_dir) as manager:
            launched = await manager.call(
                "csi_sap2000", "main", "csi_launch", {"product": "SAP2000"}, CallEffect.WRITE
            )
            block = launched.content[0]
            assert isinstance(block, types.TextContent)
            pid = json.loads(block.text)["pid"]
            manager.bind_instance("csi_sap2000", pid=pid, product="SAP2000")
            recorder = Recorder(manager)
            recorder_box["r"] = recorder
            port = CsiToolPort(
                binder=Binder(pid),
                config=config,
                server="csi_sap2000",
                caller=recorder,
                store=store,
                ledger=WriteLedger(run_dir),
                clock=clock,
                ids=ids,
                check=CHECK,
                errors=CsiErrorMapper(ids),
            )
            await body(port, recorder, pid)

    anyio.run(scenario)
    return recorder_box["r"]


@pytest.fixture
def store(tmp_path: Path, ids: SeededIdSource) -> ResultStore:
    from eng_harness._kinds import HARNESS_KINDS

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS, ids, FixedClock(1_767_225_600_000, 1))


def test_steel_and_concrete_run(
    make_config: ConfigFactory, control: Path, store: ResultStore, tmp_path: Path
) -> None:
    """AC16: steel and concrete design runs and steel design results are raw harness kinds (never a verdict)."""
    from eng_harness.adapters.csi.products import _sap2000_results as results

    assert "csi_design_run" in results.READERS
    assert "csi_design_results" in results.READERS

    control.write_text(json.dumps({"faults": [], "seed": _SEED, "product": "SAP2000"}))

    async def body(port: Any, recorder: Recorder, pid: int) -> None:
        for kind in ("steel", "concrete"):
            info = await port.describe("csi_design_run")
            assert (info.effect, info.action, info.model_param) == ("write", "design", "model")
            run = await port.call(
                "csi_design_run", {"model": "m", "kind": kind}, op_id=f"op-run-{kind}", model="m"
            )
            assert isinstance(run, SuccessEnvelope), run
            assert run.kind == "harness.csi_design_run/1"
            assert run.data["kind"] == kind
            assert run.data.get("completed") is True
        steel = await port.call(
            "csi_design_results", {"model": "m", "kind": "steel"}, op_id="op-steel-rows", model="m"
        )
        assert isinstance(steel, SuccessEnvelope), steel
        assert steel.kind == "harness.csi_design_results/1"
        assert steel.data == {
            "rows": [{"frame": "B1", "ratio": 0.75, "ratio_type": "PMM", "location": 1.5, "combo": "1.4D"}]
        }
        assert [("long" if tool == "csi_design_run" else "main", tool) for role, tool, _ in recorder.sent].count(
            ("long", "csi_design_run")
        ) == 2
        assert recorder.sent[-1][:2] == ("main", "csi_design_results")

    _run(_sap_config(make_config()), tmp_path / "run", store, control, body)


def test_concrete_non_beam_results_gap(
    make_config: ConfigFactory, control: Path, store: ResultStore, tmp_path: Path
) -> None:
    """AC16 / SP-3: concrete design results for frames that are not beams raise NotImplementedGap; nothing is sent."""
    from eng_harness.adapters.csi.products import _sap2000_results as results

    control.write_text(json.dumps({"faults": [], "seed": _SEED, "product": "SAP2000"}))
    before = len(_calls(control))

    with pytest.raises(NotImplementedGap) as caught:
        results.concrete_non_beam_results()
    assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
    assert caught.value.evidence == ("SP-3",)
    assert "SP-3" in caught.value.message or "not beams" in caught.value.message

    async def body(port: Any, recorder: Recorder, pid: int) -> None:
        with pytest.raises(NotImplementedGap) as from_port:
            await port.call(
                "csi_design_results",
                {"model": "m", "kind": "concrete", "name": "C1"},
                op_id="op-concrete-col",
                model="m",
            )
        assert from_port.value.code is HarnessCode.NOT_IMPLEMENTED
        assert from_port.value.evidence == ("SP-3",)
        assert not any(tool == "csi_design_results" for _role, tool, _args in recorder.sent)

    _run(_sap_config(make_config()), tmp_path / "run", store, control, body)
    assert len([c for c in _calls(control) if c.get("tool") == "csi_design_results"]) == 0
    assert len(_calls(control)) >= before  # launch may add calls; design_results must not


def test_other_kinds_refused(
    make_config: ConfigFactory, control: Path, store: ResultStore, tmp_path: Path
) -> None:
    """AC16: aluminum and coldformed are NOT_SUPPORTED_BY_VERSION before any host call."""
    from eng_harness.adapters.csi.products import _sap2000_results as results

    assert hasattr(results, "refuse_unsupported_design_kind")

    control.write_text(json.dumps({"faults": [], "seed": _SEED, "product": "SAP2000"}))

    async def body(port: Any, recorder: Recorder, pid: int) -> None:
        for kind in ("aluminum", "coldformed"):
            reply = await port.call(
                "csi_design_run", {"model": "m", "kind": kind}, op_id=f"op-{kind}", model="m"
            )
            assert isinstance(reply, FailureEnvelope), reply
            assert reply.error.code is ErrorCode.NOT_SUPPORTED_BY_VERSION
        assert not any(tool == "csi_design_run" for _role, tool, _args in recorder.sent)

    _run(_sap_config(make_config()), tmp_path / "run", store, control, body)
    assert not any(c.get("tool") == "csi_design_run" for c in _calls(control))
