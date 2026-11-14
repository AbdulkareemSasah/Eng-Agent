"""CSI reconciliation by reading model state against the synthetic fake (plan 0002 T14; spec 0002 AC23, 4.5.7).

A write is cut off by a server `timeout` that the fake raises either after the write was applied
(`timeout_after_apply`) or before it was (`timeout_before_apply`); the adapter then reads the object back and decides.
The pre-image of a write is the `observed` value of a `read_back` taken before it, as the binder of the host port would
point to (`Binding.pre_image_ref`). Expected outcomes are derived from the spec table of 4.5.7 by hand: a setter whose
state equals the request is `applied`, one whose state equals the pre-image is `not_applied`; a new pattern or
combination is `applied` when present as requested and `not_applied` when absent (and absent before, for a
combination); `csi_delete_load_combo` is `applied` when absent and `not_applied` when present. Analysis and design are
`unknown` whatever the host answers while no proof of end of the abandoned call exists (gap H-G7). The adapter imports
are inside the tests so a missing module fails the test.
"""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import FailureEnvelope, HostInfo, Provenance, SuccessEnvelope
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from mcp import types

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.ports import Reconciliation, ServerCheck
from eng_harness.servers import CallEffect, ServerManager, ServersConfig

from .test_csi_session_ops import ConfigFactory
from .test_csi_state import _seed

HOST = HostInfo(program="ETABS", version="22.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0)
SHA = "d" * 64
CHECK = ServerCheck(
    server="csi", build="0123456789ab+fedcba987654", min_build="", fingerprint=SHA, expected_fingerprint=SHA, ok=True,
    reason=None,
)  # fmt: skip
TOLERANCE = 0.001  # a test input: the value a workflow's frozen basis would hand over
AFTER, BEFORE = "timeout_after_apply", "timeout_before_apply"
_ALL = {"ux": True, "uy": True, "uz": True, "rx": True, "ry": True, "rz": True}


def _seeded() -> dict[str, Any]:
    seed = _seed()
    seed["frame_sections"] = [{"name": "C30"}, {"name": "C40"}]
    seed["area_sections"] = [{"name": "SL", "type": "slab"}, {"name": "SL20", "type": "slab"}]
    seed["load_cases"] = [{"name": "DEAD"}]
    return seed


class Binder:
    """The bound instance of the only model; `pre_image` is the ref the next call's binding carries."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.pre_image: str | None = None
        self.current: int | None = None

    async def binding(self, host_key: str, model: str | None, descriptor: ToolDescriptor) -> Binding:
        target = HostTarget(product="ETABS", pid=self.pid)
        return Binding(target=target, host=HOST, owned=True, pre_image_ref=self.pre_image)

    def revision(self, model_id: str) -> int | None:
        return self.current


class Recorder:
    """The session side: the manager, noting the role and the tool of each call."""

    def __init__(self, manager: ServerManager) -> None:
        self.manager = manager
        self.sent: list[tuple[str, str]] = []

    async def call(self, server: str, role: str, tool: str, arguments: Any, effect: CallEffect) -> types.CallToolResult:
        self.sent.append((role, tool))
        return await self.manager.call(server, role, tool, arguments, effect)


@dataclass
class Rig:
    """The tool port over the fake with its binder, recorder and the fault control file."""

    port: Any
    binder: Binder
    recorder: Recorder
    store: ResultStore
    control: Path
    manager: ServerManager
    pid: int
    count: int = 0

    def value(self, name: str, number: float) -> dict[str, str]:
        producer = Provenance(
            tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
        )
        record = self.store.put("harness.run_input/1", {"value": {name: number}}, producer)
        return {"$ref": f"{record.result_id}#/value/{name}"}

    def arm(self, fault: str, tool: str) -> None:
        data = json.loads(self.control.read_text())
        data["faults"].append({"fault": fault, "tool": tool})
        self.control.write_text(json.dumps(data))

    async def engineer(self, tool: str, **arguments: Any) -> None:
        target = {"target": {"product": "ETABS", "pid": self.pid}}
        await self.manager.call("csi", "main", tool, {**target, **arguments}, CallEffect.WRITE)

    async def before(self, tool: str, args: dict[str, Any]) -> None:
        """Take the pre-image: the state of the object before the write, as `read_back` shows it."""
        envelope = await self.port.read_back(tool, {"model": "m", **args})
        assert isinstance(envelope, SuccessEnvelope), envelope
        self.binder.pre_image = f"{envelope.result_id}#/value/observed"

    async def cut_off(self, tool: str, args: dict[str, Any], fault: str, op_id: str = "op-1") -> None:
        """Send the write with `fault` armed: it comes back as a timeout of unknown outcome."""
        self.arm(fault, tool)
        reply = await self.port.call(tool, {"model": "m", **args}, op_id=op_id, model="m")
        assert isinstance(reply, FailureEnvelope), reply
        assert reply.error.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME

    async def reconcile(self, tool: str, args: dict[str, Any], op_id: str = "op-1") -> Reconciliation:
        return await self.port.reconcile(tool, {"model": "m", **args}, op_id)


@asynccontextmanager
async def _rig(
    config: ServersConfig, control: Path, store: ResultStore, run_dir: Path, *, tolerance: float | None = TOLERANCE,
    wired: bool = True,
) -> AsyncIterator[Rig]:  # fmt: skip
    from eng_harness.adapters.csi._reconcile import CsiReconciler

    from eng_harness.adapters.csi._tools import CsiToolPort

    control.write_text(json.dumps({"faults": [], "seed": _seeded()}))
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"reconcile", clock)
    async with ServerManager(config, run_dir) as manager:
        launched = await manager.call("csi", "main", "csi_launch", {"product": "ETABS"}, CallEffect.WRITE)
        block = launched.content[0]
        assert isinstance(block, types.TextContent)
        pid = json.loads(block.text)["pid"]
        manager.bind_instance("csi", pid=pid, product="ETABS")  # the long role attaches to it by process id
        binder, recorder = Binder(pid), Recorder(manager)
        extra: dict[str, Any] = (
            {"reconciler": CsiReconciler(product="ETABS", tolerance_ratio=tolerance)} if wired else {}
        )
        port = CsiToolPort(
            binder=binder, config=config, server="csi", caller=recorder, store=store, ledger=WriteLedger(run_dir),
            clock=clock, ids=ids, check=CHECK, errors=CsiErrorMapper(ids), **extra,
        )  # fmt: skip
        yield Rig(port, binder, recorder, store, control, manager, pid)


@pytest.fixture
def store(tmp_path: Path, ids: SeededIdSource) -> ResultStore:
    """A result store that knows the harness kinds and the CSI kinds of the adapter."""
    from eng_harness._kinds import HARNESS_KINDS
    from eng_harness.adapters.csi._replies import CSI_KINDS

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS.extend(CSI_KINDS), ids, FixedClock(1_767_225_600_000, 1))


def _combo(rig: Rig) -> dict[str, Any]:
    items = [{"case": {"case": "DEAD", "case_type": "load_pattern"}, "scale_ratio": 1.2}]
    return {"name": "C2", "type": "envelope", "items": items}


WRITES: dict[str, Callable[[Rig], dict[str, Any]]] = {
    "csi_assign_frame_section": lambda r: {"frame": "F1", "section": "C40"},
    "csi_assign_area_section": lambda r: {"area": "A1", "section": "SL20"},
    "csi_define_wall_section": lambda r: {
        "name": "W1", "material": "C30", "thickness_mm": r.value("thickness_mm", 250.0)
    },
    "csi_set_frame_load_distributed": lambda r: {
        "frame": "F1", "pattern": "DEAD", "w_kN_m": r.value("w_kN_m", 20.0)
    },
    "csi_set_area_load_uniform": lambda r: {"area": "A1", "pattern": "DEAD", "q_kPa": r.value("q_kPa", 8.0)},
    "csi_add_load_pattern": lambda r: {
        "name": "SNOW1", "type": "snow", "self_weight_ratio": r.value("w_ratio", 0.0)
    },
    "csi_add_load_combo": _combo,
    "csi_delete_load_combo": lambda r: {"name": "C1"},
    "csi_set_point_restraint": lambda r: {"joint": "P0", **_ALL},
}  # fmt: skip
CASES = [(tool, fault, outcome) for tool in WRITES for fault, outcome in ((AFTER, "applied"), (BEFORE, "not_applied"))]


@pytest.mark.parametrize(("tool", "fault", "expected"), CASES, ids=[f"{t}-{f}" for t, f, _ in CASES])
def test_outcomes_per_tool(
    tool: str, fault: str, expected: str, make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """Each write tool is reconciled from the state read back: applied after the write, not applied before it."""

    async def body() -> None:
        async with _rig(make_config(), control, store, run_dir) as rig:
            args = WRITES[tool](rig)
            await rig.before(tool, args)
            await rig.cut_off(tool, args, fault)
            found = await rig.reconcile(tool, args)
            assert found.outcome == expected
            assert found.missing == ()
            assert len(found.evidence) == 1  # the reads, stored as a result and referenced

    anyio.run(body)


LONG = [
    ("csi_run_analysis", {}, AFTER, True, 4),
    ("csi_run_analysis", {}, BEFORE, False, 1),
    ("csi_design_run", {"kind": "steel"}, AFTER, False, None),
    ("csi_design_run", {"kind": "steel"}, BEFORE, False, None),
]


@pytest.mark.parametrize(("tool", "args", "fault", "locked", "code"), LONG, ids=[f"{t}-{f}" for t, _, f, _, _ in LONG])
def test_long_tools_unknown_without_proof_of_end(
    tool: str, args: dict[str, Any], fault: str, locked: bool, code: int | None, make_config: ConfigFactory,
    control: Path, store: ResultStore, run_dir: Path,
) -> None:  # fmt: skip
    """Analysis and design are `unknown` whatever the host answers; the adapter sends no re-run."""

    async def body() -> None:
        async with _rig(make_config(), control, store, run_dir) as rig:
            await rig.cut_off(tool, args, fault)
            found = await rig.reconcile(tool, args)
            assert found.outcome == "unknown"
            assert found.missing == ()
            evidence: dict[str, Any] = store.get(found.evidence[0].ref.split("#")[0]).payload["value"]
            assert evidence["locked"] is locked
            assert evidence["proof_of_end"] is False
            if code is None:
                assert "analysis_status" not in evidence
            else:
                assert evidence["analysis_status"] == {"cases": [{"case": "DEAD", "status_code": code}]}
            assert [t for role, t in rig.recorder.sent if role == "long"] == [tool]  # no second run was sent

    anyio.run(body)
