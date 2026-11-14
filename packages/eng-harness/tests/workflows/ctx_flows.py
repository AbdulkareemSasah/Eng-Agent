"""Test workflows and helpers of the ctx tests: a block body wrapped as a workflow or child block (plan 0001 T10).

Test doubles for spec 0001 AC9 to AC15 and AC27; never shipped. The body is plain Python under `tests/`, so the rules
for block modules do not apply. `need_approval` stands for the approval of plan task T15: it asks the approval port
for an
answer and pauses the run when there is none.
"""

import hashlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal

from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.ids import new_result_id
from pydantic import BaseModel, JsonValue

from eng_harness.block import BlockDef, WorkflowDef, block, workflow
from eng_harness.ctx import ModelHandle, Preview, PreviewItem
from eng_harness.errors import Pause
from eng_harness.ports import ApprovalAnswer, ApprovalPort
from workflows.chain import ChainInput, ChainOutput
from workflows.rig import Rig

Body = Callable[[Any], Awaitable[Sequence[str]]]
"""A block body: it takes the ctx and returns the result references it wants in the output."""


class ChildInput(BaseModel):
    """Input of the child test block."""

    n: int = 0


class ChildOutput(BaseModel):
    """Output of the child test block: the result references of its steps."""

    refs: list[str]


def flow(
    body: Body, *, name: str = "chain", version: int = 1, always_ask: tuple[str, ...] = ()
) -> WorkflowDef[ChainInput, ChainOutput]:
    """A workflow that runs `body` and returns what it returns as the references of its output."""

    @workflow(name=name, version=version, description="Runs its body.", always_ask=always_ask)
    async def run(ctx: Any, inp: ChainInput) -> ChainOutput:
        return ChainOutput(refs=list(await body(ctx)))

    return run


def child(body: Body, *, name: str = "child", version: int = 1) -> BlockDef[ChildInput, ChildOutput]:
    """A child block that runs `body` and returns what it returns as the references of its output."""

    @block(name=name, version=version)
    async def run(ctx: Any, inp: ChildInput) -> ChildOutput:
        return ChildOutput(refs=list(await body(ctx)))

    return run


def success(rig: Rig, summary: Mapping[str, JsonValue]) -> SuccessEnvelope:
    """A success envelope whose summary is `summary`, for a scripted tool or calc result."""
    producer = Provenance(tool="harness", tool_version="fake", inputs={}, started_at=rig.clock.now(), duration_ms=0)
    return SuccessEnvelope(
        contract="eng-contract/1", ok=True, result_id=new_result_id(rig.ids), kind="harness.run_output/1",
        summary=dict(summary), complete=True, provenance=producer,
    )  # fmt: skip


def answer(request_id: str) -> ApprovalAnswer:
    """An approving answer to the request `request_id`."""
    return ApprovalAnswer(request_id=request_id, shown_sha256="a" * 64, decision="approve", by="engineer:test")


async def need_approval(port: ApprovalPort, request_id: str) -> ApprovalAnswer:
    """The answer to `request_id`, or a pause of the run when there is none (the stub of plan task T15's approval)."""
    given = await port.answer(request_id, wait=False)
    if given is None:
        raise Pause("awaiting approval", evidence=[request_id])
    return given


def written(rig: Rig, model_key: str, revision: int) -> SuccessEnvelope:
    """A write result as an adapter returns it: stored, with the revision the write produced in `provenance.host`."""
    state = rig.host.models[model_key]
    assert state.model_id is not None
    host = HostInfo(program="csi", version="1", model_id=state.model_id, model_revision=revision)
    producer = Provenance(
        tool="harness", tool_version="fake", host=host, inputs={}, started_at=rig.clock.now(), duration_ms=0
    )
    stored = rig.store.put("harness.run_output/1", {"value": {"revision": revision}}, producer)
    return SuccessEnvelope(
        contract="eng-contract/1", ok=True, result_id=stored.result_id, kind="harness.run_output/1",
        summary={"revision": revision}, complete=True, provenance=producer,
    )  # fmt: skip


def change_set(rig: Rig, *items: str, models: Sequence[str] = ("m1",)) -> Preview:
    """A preview with the items `items` over the open models `models`, at the revision the fake host holds."""
    handles = []
    for key in models:
        state = rig.host.models[key]
        assert state.model_id is not None
        handles.append(ModelHandle(model_key=key, model_id=state.model_id, revision=state.revision or 0))
    shown = tuple(PreviewItem(id=item, label=f"Change {item}", refs=()) for item in items)
    return Preview(items=shown, diff_ref=None, models=tuple(handles))


def reply(
    rig: Rig, *, decision: Literal["approve", "reject"] = "approve", rejected: Mapping[str, str] | None = None,
    notes: Mapping[str, str] | None = None, acknowledged: bool = False, sha: str | None = None,
    rid: str | None = None, by: str = "ada",
) -> ApprovalAnswer:  # fmt: skip
    """The engineer's answer to the request the approval port presented last; `rejected` maps item to reason."""
    shown = rig.approvals.presented[-1]
    given = dict(rejected or {})
    return ApprovalAnswer(
        request_id=rid or shown.request_id, shown_sha256=sha or shown.shown_sha256, decision=decision,
        rejected_items=tuple(given), item_reasons={**given, **(notes or {})}, acknowledged_unreleased=acknowledged,
        reason="because", by=by,
    )  # fmt: skip


def request_id(run_id: str, path: str) -> str:
    """The id of the approval requested at step `path` of the run (spec 0001 4.9), computed here from the rule."""
    return "apr_" + hashlib.sha256(f"{run_id}\n{path}".encode()).hexdigest()[:32]
