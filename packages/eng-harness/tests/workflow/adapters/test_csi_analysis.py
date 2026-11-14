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
from eng_contract.envelope import FailureEnvelope, HostInfo, SuccessEnvelope
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds import NEUTRAL_KINDS
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
    "frames": [{"name": "F1", "section": "C30"}],
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
    config: ServersConfig,
    run_dir: Path,
    store: ResultStore,
    body: Any,
    launcher: SpyLauncher | None = None,
    marks: list[str] | None = None,
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
                wrote=None if marks is None else marks.append,
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


def test_status_after_analysis_and_design_rows(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """The status read on `main` sees the analysis run on `long` (raw codes); design rows follow the design run."""
    control.write_text(json.dumps({"faults": [], "seed": SEED}))

    async def body(port: Any, recorder: Recorder, pid: int) -> None:
        before = await _call(port, "csi_analysis_status")
        assert isinstance(before, SuccessEnvelope), before
        assert before.data == {"cases": [{"case": "DEAD", "status_code": 1}, {"case": "LIVE", "status_code": 1}]}
        refused = await _call(port, "csi_design_results", kind="steel")
        assert isinstance(refused, FailureEnvelope), refused  # no design run yet: the host says so
        assert "run csi_design_run first" in refused.error.message
        run = await _call(port, "csi_run_analysis")
        assert isinstance(run, SuccessEnvelope), run
        assert run.data == {"started": True}
        after = await _call(port, "csi_analysis_status")
        assert isinstance(after, SuccessEnvelope), after
        assert after.data == {"cases": [{"case": "DEAD", "status_code": 4}, {"case": "LIVE", "status_code": 4}]}
        await _call(port, "csi_design_run", kind="steel")
        rows = await _call(port, "csi_design_results", kind="steel")
        assert isinstance(rows, SuccessEnvelope), rows
        assert rows.kind == "harness.csi_design_results/1"
        assert rows.data == {
            "rows": [{"frame": "B1", "ratio": 0.75, "ratio_type": "PMM", "location": 1.5, "combo": "1.4D"}]
        }
        sent = [(role, tool) for role, tool, _ in recorder.sent]
        assert sent[-1] == ("main", "csi_design_results")
        assert recorder.sent[-1][2]["limit"] == 2000  # the largest page the tool allows

    _run(make_config(), run_dir, store, body)


def test_unsupported_design_kinds(make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path) -> None:
    """Aluminum and cold-formed design are `NOT_SUPPORTED_BY_VERSION`: the host says so and the adapter maps it."""
    control.write_text(json.dumps({"faults": [], "seed": SEED}))

    async def body(port: Any, recorder: Recorder, pid: int) -> None:
        for kind in ("aluminum", "coldformed"):
            reply = await _call(port, "csi_design_run", kind=kind)
            assert isinstance(reply, FailureEnvelope), reply
            assert reply.error.code is ErrorCode.NOT_SUPPORTED_BY_VERSION

    _run(make_config(), run_dir, store, body)


def test_force_results_are_neutral_kinds(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """The three force reads send the token `kN_m_C` and store neutral payloads; lengths are millimetres."""
    control.write_text(json.dumps({"faults": [], "seed": SEED}))
    cases = {"cases": ["DEAD"], "combos": ["1.4D"]}

    async def body(port: Any, recorder: Recorder, pid: int) -> None:
        reactions = await _call(port, "csi_results_joint_reactions", object="J1", **cases)
        frames = await _call(port, "csi_results_frame_forces", **cases)
        drifts = await _call(port, "csi_results_story_drifts", **cases)
        for reply, kind in (
            (reactions, "forces.joint_reactions/1"),
            (frames, "forces.member_end/1"),
            (drifts, "forces.story_drifts/1"),
        ):
            assert isinstance(reply, SuccessEnvelope), reply
            assert reply.kind == kind
            NEUTRAL_KINDS[kind].model_validate(reply.data)
        assert [(role, tool) for role, tool, _ in recorder.sent] == [("main", t) for t in (
            "csi_results_joint_reactions", "csi_results_frame_forces", "csi_results_story_drifts"
        )]  # fmt: skip
        target = {"product": "ETABS", "pid": pid}
        assert recorder.sent[0][2] == {**cases, "object": "J1", "units": "kN_m_C", "target": target}
        assert recorder.sent[1][2] == {**cases, "units": "kN_m_C", "target": target}
        assert recorder.sent[2][2] == {**cases, "units": "kN_m_C", "target": target}
        assert reactions.data["rows"][0]["FZ_kN"] == 120.25  # kN stays kN
        assert frames.data["rows"][0]["station_mm"] == 1250.0  # 1.25 m
        assert frames.data["rows"][0]["case"] == {"case": "1.4D", "case_type": "load_combination", "step": None}
        assert drifts.data["rows"][0]["x_mm"] == 5000.0  # 5.0 m

    _run(make_config(), run_dir, store, body)


def test_only_edits_are_marked_as_writes(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """An edit tells the host port the next change is the adapter's; analysis, design and reads change no model row."""
    control.write_text(json.dumps({"faults": [], "seed": SEED}))
    marks: list[str] = []

    async def body(port: Any, recorder: Recorder, pid: int) -> None:
        edit = await _call(port, "csi_assign_frame_section", frame="F1", section="C40")
        assert isinstance(edit, SuccessEnvelope), edit
        assert marks == ["m"]
        marks.clear()
        for tool, arguments in (
            ("csi_run_analysis", {}),
            ("csi_analysis_status", {}),
            ("csi_design_run", {"kind": "steel"}),
            ("csi_design_results", {"kind": "steel"}),
            ("csi_results_joint_reactions", {}),
        ):
            reply = await _call(port, tool, **arguments)
            assert isinstance(reply, SuccessEnvelope), reply
        assert marks == []

    _run(make_config(), run_dir, store, body, marks=marks)


def test_argument_bounds() -> None:
    """The design kind is one of the four the host names; the row cap is the host's 1 to 2000, 2000 by default."""
    from pydantic import ValidationError

    from eng_harness.adapters.csi._tools import ANALYSIS_MODELS

    results = ANALYSIS_MODELS["DesignResultsArgs"]
    assert results.model_validate({"model": "m", "kind": "concrete"}).model_dump()["limit"] == 2000
    for limit in (1, 2000):
        assert results.model_validate({"model": "m", "kind": "steel", "limit": limit}).model_dump()["limit"] == limit
    for bad in ({"limit": 0}, {"limit": 2001}, {"kind": "timber"}):
        with pytest.raises(ValidationError):
            results.model_validate({"model": "m", "kind": "steel", **bad})
    with pytest.raises(ValidationError):
        ANALYSIS_MODELS["DesignRunArgs"].model_validate({"model": "m", "kind": "timber"})
    assert ANALYSIS_MODELS["ResultsStoryDriftsArgs"].model_validate({"model": "m"}).model_dump() == {
        "model": "m",
        "cases": [],
        "combos": [],
    }
