"""Stand of the edit-cycle workflow tests (plan 0007 T8): the real engine, the real calcs and the real CSI adapter over
the synthetic CSI fake server process, with scripted engineer answers (spec 0007 section 3, "fake-host workflow test").

Test code, never shipped. Every basis value below is a synthetic test input of the engineer, not an engineering value;
the fake's model values are synthetic too. The test workflow runs the real child blocks of the cycle under the real
definition (basis fields, copy on open) and returns what each cycle produced.
"""

import asyncio
import json
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.envelope import Provenance
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from fakes.ports import FakeApprovalPort, FakeInputPort
from fakes.sasaah_csi.wiring import Inspector, config
from pydantic import BaseModel, JsonValue

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters import build_ports
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.basis import StoreBasisPort
from eng_harness.block import Registry, workflow
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.design_summary import BASIS_FIELDS as DESIGN_FIELDS
from eng_harness.calcs.edit_cycle.analysis_summary import BASIS_FIELDS as ANALYSIS_FIELDS
from eng_harness.calcs.edit_cycle.change_set_check import BASIS_FIELDS as CHECK_FIELDS
from eng_harness.calcs.edit_cycle.host_design_verdicts import BASIS_FIELDS as VERDICT_FIELDS
from eng_harness.calcs.model_diff import BASIS_FIELDS as DIFF_FIELDS
from eng_harness.decisions import Cascade, LabelStore
from eng_harness.decisions._points import discover
from eng_harness.decisions._policy import DecisionSettings
from eng_harness.engine import (
    Engine,
    EnginePorts,
    EngineSettings,
    PermissionMode,
    RunOutcome,
    RunRequest,
    RunStatus,
    rule_guard,
)
from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalAnswer, ApprovalRequest, InputAnswer, InputRequest, RunClass
from eng_harness.servers._launcher import PosixLauncher
from workflow.adapters.test_readback import _seeded

MODEL_KEY = "m"
BY = "engineer:test"
SOURCE = "engineer:test@2026-01-01T00:00:00.000Z"
VALUES: dict[str, tuple[Any, str | None]] = {  # synthetic test inputs: path -> (value, unit)
    "compare.length_mm": (0.001, "mm"),
    "compare.angle_deg": (0.001, "deg"),
    "compare.stress_MPa": (0.001, "MPa"),
    "compare.unit_weight_kN_m3": (0.001, "kN/m3"),
    "compare.line_load_kN_m": (0.001, "kN/m"),
    "compare.area_load_kPa": (0.001, "kPa"),
    "compare.dimensionless_ratio": (0.001, "1"),
    "checks.readback_relative_tolerance_ratio": (0.25, "1"),
    "report.top_n": (5, None),
    "limits.ratio_limit_ratio": (1.0, "1"),
    "limits.drift_ratio": (0.01, "1"),
    "bounds.thickness_min_mm": (100.0, "mm"),
    "bounds.thickness_max_mm": (1000.0, "mm"),
    "bounds.line_load_min_kN_m": (0.0, "kN/m"),
    "bounds.line_load_max_kN_m": (100.0, "kN/m"),
    "bounds.area_load_min_kPa": (0.0, "kPa"),
    "bounds.area_load_max_kPa": (50.0, "kPa"),
    "bounds.ratio_min_ratio": (0.0, "1"),
    "bounds.ratio_max_ratio": (5.0, "1"),
    "design.run": ("steel", None),
    "attempts.cycles": (3, None),
    "attempts.change_set": (2, None),
    "attempts.approval_void": (2, None),
}
ITEM_SECTION: dict[str, JsonValue] = {"id": "a1", "kind": "frame_section", "frames": ["F1"], "section": "C40"}
ITEM_LOAD: dict[str, JsonValue] = {
    "id": "a2",
    "kind": "frame_uniform_load",
    "frames": ["F1"],
    "pattern": "DEAD",
    "direction": "gravity",
    "w": {"source": "input", "value": 20.0, "unit": "kN/m"},
}
ITEM_AREA: dict[str, JsonValue] = {"id": "a3", "kind": "area_section", "areas": ["A1"], "section": "SL20"}
LOADS = "Frame Loads Assignments - Distributed"


STOP = object()
"""What a responder returns to end `Stand.play` at the request it was shown; the outcome is then the paused one."""


def _warm_coverage_multiline_maps(folder: Path, rules_file: Path) -> None:
    """Pre-compute coverage.py's sysmon multiline maps outside `block_code()`.

    Under `coverage run --branch` on Python 3.14, `SysMonitor` lazily calls `open()` on a file the first time a
    branch inside it runs; for block and rule modules that happens while the runtime guard blocks `open()`.
    """
    cov_mod = sys.modules.get("coverage")
    current = getattr(getattr(cov_mod, "Coverage", None), "current", lambda: None)()
    collector = getattr(current, "_collector", None)
    for tracer in getattr(collector, "tracers", ()):
        get_map = getattr(tracer, "get_multiline_map", None)
        if callable(get_map):
            for path in (*folder.glob("*.py"), rules_file):
                get_map(str(path))


@dataclass
class Stand:
    """One test's workspace, store, fake server control file, ports and engineer."""

    root: Path
    control: Path
    workspace: Workspace
    store: ResultStore
    clock: FixedClock
    ids: SeededIdSource
    basis_ref: str
    original: Path
    run_id: str
    approvals: FakeApprovalPort = field(default_factory=FakeApprovalPort)
    inputs: FakeInputPort = field(default_factory=FakeInputPort)
    labels: list[LabelStore] = field(default_factory=list)
    hooks: dict[str, Callable[[], None]] = field(default_factory=dict)

    def ports(self) -> Any:
        """The production CSI ports of the run over the fake server process (enter with `async with`)."""
        return build_ports(
            config(self.control), self.workspace, self.store, self.run_dir, self.clock, self.ids,
            inspector=Inspector(self.control), launcher=PosixLauncher(), lock_dir=self.root / "locks",
            files={MODEL_KEY: self.original},
        )  # fmt: skip

    @property
    def run_dir(self) -> Path:
        """The folder of the run."""
        return self.workspace.root / "runs" / self.run_id

    def flow(self, cycles: int = 1, *, ask: bool = True, summarize: bool = False, min_build: str | None = None) -> Any:
        """The test workflow: open the model, then `cycles` of `edit_cycle_once` (and `run_and_summarize` when asked).

        The workflow code is imported here, so that a missing module fails the test and not the collection.
        `min_build` overrides the workflow minimum Sasaah commit (the stale-build test).
        """
        from eng_harness.rules import edit_cycle as edit_rules
        from eng_harness.workflows import model_edit_cycle
        from eng_harness.workflows.model_edit_cycle import BASIS_FIELDS, EditCycleInput
        from eng_harness.workflows.model_edit_cycle._cycle import (
            CycleInput,
            CycleOutput,
            Route,
            SummarizeInput,
            SummarizeOutput,
            edit_cycle_once,
            run_and_summarize,
        )
        from eng_harness.workflows.model_edit_cycle._points import TurnAction

        _warm_coverage_multiline_maps(
            Path(model_edit_cycle.__file__).resolve().parent, Path(edit_rules.__file__).resolve()
        )
        build = csi_allowlist().sasaah_commit if min_build is None else min_build

        class FlowOutput(BaseModel):
            """What the test workflow returns: each cycle and, when asked, each summarize step."""

            cycles: list[CycleOutput]
            summaries: list[SummarizeOutput] = []

        @workflow(
            name="edit_cycle_test",
            version=1,
            description="Runs the real cycle blocks of the edit cycle under its real definition.",
            min_server_builds={"csi": build},
            always_ask=("csi_unlock_model",),
            basis_fields=BASIS_FIELDS,
            copy_on_open=True,
        )
        async def run(ctx: Any, inp: EditCycleInput) -> FlowOutput:
            await ctx.tool("csi_open_model", {"model": MODEL_KEY})
            done: list[CycleOutput] = []
            summarized: list[SummarizeOutput] = []
            previous = None
            designs: dict[str, Any] = {}
            ask_next = ask
            for _ in range(cycles):
                out = await ctx.block(edit_cycle_once, CycleInput(model=MODEL_KEY, previous=previous, ask=ask_next))
                previous = out.state
                done.append(out)
                if not summarize or out.route != Route.DONE:
                    continue
                summary = await ctx.block(
                    run_and_summarize,
                    SummarizeInput(
                        model=MODEL_KEY,
                        state=out.state,
                        diff=out.diff,
                        readback=out.readback,
                        previous_designs=tuple(designs.items()),
                    ),
                )
                summarized.append(summary)
                designs = dict(summary.designs)
                if summary.turn == TurnAction.ACCEPT:
                    break
                ask_next = summary.turn == TurnAction.MORE_EDITS
            return FlowOutput(cycles=done, summaries=summarized)

        return run

    def engine(self, ports: Any, flow: Any) -> Engine:
        """An engine over the real calc port, the real decision cascade and the scripted approval and input ports."""
        calc = HarnessCalcPort(
            REGISTRY,
            ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []}),
            self.store,
            CalcSettings(max_items=10_000),
            RunClass.TRIAL,
            self.clock,
            self.ids,
            basis_fields={
                "harness.model_diff": DIFF_FIELDS,
                "harness.readback_check": DIFF_FIELDS,
                "harness.change_set_check": CHECK_FIELDS,
                "harness.analysis_summary": ANALYSIS_FIELDS,
                "harness.host_design_verdicts": VERDICT_FIELDS,
                "harness.design_summary": DESIGN_FIELDS,
            },
        )
        settings = DecisionSettings()
        labels = LabelStore(self.workspace.root.parent, settings, self.clock, self.ids)
        self.labels.append(labels)
        cascade = Cascade(
            discover(), settings, labels, clock=self.clock, monotonic=time.monotonic, rule_guard=rule_guard
        )
        bound = EnginePorts(
            tool=ports.tool_port, host=ports.host_port, calc=calc, basis=StoreBasisPort(self.store),
            approvals=self.approvals, inputs=self.inputs, decision=cascade,
        )  # fmt: skip
        return Engine(self.workspace, Registry([flow]), bound, self.store, EngineSettings(), self.clock, self.ids)

    def request(self, mode: PermissionMode = PermissionMode.WORK_ON_COPY) -> RunRequest:
        """The run request of the test workflow."""
        return RunRequest(
            workflow="edit_cycle_test",
            input={"model": str(self.original), "visible_host": False},
            basis_ref=self.basis_ref,
            run_class=RunClass.TRIAL,
            mode=mode,
            run_id=self.run_id,
        )

    def play(
        self,
        flow: Any,
        responder: Callable[[Any, Any], Any],
        *,
        cycles_hook: Any = None,
        mode: PermissionMode = PermissionMode.WORK_ON_COPY,
    ) -> RunOutcome:
        """Start the run and answer every pause with `responder(stand, request)` until it ends or stops."""

        async def body() -> RunOutcome:
            async with self.ports() as ports:
                engine = self.engine(ports, flow)
                if cycles_hook is not None:
                    cycles_hook(ports)
                outcome = await engine.start(self.request(mode=mode))
                for _ in range(40):  # a bound, never reached by a run that behaves
                    if outcome.status is not RunStatus.PAUSED:
                        return outcome
                    shown = self.shown(outcome.pending[0])
                    answered = responder(self, shown)
                    if answered is STOP:
                        return outcome
                    assert answered is not None, f"nothing to answer {shown!r}"
                    (self.approvals if isinstance(shown, ApprovalRequest) else self.inputs).script(
                        shown.request_id, answered
                    )
                    outcome = await engine.resume(outcome.run_id)
                raise AssertionError(f"the run did not end: {outcome}")

        try:
            return asyncio.run(body())
        finally:
            for store in self.labels:
                store.close()
            self.labels.clear()

    def shown(self, request_id: str) -> ApprovalRequest | InputRequest:
        """The request with this id, as last presented to the engineer."""
        found: list[ApprovalRequest | InputRequest] = []
        for request in (*self.approvals.presented, *self.inputs.presented):
            if isinstance(request, ApprovalRequest | InputRequest) and request.request_id == request_id:
                found.append(request)
        assert found, request_id
        return found[-1]

    def approve(
        self, request: ApprovalRequest, *, rejected: tuple[str, ...] = (), decision: str = "approve"
    ) -> ApprovalAnswer:
        """The engineer's answer to an approval: approve (with some items rejected), or reject the whole set."""
        return ApprovalAnswer(
            request_id=request.request_id,
            shown_sha256=request.shown_sha256,
            decision="reject" if decision == "reject" else "approve",
            rejected_items=rejected,
            item_reasons=dict.fromkeys(rejected, "test: rejected"),
            reason="test: rejected" if decision == "reject" else None,
            by=BY,
        )

    def give(self, request: InputRequest, values: Mapping[str, JsonValue]) -> InputAnswer:
        """The engineer's data answer to a data request."""
        return InputAnswer(
            request_id=request.request_id, shown_sha256=request.fields_schema_sha256, values=values, by=BY
        )

    def choose(self, request: InputRequest, option: str) -> InputAnswer:
        """The engineer's choice: `option` for every question of the request (the properties with an enum)."""
        props: dict[str, Any] = cast(dict[str, Any], request.fields_schema["properties"])
        choices = {name: option for name, prop in props.items() if "enum" in prop and option in prop["enum"]}
        accept = {name: "accept" for name, prop in props.items() if "enum" in prop and "accept" in prop["enum"]}
        return InputAnswer(
            request_id=request.request_id,
            shown_sha256=request.fields_schema_sha256,
            choices=choices or accept,
            by=BY,
        )

    def model(self) -> dict[str, Any]:
        """The fake's model as the control file holds it."""
        loaded: dict[str, Any] = json.loads(self.control.read_text())["model"]
        return loaded

    def hand_edit(self, change: Callable[[dict[str, Any]], None]) -> None:
        """Change the fake's model between two calls, as the engineer would in the host program."""
        data = json.loads(self.control.read_text())
        change(data["model"])
        self.control.write_text(json.dumps(data))

    def calls(self, tool: str | None = None) -> list[dict[str, Any]]:
        """The calls the fake served, in order, optionally of one tool."""
        recorded: list[dict[str, Any]] = json.loads(self.control.read_text()).get("calls", [])
        return [c for c in recorded if tool is None or c["tool"] == tool]

    def events(self) -> list[Any]:
        """The run's journal."""
        reader = JournalReader(self.run_dir)
        try:
            return reader.events()
        finally:
            reader.close()

    def steps(self, kind: str | None = None) -> list[Any]:
        """The `step_started` payloads of the journal, optionally of one step kind."""
        return [
            e.payload for e in self.events() if isinstance(e.payload, ev.StepStarted) and kind in (None, e.payload.kind)
        ]

    def results(self, calc_id: str) -> list[dict[str, Any]]:
        """The stored payloads of every completed run of a calc, in journal order."""
        done = [
            e.payload.result
            for e in self.events()
            if isinstance(e.payload, ev.StepCompleted) and e.payload.calc and e.payload.calc.id == calc_id
        ]
        return [dict(self.store.payload(r.ref)) for r in done if r is not None]


def seed_results(
    stand: Stand,
    *,
    drifts: list[dict[str, Any]] | None = None,
    design: dict[str, list[dict[str, Any]]] | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> None:
    """Put synthetic analysis results, design rows and optional analysis messages into the fake control file."""
    data = json.loads(stand.control.read_text())
    seed = data.setdefault("seed", {})
    results = seed.setdefault("results", {})
    if drifts is not None:
        results["csi_results_story_drifts"] = drifts
    if design is not None:
        seed["design_results"] = design
    if messages is not None:
        tables = seed.setdefault("tables", {})
        tables["Analysis Messages"] = messages
    stand.control.write_text(json.dumps(data))


def arm_fault(stand: Stand, fault: str, tool: str) -> None:
    """Arm a one-shot fake fault on `tool` (removed when it fires)."""
    data = json.loads(stand.control.read_text())
    data.setdefault("faults", []).append({"fault": fault, "tool": tool})
    stand.control.write_text(json.dumps(data))


def build_stand(root: Path, *, values: Mapping[str, tuple[Any, str | None]] | None = None) -> Stand:
    """A stand over a fake model with one frame, one area, a frame load and the synthetic basis of `VALUES`."""
    root.mkdir(parents=True, exist_ok=True)
    control = root / "control.json"
    _seeded(control)
    data = json.loads(control.read_text())
    data["persist_model"] = True
    data["seed"]["frame_sections"] = [{"name": "C30"}, {"name": "C40"}]
    data["seed"]["area_sections"] = [{"name": "SL", "type": "slab"}, {"name": "SL20", "type": "slab"}]
    control.write_text(json.dumps(data))
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"b526-" + root.name.encode(), clock)
    workspace = Workspace(root=root / "workspace", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    used = VALUES if values is None else values
    fields: dict[str, JsonValue] = {
        path: {"value": value, "unit": unit, "source": SOURCE, "confirmed": True, "citation": None}
        for path, (value, unit) in used.items()
    }
    producer = Provenance(tool="test/stand", tool_version="1", inputs={}, started_at=clock.now(), duration_ms=0)
    basis = store.put("basis.design_basis/1", {"template": None, "fields": fields}, producer)
    original = root / "original.EDB"
    original.write_bytes(b"synthetic model")
    return Stand(root, control, workspace, store, clock, ids, basis.result_id, original, f"run_{ids.new_ulid()}")


@pytest.fixture
def stand(tmp_path: Path) -> Stand:
    """A stand over a fake model with one frame, one area, a frame load and the synthetic basis of `VALUES`."""
    return build_stand(tmp_path)
