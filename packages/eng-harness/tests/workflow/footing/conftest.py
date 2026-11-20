# ruff: noqa: N803  # reaction helpers keep contract unit suffixes (FZ_kN, MY_kNm)
"""Stand of the isolated-footing block tests (plan 0010 T8).

Test code, never shipped. Every basis and reaction value below is a synthetic test input labelled so; no case
reproduces a project. The test workflow runs the real `design_isolated_footing` block under the real harness calcs
and the real ACI 318-14 pack through `CodePackRoute`.

No ``from __future__ import annotations``: the nested workflow return type must resolve at decorate time the same
way as ``tests/workflow/edit_cycle/conftest.py``.
"""

import asyncio
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.envelope import Provenance
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from fakes.decision_providers import FakeDecisionProvider
from fakes.ports import FakeApprovalPort, FakeHost, FakeInputPort
from pydantic import BaseModel, JsonValue
from structural_codes.pack import Registry as PackRegistry

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._code_packs import FOOTING_CHECK_IDS, CodePackRoute
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.basis import StoreBasisPort
from eng_harness.block import Registry, workflow
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.footing.layout import BASIS_FIELDS as LAYOUT_FIELDS
from eng_harness.calcs.footing.plan_size import BASIS_FIELDS as PLAN_FIELDS
from eng_harness.calcs.footing.resize import BASIS_FIELDS as RESIZE_FIELDS
from eng_harness.decisions import Cascade, LabelStore
from eng_harness.decisions._points import discover
from eng_harness.decisions._policy import DecisionSettings
from eng_harness.decisions.interfaces import ChoiceAnswer
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
from eng_harness.ports import InputAnswer, InputRequest, RunClass, ToolInfo

BY = "engineer:test"
SOURCE = "engineer:test@2026-01-01T00:00:00.000Z"
ENTERED_AT = "2026-01-01T00:00:00.000Z"
CHECK_IDS = {base: base for base in FOOTING_CHECK_IDS}


class Empty(BaseModel):
    """No engineer workflow input beyond the stored refs."""


# Synthetic engineer basis for the footing block scenarios (spec 0010 4.7 paths; values from golden plan-gross
# overburden derivation and ACI packing needs). Cited in scenario JSON under tests/data/footing/.
BASIS_VALUES: dict[str, tuple[Any, str | None]] = {
    "foundation.allowable_bearing_pressure_kPa": (200.0, "kPa"),
    "foundation.allowable_bearing_kind": ("gross", None),
    "foundation.soil_unit_weight_kN_m3": (18.0, "kN/m3"),
    "foundation.soil_depth_above_footing_mm": (1000.0, "mm"),
    "foundation.surcharge_kPa": (10.0, "kPa"),
    "materials.concrete_unit_weight_kN_m3": (24.0, "kN/m3"),
    "materials.concrete_fc_MPa": (30.0, "MPa"),
    "materials.rebar_fy_MPa": (420.0, "MPa"),
    "materials.concrete_class": ("normalweight", None),
    "materials.rebar_coating": ("uncoated", None),
    "durability.cover_footing_mm": (75.0, "mm"),
    "limits.ratio_limit_ratio": (1.0, "1"),
    "foundation.min_plan_dimension_mm": (900.0, "mm"),
    "foundation.max_plan_dimension_mm": (4000.0, "mm"),
    "foundation.plan_increment_mm": (200.0, "mm"),
    "foundation.plan_shape": ("square", None),
    "foundation.min_depth_mm": (500.0, "mm"),
    "foundation.max_depth_mm": (1200.0, "mm"),
    "foundation.depth_increment_mm": (50.0, "mm"),
    "foundation.reaction_point": ("top_of_footing", None),
    "reinforcement.bar_diameter_mm": (16.0, "mm"),
    "reinforcement.max_spacing_mm": (300.0, "mm"),
    "reinforcement.min_spacing_mm": (100.0, "mm"),
    "reinforcement.spacing_increment_mm": (25.0, "mm"),
    "reinforcement.bottom_layer": ("x_bottom", None),
    "attempts.footing_rounds": (3, None),
    "attempts.cases": (2, None),
    "compare.angle_deg": (0.001, "deg"),
    "compare.length_mm": (0.001, "mm"),
    "checks.equilibrium_relative_tolerance_ratio": (0.05, "1"),
    "seismic.design_category": ("a", None),
    "seismic.special_system": ("no", None),
    "design.code_pack": ("aci318_14", None),
    "safe.cross_check": ("off", None),
    "foundation.min_clear_distance_mm": (50.0, "mm"),
}


def _warm_coverage_multiline_maps(folder: Path, rules_file: Path) -> None:
    """Pre-compute coverage.py's sysmon multiline maps outside `block_code()`."""
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
    """One test's workspace, store, scripted engineer and optional decision-model provider."""

    root: Path
    workspace: Workspace
    store: ResultStore
    clock: FixedClock
    ids: SeededIdSource
    basis_ref: str
    run_id: str
    subjects_ref: str
    reactions_ref: str
    service_ref: str
    factored_ref: str
    unused_dims_ref: str
    approvals: FakeApprovalPort = field(default_factory=FakeApprovalPort)
    inputs: FakeInputPort = field(default_factory=FakeInputPort)
    labels: list[LabelStore] = field(default_factory=list)
    model: FakeDecisionProvider | None = None

    def flow(self) -> Any:
        """The test workflow: one `design_isolated_footing` call (import here so a missing module fails the test)."""
        from eng_contract.refs import Ref

        from eng_harness.rules import footing as footing_rules
        from eng_harness.workflows import isolated_footing
        from eng_harness.workflows.isolated_footing._block import (
            CHECK_BASE_IDS,
            DesignIsolatedFootingInput,
            DesignIsolatedFootingOutput,
            design_isolated_footing,
        )

        _warm_coverage_multiline_maps(
            Path(isolated_footing.__file__).resolve().parent, Path(footing_rules.__file__).resolve()
        )

        required = tuple(sorted({*PLAN_FIELDS, *LAYOUT_FIELDS, *RESIZE_FIELDS, *BASIS_VALUES}))

        @workflow(
            name="footing_block_test",
            version=1,
            description="Runs the real design_isolated_footing block under its real calcs and ACI pack.",
            required_basis=required,
        )
        async def run(ctx: Any, inp: Empty) -> DesignIsolatedFootingOutput:
            out = await ctx.block(
                design_isolated_footing,
                DesignIsolatedFootingInput(
                    subjects=Ref.model_validate({"$ref": self.subjects_ref}),
                    reactions=Ref.model_validate({"$ref": self.reactions_ref}),
                    service_cases=Ref.model_validate({"$ref": self.service_ref}),
                    factored_cases=Ref.model_validate({"$ref": self.factored_ref}),
                    check_ids={base: base for base in CHECK_BASE_IDS},
                    unused_engineer_dims=Ref.model_validate({"$ref": self.unused_dims_ref}),
                ),
            )
            return cast(DesignIsolatedFootingOutput, out)

        return run

    def engine(self, flow: Any) -> Engine:
        """An engine over the real calc port (with the ACI code-pack route) and the decision cascade."""
        pack_registry = PackRegistry.discover()
        route = CodePackRoute(
            pack_registry,
            self.store,
            max_items=10_000,
            run_class=RunClass.TRIAL,
            clock=self.clock,
            ids=self.ids,
            allowed=frozenset(FOOTING_CHECK_IDS),
        )
        calc = HarnessCalcPort(
            REGISTRY,
            ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []}),
            self.store,
            CalcSettings(max_items=10_000),
            RunClass.TRIAL,
            self.clock,
            self.ids,
            basis_fields={
                "harness.footing_plan_size": PLAN_FIELDS,
                "harness.footing_layout": LAYOUT_FIELDS,
                "harness.footing_resize": RESIZE_FIELDS,
            },
            code_packs=route,
        )
        settings = DecisionSettings()
        labels = LabelStore(self.workspace.root.parent, settings, self.clock, self.ids)
        self.labels.append(labels)
        providers: dict[str, Any] = {} if self.model is None else {"model": self.model}
        cascade = Cascade(
            discover(),
            settings,
            labels,
            clock=self.clock,
            monotonic=time.monotonic,
            rule_guard=rule_guard,
            max_concurrent_decisions=EngineSettings().max_concurrent_decisions,
            **providers,
        )
        host = FakeHost(
            (ToolInfo(name="noop_read", effect="read", action="plain", host_key="csi"),),
            self.ids,
            self.clock,
        )
        bound = EnginePorts(
            tool=host,
            host=host,
            calc=calc,
            basis=StoreBasisPort(self.store),
            approvals=self.approvals,
            inputs=self.inputs,
            decision=cascade,
        )
        return Engine(self.workspace, Registry([flow]), bound, self.store, EngineSettings(), self.clock, self.ids)

    def request(self) -> RunRequest:
        return RunRequest(
            workflow="footing_block_test",
            input={},
            basis_ref=self.basis_ref,
            run_class=RunClass.TRIAL,
            mode=PermissionMode.WORK_ON_COPY,
            run_id=self.run_id,
        )

    def play(self, responder: Callable[[Stand, InputRequest], InputAnswer | None]) -> RunOutcome:
        """Start the run and answer every pause until it ends."""

        async def body() -> RunOutcome:
            engine = self.engine(self.flow())
            outcome = await engine.start(self.request())
            for _ in range(40):
                if outcome.status is not RunStatus.PAUSED:
                    return outcome
                shown = self.shown(outcome.pending[0])
                answered = responder(self, shown)
                assert answered is not None, f"nothing to answer {shown!r}"
                self.inputs.script(shown.request_id, answered)
                outcome = await engine.resume(outcome.run_id)
            raise AssertionError(f"the run did not end: {outcome}")

        try:
            return asyncio.run(body())
        finally:
            for store in self.labels:
                store.close()
            self.labels.clear()

    def shown(self, request_id: str) -> InputRequest:
        found = [r for r in self.inputs.presented if r.request_id == request_id]
        assert found, request_id
        return found[-1]

    def give(self, request: InputRequest, values: Mapping[str, JsonValue]) -> InputAnswer:
        return InputAnswer(
            request_id=request.request_id, shown_sha256=request.fields_schema_sha256, values=dict(values), by=BY
        )

    def choose(self, request: InputRequest, option: str) -> InputAnswer:
        props: dict[str, Any] = cast(dict[str, Any], request.fields_schema["properties"])
        choices = {name: option for name, prop in props.items() if "enum" in prop and option in prop["enum"]}
        return InputAnswer(
            request_id=request.request_id, shown_sha256=request.fields_schema_sha256, choices=choices, by=BY
        )

    def events(self) -> list[Any]:
        reader = JournalReader(self.workspace.root / "runs" / self.run_id)
        try:
            return reader.events()
        finally:
            reader.close()

    def steps(self, kind: str | None = None) -> list[Any]:
        return [
            e.payload for e in self.events() if isinstance(e.payload, ev.StepStarted) and kind in (None, e.payload.kind)
        ]


def _put(
    store: ResultStore,
    kind: str,
    payload: dict[str, JsonValue],
    producer: Provenance,
) -> str:
    return store.put(kind, payload, producer).result_id


def _field(value: Any, unit: str | None) -> dict[str, JsonValue]:
    return {"value": value, "unit": unit, "source": SOURCE, "confirmed": True, "citation": None}


def _engineer_list(names: Sequence[str], field: str) -> dict[str, JsonValue]:
    return {
        "step": "test",
        "fields": {
            field: {"value": list(names), "unit": None, "entered_by": "test", "entered_at": ENTERED_AT},
        },
    }


def _unused_engineer_dims(used: Mapping[str, tuple[Any, str | None]]) -> dict[str, JsonValue]:
    """Ask-shaped Quantity fields for unused resize engineer refs (spec 0010 4.4.4; values from the stand basis)."""
    plan = used["foundation.min_plan_dimension_mm"][0]
    depth = used["foundation.min_depth_mm"][0]
    spacing = used["reinforcement.max_spacing_mm"][0]
    entered = {"unit": None, "entered_by": "test", "entered_at": ENTERED_AT}
    return {
        "step": "unused_resize_dims",
        "fields": {
            "L": {"value": {"value": plan, "unit": "mm"}, **entered},
            "h": {"value": {"value": depth, "unit": "mm"}, **entered},
            "s": {"value": {"value": spacing, "unit": "mm"}, **entered},
        },
    }


def build_stand(
    root: Path,
    *,
    subjects: Mapping[str, JsonValue],
    reactions: Mapping[str, JsonValue],
    service_cases: Sequence[str] = ("S1",),
    factored_cases: Sequence[str] = ("U1",),
    basis: Mapping[str, tuple[Any, str | None]] | None = None,
    model: FakeDecisionProvider | None = None,
) -> Stand:
    """A stand with stored subjects, reactions, case lists and a confirmed design basis."""
    root.mkdir(parents=True, exist_ok=True)
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"b399-" + root.name.encode(), clock)
    workspace = Workspace(root=root / "workspace", classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    producer = Provenance(tool="test/footing", tool_version="1", inputs={}, started_at=clock.now(), duration_ms=0)
    used = BASIS_VALUES if basis is None else {**BASIS_VALUES, **basis}
    fields: dict[str, JsonValue] = {path: _field(value, unit) for path, (value, unit) in used.items()}
    basis_id = _put(store, "basis.design_basis/1", {"template": None, "fields": fields}, producer)
    subjects_id = _put(store, "harness.footing_subjects/1", dict(subjects), producer)
    reactions_id = _put(store, "forces.joint_reactions/1", dict(reactions), producer)
    service_id = _put(store, "basis.engineer_input/1", _engineer_list(service_cases, "service_cases"), producer)
    factored_id = _put(store, "basis.engineer_input/1", _engineer_list(factored_cases, "factored_cases"), producer)
    unused_id = _put(store, "basis.engineer_input/1", _unused_engineer_dims(used), producer)
    return Stand(
        root,
        workspace,
        store,
        clock,
        ids,
        basis_id,
        f"run_{ids.new_ulid()}",
        subjects_id,
        reactions_id,
        service_id,
        factored_id,
        unused_id,
        model=model,
    )


def subject(
    footing_id: str = "F1",
    joint: str = "J1",
    column: str = "C1",
    *,
    cx_mm: float = 400.0,
    cy_mm: float = 400.0,
) -> dict[str, JsonValue]:
    """One footing subject (synthetic)."""
    return {
        "id": footing_id,
        "joint": joint,
        "column": column,
        "x_mm": 0.0,
        "y_mm": 0.0,
        "cx_mm": cx_mm,
        "cy_mm": cy_mm,
    }


def reaction_row(
    joint: str,
    case: str,
    *,
    fz_kN: float,
    mx_kNm: float = 0.0,
    my_kNm: float = 0.0,
    fx_kN: float = 0.0,
    fy_kN: float = 0.0,
) -> dict[str, JsonValue]:
    """One joint reaction row (synthetic; forces.joint_reactions/1)."""
    return {
        "joint": joint,
        "case": {"case": case, "case_type": "load_combination", "step": None},
        "FX_kN": fx_kN,
        "FY_kN": fy_kN,
        "FZ_kN": fz_kN,
        "MX_kNm": mx_kNm,
        "MY_kNm": my_kNm,
        "MZ_kNm": 0.0,
    }


def subjects_payload(*rows: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "subjects": list(rows),
        "excluded": [],
        "calc": {
            "id": "harness.footing_subjects",
            "version": 1,
            "content_sha256": "ab" * 32,
            "status": "draft",
        },
        "draft": True,
        "trace": {
            "calc_id": "harness.footing_subjects",
            "calc_version": "1",
            "content_sha256": "ab" * 32,
            "inputs": [],
            "constants": [],
            "steps": [],
            "outputs": [],
        },
    }


def reactions_payload(*rows: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"axes": "global", "rows": list(rows)}


def shadow_model(*choices: str) -> FakeDecisionProvider:
    """A fake decision provider that suggests the given options (shadow only; engineer still decides)."""
    return FakeDecisionProvider(choices=[ChoiceAnswer(choice=c, confidence=0.9) for c in choices])


@pytest.fixture
def tmp_stand_root(tmp_path: Path) -> Path:
    return tmp_path
