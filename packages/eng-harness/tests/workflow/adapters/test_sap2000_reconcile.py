"""SAP2000 add-frame reconciliation by geometry (plan 0012 T5; spec 0012 AC12).

A write cut off by a timeout is decided from `csi_list_frames`: exactly one new frame with the requested points and
section is `applied`, none is `not_applied`, anything else is `unknown`. Adapter imports sit inside the tests.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from eng_contract.envelope import FailureEnvelope, HostInfo, Provenance, SuccessEnvelope
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from mcp import types

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.ports import Reconciliation, ServerCheck
from eng_harness.servers import CallEffect, ServerManager, ServersConfig

from .test_sap2000_state import _seed

ConfigFactory = Callable[..., ServersConfig]
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
TOLERANCE = 0.001
AFTER, BEFORE = "timeout_after_apply", "timeout_before_apply"


class Binder:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.pre_image: str | None = None

    async def binding(self, host_key: str, model: str | None, descriptor: Any) -> Binding:
        return Binding(
            target=HostTarget(product="SAP2000", pid=self.pid), host=HOST, owned=True, pre_image_ref=self.pre_image
        )

    def revision(self, model_id: str) -> int | None:
        return None


@dataclass
class Rig:
    port: Any
    binder: Binder
    store: ResultStore
    control: Path
    manager: ServerManager
    pid: int
    count: int = 0

    def value(self, name: str, number: float) -> dict[str, str]:
        producer = Provenance(
            tool="harness",
            tool_version="1",
            inputs={},
            started_at="2026-01-01T00:00:00.000Z",
            duration_ms=0,
            host=HOST,
        )
        record = self.store.put("harness.run_input/1", {"value": {name: number}}, producer)
        return {"$ref": f"{record.result_id}#/value/{name}"}

    def arm(self, fault: str, tool: str) -> None:
        data = json.loads(self.control.read_text())
        data["faults"].append({"fault": fault, "tool": tool})
        self.control.write_text(json.dumps(data))

    async def before(self, tool: str, args: dict[str, Any]) -> None:
        envelope = await self.port.read_back(tool, {"model": "m", **args})
        assert isinstance(envelope, SuccessEnvelope), envelope
        self.binder.pre_image = f"{envelope.result_id}#/value/observed"

    async def cut_off(self, tool: str, args: dict[str, Any], fault: str, op_id: str = "op-1") -> None:
        self.arm(fault, tool)
        reply = await self.port.call(tool, {"model": "m", **args}, op_id=op_id, model="m")
        assert isinstance(reply, FailureEnvelope), reply
        assert reply.error.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME

    async def reconcile(self, tool: str, args: dict[str, Any], op_id: str = "op-1") -> Reconciliation:
        found: Reconciliation = await self.port.reconcile(tool, {"model": "m", **args}, op_id)
        return found


@asynccontextmanager
async def _rig(
    config: ServersConfig, control: Path, store: ResultStore, run_dir: Path, *, tolerance: float | None = TOLERANCE
) -> AsyncIterator[Rig]:
    from eng_harness.adapters.csi._reconcile import CsiReconciler
    from eng_harness.adapters.csi._tools import CsiToolPort

    seed = _seed(frames=1)
    control.write_text(json.dumps({"faults": [], "seed": seed, "product": "SAP2000"}))
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"sap-rec", clock)
    base = config.servers["csi"].model_copy(update={"product": "SAP2000", "host_key": "csi_sap2000"})
    sap_config = ServersConfig(servers={"csi_sap2000": base})
    async with ServerManager(sap_config, run_dir) as manager:
        launched = await manager.call("csi_sap2000", "main", "csi_launch", {"product": "SAP2000"}, CallEffect.WRITE)
        block = launched.content[0]
        assert isinstance(block, types.TextContent)
        pid = json.loads(block.text)["pid"]
        manager.bind_instance("csi_sap2000", pid=pid, product="SAP2000")
        binder = Binder(pid)
        port = CsiToolPort(
            binder=binder,
            config=sap_config,
            server="csi_sap2000",
            caller=manager,
            store=store,
            ledger=WriteLedger(run_dir),
            clock=clock,
            ids=ids,
            check=CHECK,
            errors=CsiErrorMapper(ids),
            reconciler=CsiReconciler(product="SAP2000", tolerance_ratio=tolerance),
        )
        yield Rig(port, binder, store, control, manager, pid)


@pytest.fixture
def store(tmp_path: Path) -> ResultStore:
    from eng_harness._kinds import HARNESS_KINDS

    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"sap-rec-store", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS, ids, clock)


def _args(rig: Rig) -> dict[str, Any]:
    return {
        "name": "RequestedCol",
        "section": "C300",
        "xi_mm": rig.value("xi_mm", 5000.0),
        "yi_mm": rig.value("yi_mm", 0.0),
        "zi_mm": rig.value("zi_mm", 0.0),
        "xj_mm": rig.value("xj_mm", 5000.0),
        "yj_mm": rig.value("yj_mm", 0.0),
        "zj_mm": rig.value("zj_mm", 3500.0),
    }


@pytest.mark.parametrize(("fault", "expected"), [(AFTER, "applied"), (BEFORE, "not_applied")])
def test_add_frame_outcomes(
    fault: str,
    expected: str,
    make_config: ConfigFactory,
    control: Path,
    store: ResultStore,
    tmp_path: Path,
) -> None:
    """AC12: add-frame reconciles by geometry; applied / not_applied; never added twice."""

    async def body() -> None:
        async with _rig(make_config(), control, store, tmp_path / "run") as rig:
            args = _args(rig)
            await rig.before("csi_add_frame_by_coord", args)
            await rig.cut_off("csi_add_frame_by_coord", args, fault)
            found = await rig.reconcile("csi_add_frame_by_coord", args)
            assert found.outcome == expected
            assert found.missing == ()
            assert len(found.evidence) == 1
            evidence = cast(dict[str, Any], store.payload(found.evidence[0].ref)["value"])
            assert "requested" in evidence
            assert "observed" in evidence

            # A second reconcile after an applied write must not invent another frame (AC12).
            if expected == "applied":
                again = await rig.reconcile("csi_add_frame_by_coord", args, op_id="op-1")
                assert again.outcome == "applied"
                listed = await rig.manager.call(
                    "csi_sap2000",
                    "main",
                    "csi_list_frames",
                    {"target": {"product": "SAP2000", "pid": rig.pid}, "limit": 2000, "units": "kN_mm_C"},
                    CallEffect.READ,
                )
                block = listed.content[0]
                assert isinstance(block, types.TextContent)
                items = json.loads(block.text)["items"]
                matches = [
                    row
                    for row in items
                    if row.get("section") == "C300"
                    and row.get("point1") == [5000.0, 0.0, 0.0]
                    and row.get("point2") == [5000.0, 0.0, 3500.0]
                ]
                assert len(matches) == 1

    anyio.run(body)
