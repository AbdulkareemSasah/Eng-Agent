"""SAP2000 analysis on the long role (plan 0012 T6; spec 0012 AC14).

Adapter imports sit inside the tests so a missing module fails the test. Analysis is a `long`-class tool: the call goes
to the `long` role (its own call timeout) and its `action` makes the engine save first (0002 AC29 interim: locked edits
are `HOST_LOCKED`). Gap SP-6: the run-case selection is the saved one; no tool changes it.
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
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._launcher import LaunchedProcess, LaunchSpec, PosixLauncher

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
MAIN_S, LONG_S = 30, 90


class SpyLauncher:
    """The POSIX launcher that remembers each process's specification."""

    def __init__(self) -> None:
        self.specs: list[LaunchSpec] = []
        self._inner = PosixLauncher()

    def start(self, spec: LaunchSpec) -> LaunchedProcess:
        self.specs.append(spec)
        return self._inner.start(spec)

    def timeouts(self) -> dict[str, str]:
        return {s.stderr_path.name: s.argv[s.argv.index("--call-timeout-sec") + 1] for s in self.specs}


class Recorder:
    """The session side: notes the role and the tool of each call."""

    def __init__(self, manager: ServerManager) -> None:
        self.manager = manager
        self.sent: list[tuple[str, str, dict[str, Any]]] = []

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        self.sent.append((role, tool, dict(arguments)))
        return await self.manager.call(server, role, tool, arguments, effect)


class Binder:
    """The bound instance of the only SAP2000 model."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    async def binding(self, host_key: str, model: str | None, descriptor: ToolDescriptor) -> Binding:
        return Binding(target=HostTarget(product="SAP2000", pid=self.pid), host=HOST, owned=True)

    def revision(self, model_id: str) -> int | None:
        return None


@pytest.fixture
def store(tmp_path: Path, ids: SeededIdSource) -> ResultStore:
    from eng_harness._kinds import HARNESS_KINDS

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS, ids, FixedClock(1_767_225_600_000, 1))


def _timeouts(config: ServersConfig) -> ServersConfig:
    server = config.servers["csi"].model_copy(
        update={
            "product": "SAP2000",
            "host_key": "csi_sap2000",
            "roles": {
                "main": config.servers["csi"].roles["main"].model_copy(update={"call_timeout_s": MAIN_S}),
                "long": config.servers["csi"].roles["long"].model_copy(update={"call_timeout_s": LONG_S}),
            },
        }
    )
    return ServersConfig(servers={"csi_sap2000": server})


def test_long_role_save_first(make_config: ConfigFactory, control: Path, store: ResultStore, tmp_path: Path) -> None:
    """AC14: SAP2000 analysis goes to `long` after save; the model is locked and an edit is `HOST_LOCKED` (SP-6)."""
    from eng_harness.adapters.csi._tools import CsiToolPort
    from eng_harness.adapters.csi.products import _sap2000_results as results

    assert "csi_run_analysis" in results.READERS

    control.write_text(json.dumps({"faults": [], "seed": {"load_cases": [{"name": "DEAD"}]}, "product": "SAP2000"}))
    launcher = SpyLauncher()
    run_dir = tmp_path / "run"
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"sap-analysis", clock)

    async def scenario() -> None:
        async with ServerManager(_timeouts(make_config()), run_dir, launcher=launcher) as manager:
            launched = await manager.call(
                "csi_sap2000", "main", "csi_launch", {"product": "SAP2000"}, CallEffect.WRITE
            )
            block = launched.content[0]
            assert isinstance(block, types.TextContent)
            pid = json.loads(block.text)["pid"]
            manager.bind_instance("csi_sap2000", pid=pid, product="SAP2000")
            recorder = Recorder(manager)
            port = CsiToolPort(
                binder=Binder(pid),
                config=_timeouts(make_config()),
                server="csi_sap2000",
                caller=recorder,
                store=store,
                ledger=WriteLedger(run_dir),
                clock=clock,
                ids=ids,
                check=CHECK,
                errors=CsiErrorMapper(ids),
            )
            info = await port.describe("csi_run_analysis")
            assert (info.effect, info.action, info.model_param) == ("write", "analysis", "model")
            analysis = await port.call("csi_run_analysis", {"model": "m"}, op_id="op-analysis", model="m")
            assert isinstance(analysis, SuccessEnvelope), analysis
            assert analysis.kind == "harness.csi_analysis_run/1"
            assert analysis.data == {"started": True}
            assert recorder.sent[0][0] == "long"
            assert recorder.sent[0][1] == "csi_run_analysis"
            # SP-6: analysis sends no case-selection argument; the saved selection is used.
            assert "cases" not in recorder.sent[0][2]
            assert "combos" not in recorder.sent[0][2]
            locked = await port.call(
                "csi_assign_frame_section",
                {"model": "m", "frame": "F1", "section": "C300"},
                op_id="op-edit",
                model="m",
            )
            assert isinstance(locked, FailureEnvelope), locked
            assert locked.error.code is ErrorCode.HOST_LOCKED

    anyio.run(scenario)
    assert launcher.timeouts() == {
        "csi_sap2000-main.stderr.log": str(MAIN_S),
        "csi_sap2000-long.stderr.log": str(LONG_S),
    }
