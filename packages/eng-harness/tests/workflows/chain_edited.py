"""Test workflow `chain` version 1 with another module source, so its code hash differs (spec 0001 AC29).

Same name, version and behavior as `workflows.chain.chain` called with the steps of `STEPS`; only this text differs,
which is what a refactor without a version bump looks like. A test double, never shipped.
"""

from typing import Any

from pydantic import JsonValue

from eng_harness.block import workflow
from workflows.chain import ChainInput, ChainOutput

STEPS: list[tuple[str, dict[str, JsonValue]]] = [("read_a", {"n": 1}), ("write_b", {"n": 2})]


@workflow(name="chain", version=1, description="Calls its tools in order.")
async def chain_edited(ctx: Any, inp: ChainInput) -> ChainOutput:
    """The edited copy of the chain workflow."""
    refs = []
    for tool, args in STEPS:
        result = await ctx.tool(tool, args)
        refs.append(result.ref.ref)
    return ChainOutput(refs=refs)
