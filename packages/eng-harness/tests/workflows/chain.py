"""Test workflows of the engine tests: tools called in order, and a block with a wrong return value.

Test doubles for plan 0001 T9 and T9b (spec 0001 AC16, AC28, AC29); never shipped. The block code is plain Python with
no rules of its own to follow, because it lives under `tests/`, not under `block_modules`.
"""

from collections.abc import Sequence
from typing import Any, cast

from pydantic import BaseModel, JsonValue

from eng_harness.block import WorkflowDef, workflow

Step = tuple[str, dict[str, JsonValue]]
"""A tool name and its arguments."""

ORIGINAL: list[Step] = [("read_a", {"n": 0}), ("write_b", {"n": 1, "model": "m1"}), ("read_c", {"n": 2})]
"""The steps of the workflow that the divergence tests interrupt and then change."""


class ChainInput(BaseModel):
    """Input of the test workflows: a label and a count (an integer, so a string for it is an invalid input)."""

    label: str = "x"
    count: int = 0


class ChainOutput(BaseModel):
    """Output of the test workflows: the result reference of each step, in order."""

    refs: list[str]


class RetypedInput(BaseModel):
    """`ChainInput` with a string where the original has an integer: a run input that no longer fits."""

    label: str = "x"
    count: str = ""


class Impostor(BaseModel):
    """A model that is not `ChainOutput`."""

    refs: list[str] = []


def chain(
    steps: Sequence[Step], *, name: str = "chain", version: int = 1, always_ask: tuple[str, ...] = ()
) -> WorkflowDef[ChainInput, ChainOutput]:
    """A workflow that calls each of `steps` in order and returns their result references."""

    @workflow(name=name, version=version, description="Calls its tools in order.", always_ask=always_ask)
    async def run(ctx: Any, inp: ChainInput) -> ChainOutput:
        refs = []
        for tool, args in steps:
            result = await ctx.tool(tool, args)
            refs.append(result.ref.ref)
        return ChainOutput(refs=refs)

    return run


@workflow(name="bad_output", version=1, description="Returns a value that is not its output model.")
async def bad_output(ctx: Any, inp: ChainInput) -> ChainOutput:
    """Returns an `Impostor`, which the engine must refuse."""
    return cast(ChainOutput, Impostor())


@workflow(name="chain", version=1, description="Calls its tools in order.")
async def chain_retyped(ctx: Any, inp: RetypedInput) -> ChainOutput:
    """The `ORIGINAL` steps under the name and version of `chain`, with an input model that changed its type."""
    refs = []
    for tool, args in ORIGINAL:
        result = await ctx.tool(tool, args)
        refs.append(result.ref.ref)
    return ChainOutput(refs=refs)
