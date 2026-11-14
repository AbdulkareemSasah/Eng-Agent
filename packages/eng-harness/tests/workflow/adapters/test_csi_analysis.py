"""CSI analysis, design and results through the ToolPort against the synthetic fake (plan 0002 T13; spec 0002 AC28).

Analysis and design are `long`-class tools: the call goes to the `long` role server, which has its own call timeout, and
its descriptor says `action` `analysis` or `design`, which is what makes the engine save the model first (engine
invariant 7, AC43). The status and result reads stay on the `main` role. The units token of the results is `kN_m_C`
(spec 4.6.1): the seeded rows are in metres and kilonewtons, so a length maps to millimetres by a factor of 1000.
The adapter imports are inside the tests so a missing module fails the test.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import HostInfo, SuccessEnvelope
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from mcp import types

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._launcher import LaunchedProcess, LaunchSpec, PosixLauncher

from .test_csi_session_ops import ConfigFactory

HOST = HostInfo(program="ETABS", version="22.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0)
SHA = "d" * 64
CHECK = ServerCheck(
    server="csi", build="0123456789ab+fedcba987654", min_build="", fingerprint=SHA, expected_fingerprint=SHA, ok=True,
    reason=None,
)  # fmt: skip
MAIN_S, LONG_S = 30, 90  # the call timeouts of the two roles: the long one is its own, not the main one's
SEED = {
    "load_cases": [{"name": "DEAD"}, {"name": "LIVE"}],
    "results": {
        "csi_results_joint_reactions": [
            {"joint": "J1", "case": "DEAD", "F1": 1.5, "F2": -2.0, "F3": 120.25, "M1": 0.5, "M2": -0.25, "M3": 0.0},
        ],
        "csi_results_frame_forces": [
            {
                "frame": "B1", "case": "1.4D", "kind": "combo", "station": 1.25, "P": -10.0, "V2": 4.5, "V3": 0.0,
                "T": 0.0, "M2": 0.0, "M3": -7.75,
            },
        ],
        "csi_results_story_drifts": [
            {
                "story": "S1", "case": "EQX", "direction": "X", "drift": 0.0025, "label": "J2", "x": 5.0, "y": 0.0,
                "z": 3.0,
            },
        ],
    },
    "design_results": {
        "steel": [{"frame": "B1", "ratio": 0.75, "ratio_type": "PMM", "location": 1.5, "combo": "1.4D"}]
    },
}  # fmt: skip


class SpyLauncher:
    """The POSIX launcher that remembers each process's specification."""

    def __init__(self) -> None:
        self.specs: list[LaunchSpec] = []
        self._inner = PosixLauncher()

    def start(self, spec: LaunchSpec) -> LaunchedProcess:
        self.specs.append(spec)
        return self._inner.start(spec)

    def timeouts(self) -> dict[str, str]:
        """The `--call-timeout-sec` of each started role, by its log file name."""
        return {s.stderr_path.name: s.argv[s.argv.index("--call-timeout-sec") + 1] for s in self.specs}


class Recorder:
    """The session side: the manager, noting the role and the tool of each call."""

    def __init__(self, manager: ServerManager) -> None:
        self.manager = manager
        self.sent: list[tuple[str, str, dict[str, Any]]] = []

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        self.sent.append((role, tool, dict(arguments)))
        return await self.manager.call(server, role, tool, arguments, effect)


class Binder:
    """The bound instance of the only model."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    async def binding(self, host_key: str, model: str | None, descriptor: ToolDescriptor) -> Binding:
        return Binding(target=HostTarget(product="ETABS", pid=self.pid), host=HOST, owned=True)

    def revision(self, model_id: str) -> int | None:
        return None


@pytest.fixture
def store(tmp_path: Path, ids: SeededIdSource) -> ResultStore:
    """A result store that knows the harness kinds and the CSI kinds of the adapter."""
    from eng_harness._kinds import HARNESS_KINDS
    from eng_harness.adapters.csi._replies import CSI_KINDS

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS.extend(CSI_KINDS), ids, FixedClock(1_767_225_600_000, 1))


def _timeouts(config: ServersConfig) -> ServersConfig:
    server = config.servers["csi"]
    roles = {
        "main": server.roles["main"].model_copy(update={"call_timeout_s": MAIN_S}),
        "long": server.roles["long"].model_copy(update={"call_timeout_s": LONG_S}),
    }
    return ServersConfig(servers={"csi": server.model_copy(update={"roles": roles})})


def _run(
    config: ServersConfig, run_dir: Path, store: ResultStore, body: Any, launcher: SpyLauncher | None = None
) -> None:
    from eng_harness.adapters.csi._tools import CsiToolPort

    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"analysis", clock)

    async def scenario() -> None:
        async with ServerManager(config, run_dir, launcher=launcher) as manager:
            launched = await manager.call("csi", "main", "csi_launch", {"product": "ETABS"}, CallEffect.WRITE)
            block = launched.content[0]
            assert isinstance(block, types.TextContent)
            pid = json.loads(block.text)["pid"]
            manager.bind_instance("csi", pid=pid, product="ETABS")  # the long role attaches to it by process id
            recorder = Recorder(manager)
            port = CsiToolPort(
                binder=Binder(pid), config=config, server="csi", caller=recorder, store=store,
                ledger=WriteLedger(run_dir), clock=clock, ids=ids, check=CHECK, errors=CsiErrorMapper(ids),
            )  # fmt: skip
            await body(port, recorder, pid)

    anyio.run(scenario)


def _call(port: Any, tool: str, **arguments: Any) -> Any:
    return port.call(tool, {"model": "m", **arguments}, op_id=f"op-{tool}", model="m")


def test_long_role_and_save_first(make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path) -> None:
    """Analysis and design go to the `long` role, started with its own timeout; their action makes the engine save."""
    control.write_text(json.dumps({"faults": [], "seed": SEED}))
    launcher = SpyLauncher()

    async def body(port: Any, recorder: Recorder, pid: int) -> None:
        for tool, action in (("csi_run_analysis", "analysis"), ("csi_design_run", "design")):
            info = await port.describe(tool)
            assert (info.effect, info.action, info.model_param) == ("write", action, "model")
        analysis = await _call(port, "csi_run_analysis")
        assert isinstance(analysis, SuccessEnvelope), analysis
        assert analysis.kind == "harness.csi_analysis_run/1"
        design = await _call(port, "csi_design_run", kind="steel")
        assert isinstance(design, SuccessEnvelope), design
        assert design.kind == "harness.csi_design_run/1"
        status = await _call(port, "csi_analysis_status")
        assert isinstance(status, SuccessEnvelope), status
        assert status.kind == "harness.csi_analysis_status/1"
        target = {"target": {"product": "ETABS", "pid": pid}}
        assert recorder.sent == [
            ("long", "csi_run_analysis", {"confirm": True, **target}),
            ("long", "csi_design_run", {"kind": "steel", "confirm": True, **target}),
            ("main", "csi_analysis_status", target),
        ]

    _run(_timeouts(make_config()), run_dir, store, body, launcher)
    assert launcher.timeouts() == {"csi-main.stderr.log": str(MAIN_S), "csi-long.stderr.log": str(LONG_S)}
