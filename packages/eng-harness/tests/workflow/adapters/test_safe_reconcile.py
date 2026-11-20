"""SAFE point-load reconciliation (plan 0008 T6; spec 0008 AC19, 0002 section 4.5.7).

A write cut off by a timeout is decided from the joint-load table read-back. Adapter imports sit inside the tests.
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

from .test_safe_state import _seed

ConfigFactory = Callable[..., ServersConfig]
HOST = HostInfo(program="SAFE", version="22.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0)
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
TOLERANCE = 0.001
AFTER, BEFORE = "timeout_after_apply", "timeout_before_apply"


class Binder:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.pre_image: str | None = None

    async def binding(self, host_key: str, model: str | None, descriptor: Any) -> Binding:
        return Binding(
            target=HostTarget(product="SAFE", pid=self.pid), host=HOST, owned=True, pre_image_ref=self.pre_image
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

    seed = _seed(joint_loads=0)
    control.write_text(json.dumps({"faults": [], "seed": seed, "product": "SAFE"}))
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"safe-rec", clock)
    base = config.servers["csi"].model_copy(update={"product": "SAFE", "host_key": "csi_safe"})
    safe_config = ServersConfig(servers={"csi_safe": base})
    async with ServerManager(safe_config, run_dir) as manager:
        launched = await manager.call("csi_safe", "main", "csi_launch", {"product": "SAFE"}, CallEffect.WRITE)
        block = launched.content[0]
        assert isinstance(block, types.TextContent)
        pid = json.loads(block.text)["pid"]
        manager.bind_instance("csi_safe", pid=pid, product="SAFE")
        binder = Binder(pid)
        port = CsiToolPort(
            binder=binder,
            config=safe_config,
            server="csi_safe",
            caller=manager,
            store=store,
            ledger=WriteLedger(run_dir),
            clock=clock,
            ids=ids,
            check=CHECK,
            errors=CsiErrorMapper(ids),
            reconciler=CsiReconciler(product="SAFE", tolerance_ratio=tolerance),
        )
        yield Rig(port, binder, store, control, manager, pid)


@pytest.fixture
def store(tmp_path: Path) -> ResultStore:
    from eng_harness._kinds import HARNESS_KINDS

    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"safe-rec-store", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS, ids, clock)


def _args(rig: Rig) -> dict[str, Any]:
    return {
        "joint": "P1",
        "pattern": "DEAD",
        "FX_kN": rig.value("FX_kN", 0.0),
        "FY_kN": rig.value("FY_kN", 0.0),
        "FZ_kN": rig.value("FZ_kN", -40.0),
        "MX_kNm": rig.value("MX_kNm", 0.0),
        "MY_kNm": rig.value("MY_kNm", 0.0),
        "MZ_kNm": rig.value("MZ_kNm", 0.0),
    }


@pytest.mark.parametrize(("fault", "expected"), [(AFTER, "applied"), (BEFORE, "not_applied")])
def test_point_load_outcomes(
    fault: str,
    expected: str,
    make_config: ConfigFactory,
    control: Path,
    store: ResultStore,
    tmp_path: Path,
) -> None:
    """AC19: csi_set_point_load reconciles applied after the write, not_applied before it."""

    async def body() -> None:
        async with _rig(make_config(), control, store, tmp_path / "run") as rig:
            args = _args(rig)
            await rig.before("csi_set_point_load", args)
            await rig.cut_off("csi_set_point_load", args, fault)
            found = await rig.reconcile("csi_set_point_load", args)
            assert found.outcome == expected
            assert found.missing == ()
            assert len(found.evidence) == 1
            evidence = cast(dict[str, Any], store.payload(found.evidence[0].ref)["value"])
            assert "requested" in evidence
            assert "observed" in evidence

    anyio.run(body)
