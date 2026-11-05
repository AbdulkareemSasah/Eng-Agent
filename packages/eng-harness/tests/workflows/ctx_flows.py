"""Test workflows and helpers of the ctx tests: a block body wrapped as a workflow or child block (plan 0001 T10).

Test doubles for spec 0001 AC9 to AC15 and AC27; never shipped. The body is plain Python under `tests/`, so the rules
for block modules do not apply. `need_approval` stands for the approval of plan task T15: it asks the approval port
for an
answer and pauses the run when there is none.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from eng_contract.envelope import Provenance, SuccessEnvelope
from eng_contract.ids import new_result_id
from pydantic import BaseModel, JsonValue

from eng_harness.block import BlockDef, WorkflowDef, block, workflow
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


def flow(body: Body, *, name: str = "chain", version: int = 1) -> WorkflowDef[ChainInput, ChainOutput]:
    """A workflow that runs `body` and returns what it returns as the references of its output."""

    @workflow(name=name, version=version, description="Runs its body.")
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
