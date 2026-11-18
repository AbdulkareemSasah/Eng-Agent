"""A frozen design basis reaches `ctx.basis` in a fake-host run and survives a replay (plan 0004 T10; spec 0004 AC28).

Every template, value and bound here is a synthetic placeholder, not an engineering value.
"""

import asyncio
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
from eng_contract.envelope import Provenance
from eng_contract.errors import ErrorCode
from eng_contract.kinds.basis import BasisField, DesignBasis
from fakes.ports import FakeCalcPort, failure
from pydantic import BaseModel
from workflows.chain import ChainInput
from workflows.rig import Rig, Spy, make_rig, request

from eng_harness.basis import (
    BasisSetupAnswer,
    EngineerEntry,
    EngineerValues,
    FieldSpec,
    StoreBasisPort,
    build_draft,
    freeze,
)
from eng_harness.block import BlockDef, Registry, workflow
from eng_harness.engine import Engine, EnginePorts, EngineSettings, RunStatus
from eng_harness.errors import HarnessCode, RunRefused
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev
from eng_harness.templates import Template, resolve

CITE = "Synthetic placeholder, not an engineering value"
TOL = "modeling.merge_tolerance_mm"
STORIES = "analysis.stories"
METHOD = "analysis.method"
AT = "2026-01-01T00:00:00.000Z"


class Method(StrEnum):
    """The choice of the synthetic basis."""

    A = "a"
    B = "b"


class BasisOutput(BaseModel):
    """What the workflow read from `ctx.basis`, as typed values, and the result references of its steps."""

    tolerance: float
    unit: str
    stories: int
    method: str
    tolerance_ref: str
    refs: list[str]


@workflow(
    name="reads_basis", version=1, description="Reads a quantity, a count and a choice.",
    required_basis=(TOL, STORIES, METHOD),
)  # fmt: skip
async def _reads_basis(ctx: Any, inp: ChainInput) -> BasisOutput:
    tolerance = ctx.basis.quantity(TOL)
    stories = ctx.basis.count(STORIES)
    method = ctx.basis.choice(METHOD, Method)
    first = await ctx.tool("read_a", {"n": int(stories)})
    second = await ctx.tool("read_c", {"n": 1})
    return BasisOutput(
        tolerance=tolerance.value, unit=tolerance.unit, stories=int(stories), method=method.value,
        tolerance_ref=ctx.basis.ref(TOL).ref, refs=[first.ref.ref, second.ref.ref],
    )  # fmt: skip


class _Source:
    def __init__(self, template: Template) -> None:
        self._template = template

    def find(self, name: str, version: str) -> Template | None:
        meta = self._template.meta
        return self._template if (name, version) == (meta.name, meta.version) else None


def _frozen_basis(rig: Rig) -> str:
    """Freeze a confirmed synthetic basis into the rig's store, register it with the engine's basis port; its ref."""
    specs = [
        FieldSpec(path=TOL, kind="quantity", label="Tolerance", unit="mm"),
        FieldSpec(path=STORIES, kind="count", label="Stories"),
        FieldSpec(path=METHOD, kind="choice", label="Method", choices=("a", "b")),
    ]
    data = {
        "schema": "eng-template/1",
        "meta": {"name": "synthetic-base", "version": "0.1.0", "synthetic": True},
        "ask_each_run": [],
        "modeling": {"merge_tolerance_mm": {"value": 2.5, "unit": "mm", "citation": CITE}},
    }
    base = Template.from_data(data)
    values = {STORIES: EngineerEntry(value=4), METHOD: EngineerEntry(value="b")}
    draft = build_draft(
        specs, resolve(base, _Source(base)), EngineerValues(name="syn", values=values), [], source=_Source(base)
    )
    answer = BasisSetupAnswer(
        setup_id="01JABCDEFGHJKMNPQRSTVWXYZ0", draft_sha256=draft.sha256,
        confirmed_sections=("analysis", "modeling"), by="engineer-a", at=AT,
    )  # fmt: skip
    ref = freeze(draft, answer, rig.store, rig.clock).ref
    rig.bases = {**rig.bases, ref: StoreBasisPort(rig.store).load(ref)}
    return ref


def test_basis_reaches_ctx_and_replays(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    ref = _frozen_basis(rig)
    # the values arrive typed and the run header holds the basis reference
    done = asyncio.run(rig.engine(_reads_basis).start(request(workflow="reads_basis", basis_ref=ref)))
    assert done.status is RunStatus.COMPLETED
    assert isinstance(done.output, BasisOutput)
    assert (done.output.tolerance, done.output.unit) == (2.5, "mm")
    assert (done.output.stories, done.output.method) == (4, "b")
    assert done.output.tolerance_ref == f"{ref}#/fields/{TOL}/value"
    assert rig.header(done.run_id).basis_ref == ref
    # an interrupted run replays: the resume does not repeat the recorded step, does not diverge and ends equal
    rig.host.script("read_c", failure(ErrorCode.HOST_BUSY))
    stopped = asyncio.run(rig.engine(_reads_basis).start(request(workflow="reads_basis", basis_ref=ref)))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    calls = [entry.tool for entry in rig.host.ledger]
    again = asyncio.run(rig.engine(_reads_basis).resume(stopped.run_id))
    assert again.status is RunStatus.COMPLETED
    assert isinstance(again.output, BasisOutput)
    assert (again.output.tolerance, again.output.stories, again.output.method) == (2.5, 4, "b")
    reasons = [e.payload.reason for e in rig.events(stopped.run_id) if isinstance(e.payload, ev.RunEscalated)]
    assert reasons == ["unhandled_error"]  # the scripted failure only: the replay did not diverge
    assert EventType.RUN_RESUMED in rig.types(stopped.run_id)
    assert [entry.tool for entry in rig.host.ledger][len(calls) :].count("read_a") == 0
    assert rig.header(stopped.run_id).basis_ref == ref


def test_unconfirmed_basis_refuses_the_run(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    ref = _frozen_basis(rig)
    stored = rig.bases[ref].basis
    unconfirmed = DesignBasis(
        template=stored.template,
        fields={
            path: BasisField(
                value=field.value, unit=field.unit, source=field.source, confirmed=path != METHOD,
                citation=field.citation,
            )
            for path, field in stored.fields.items()
        },
    )  # fmt: skip
    producer = Provenance(tool="harness", tool_version="test", inputs={}, started_at=AT, duration_ms=0)
    raw = rig.store.put("basis.design_basis/1", unconfirmed.model_dump(mode="json"), producer)
    rig.bases = {**rig.bases, raw.result_id: StoreBasisPort(rig.store).load(raw.result_id)}
    before = rig.run_ids()
    with pytest.raises(RunRefused) as refused:
        asyncio.run(rig.engine(_reads_basis).start(request(workflow="reads_basis", basis_ref=raw.result_id)))
    assert refused.value.code is HarnessCode.BASIS_INCOMPLETE
    assert refused.value.evidence == (METHOD,)
    assert rig.run_ids() == before


def _store_engine(rig: Rig, *workflows: BlockDef[Any, Any]) -> Engine:
    """An engine over `rig` whose basis port is `StoreBasisPort(rig.store)` instead of the in-memory fake."""
    calc = FakeCalcPort(rig.run_class, rig.calc_infos)
    calc.results, calc.runs = rig.calc_results, rig.calc_runs
    ports = EnginePorts(
        tool=Spy("tool", rig.host, rig.log),
        host=Spy("host", rig.host, rig.log),
        calc=Spy("calc", calc, rig.log),
        basis=Spy("basis", StoreBasisPort(rig.store), rig.log),
        approvals=Spy("approvals", rig.approvals, rig.log),
        inputs=Spy("inputs", rig.inputs, rig.log),
    )
    return Engine(rig.workspace, Registry(workflows), ports, rig.store, EngineSettings(), rig.clock, rig.ids)


def test_basis_reaches_ctx_over_the_store_port(tmp_path: Path) -> None:
    """AC28 over `StoreBasisPort`: the frozen basis reaches `ctx.basis` from the store under the runtime guard."""
    rig = make_rig(tmp_path)
    ref = _frozen_basis(rig)
    done = asyncio.run(_store_engine(rig, _reads_basis).start(request(workflow="reads_basis", basis_ref=ref)))
    assert done.status is RunStatus.COMPLETED
    assert isinstance(done.output, BasisOutput)
    assert (done.output.tolerance, done.output.unit) == (2.5, "mm")
    assert (done.output.stories, done.output.method) == (4, "b")
    assert done.output.tolerance_ref == f"{ref}#/fields/{TOL}/value"
    assert rig.header(done.run_id).basis_ref == ref
    assert "basis.load" in rig.log
